# -*- coding: utf-8 -*-
"""
USO DIARIO: audio(s) -> informe(s) en Word con las marcas de revision.

  - Arrastra uno o varios audios sobre  informe.bat
  - o deja los audios en la carpeta  Audios_nuevos  y hace doble clic en informe.bat

Genera en la carpeta Informes:
  NOMBRE.docx             -> el informe con tu formato y las partes a revisar resaltadas
  revision\\NOMBRE.html    -> el mismo informe al lado del dictado, con el audio:
                             clic en una marca = escuchar ese momento
La configuracion (fuente, modelo, carpetas...) esta en configuracion.json
"""
import gc
import html
import json
import os
import re
import sys
import time
from pathlib import Path

import nucleo as N
from fase1_transcribir import cargar_modelo, transcribir, duracion

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

AQUI = Path(__file__).resolve().parent
EXT_AUDIO = {".wav", ".mp3", ".m4a", ".ogg", ".flac", ".wma", ".aac", ".opus"}


def config():
    archivo = AQUI / "configuracion.json"
    if not archivo.exists():                    # primera vez (repositorio recién clonado): copia del ejemplo
        ejemplo = AQUI / "configuracion.ejemplo.json"
        if ejemplo.exists():
            archivo.write_text(ejemplo.read_text(encoding="utf-8-sig"), encoding="utf-8")
    c = json.loads(archivo.read_text(encoding="utf-8-sig"))
    for k in ("carpeta_audios_nuevos", "carpeta_informes"):
        p = Path(c[k])
        c[k] = p if p.is_absolute() else (AQUI / p).resolve()
    return c


def juntar_audios(args, cfg):
    rutas = []
    for a in args or [str(cfg["carpeta_audios_nuevos"])]:
        p = Path(a)
        if p.is_dir():
            rutas += sorted(x for x in p.iterdir() if x.suffix.lower() in EXT_AUDIO)
        elif p.suffix.lower() in EXT_AUDIO and p.exists():
            rutas.append(p)
    return rutas


# ------------------------------------------------------------------- Word
COLORES = None


PAGINA_DEF = {"nombre": "A4", "ancho_cm": 21.0, "alto_cm": 29.7, "margen_superior_cm": 7.5,
              "margen_inferior_cm": 4.0, "margen_izquierdo_cm": 1.3, "margen_derecho_cm": 3.0}
ALINEACIONES = ("left", "center", "right", "justify")


def pagina(cfg):
    """Tamaño de hoja y márgenes del Word (configuracion.json -> "pagina"; si no está, los de siempre)."""
    p = dict(PAGINA_DEF)
    p.update({k: v for k, v in (cfg.get("pagina") or {}).items() if k in PAGINA_DEF})
    return p


def parrafos_docx(marcado, cfg):
    """Los párrafos tal como quedan en el Word, sin los renglones vacíos del encabezado.
    None = renglón vacío. Lo usan el Word y la vista previa de la interfaz (así son idénticos)."""
    # lineas: sacar vacias repetidas y, si se pide, las vacias entre titulo y texto
    lineas = []
    for ln in marcado:
        vacia = not "".join(t for t, _, _ in ln["segs"]).strip()
        if vacia and (not lineas or lineas[-1] is None):
            continue
        lineas.append(None if vacia else ln)
    while lineas and lineas[-1] is None:
        lineas.pop()
    if not cfg["linea_vacia_entre_titulo_y_texto"]:
        lineas = [x for i, x in enumerate(lineas)
                  if not (x is None and i > 0 and lineas[i - 1] is not None and lineas[i - 1]["titulo"])]
    out = []
    for ln in lineas:
        if ln is None:
            out.append(None)
            continue
        segs = ln["segs"]
        segs = [(segs[0][0].lstrip(), *segs[0][1:])] + list(segs[1:]) if segs else segs
        alin = "center" if ln["titulo"] and cfg.get("centrar_titulos", True) else ""
        out.append({"segs": segs, "linea": ln["linea"], "alin": alin, "alin_def": alin,
                    "negrita": N.debe_ir_en_negrita("".join(t for t, _, _ in ln["segs"]), ln["titulo"], cfg)})
    return out


def texto_parrafo(p):
    return "".join(t for t, _, _ in p["segs"]).rstrip()


def aplicar_formato(pars, formato):
    """Formato elegido a mano en la vista previa (negrita, cursiva, subrayado, color, alineación).
    Se aplica a cada párrafo cuyo texto sigue igual; si después se cambió el texto de un párrafo en el
    informe, ese párrafo vuelve al formato normal. Modifica pars (agrega "runs" y cambia "alin")."""
    lista = [f for f in ((formato or {}).get("parrafos") or []) if isinstance(f, dict) and isinstance(f.get("t"), str)]
    usados, desde = set(), 0
    for p in pars:
        if p is None:
            continue
        t = texto_parrafo(p)
        k = next((i for i in list(range(desde, len(lista))) + list(range(0, desde))
                  if i not in usados and lista[i]["t"] == t), None)
        if k is None:
            continue
        usados.add(k)
        desde = k + 1
        f = lista[k]
        if f.get("a") in ALINEACIONES or f.get("a") == "":
            p["alin"] = f["a"]
        runs = []
        for r in f.get("r") or []:
            if not isinstance(r, dict) or not isinstance(r.get("t"), str) or not r["t"]:
                continue
            c = r.get("c") or ""
            runs.append({"t": r["t"], "b": bool(r.get("b")), "i": bool(r.get("i")), "u": bool(r.get("u")),
                         "c": c if re.fullmatch(r"#[0-9a-fA-F]{6}", c) else ""})
        if runs and "".join(r["t"] for r in runs) == t:
            p["runs"] = runs
    return pars


def escribir_docx(marcado, destino, cfg, formato=None):
    from docx import Document
    from docx.enum.text import WD_COLOR_INDEX as C, WD_ALIGN_PARAGRAPH as A
    from docx.oxml.ns import qn
    from docx.shared import Cm, Pt, RGBColor
    color = {"numero": C.RED, "completar": C.RED, "dudoso": C.YELLOW, "bajaconf": C.YELLOW,
             "plantilla": C.GRAY_25, "verificar": C.TURQUOISE}

    doc = Document()
    if cfg.get("pagina"):
        pg, sec = pagina(cfg), doc.sections[0]
        sec.page_width, sec.page_height = Cm(pg["ancho_cm"]), Cm(pg["alto_cm"])
        sec.top_margin, sec.bottom_margin = Cm(pg["margen_superior_cm"]), Cm(pg["margen_inferior_cm"])
        sec.left_margin, sec.right_margin = Cm(pg["margen_izquierdo_cm"]), Cm(pg["margen_derecho_cm"])
    st = doc.styles["Normal"]
    st.font.name = cfg["fuente"]
    st.font.size = Pt(cfg["tamano_fuente"])
    rfonts = st.element.get_or_add_rPr().get_or_add_rFonts()
    for att in ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia"):
        rfonts.set(qn(att), cfg["fuente"])
    pf = st.paragraph_format
    pf.space_before = Pt(0)
    pf.space_after = Pt(0)
    pf.line_spacing = 1.0

    for _ in range(int(cfg["lineas_vacias_para_encabezado"])):
        doc.add_paragraph()

    alinear = {"left": A.LEFT, "center": A.CENTER, "right": A.RIGHT, "justify": A.JUSTIFY}
    pars = parrafos_docx(marcado, cfg)
    if formato:
        aplicar_formato(pars, formato)
    for ln in pars:
        p = doc.add_paragraph()
        if ln is None:
            continue
        if ln.get("alin") in alinear:
            p.alignment = alinear[ln["alin"]]
        if ln.get("runs"):          # formato elegido a mano en la vista previa
            for x in ln["runs"]:
                r = p.add_run(x["t"])
                r.bold = True if x["b"] else None
                r.italic = True if x["i"] else None
                r.underline = True if x["u"] else None
                if x["c"]:
                    r.font.color.rgb = RGBColor.from_string(x["c"][1:].upper())
            continue
        negrita = ln["negrita"]
        segs = ln["segs"]
        for t, tipo, _ in segs:
            if not t:
                continue
            r = p.add_run(t.rstrip() if (t, tipo) == (segs[-1][0], segs[-1][1]) else t)
            if negrita:
                r.bold = True
            if tipo:
                r.font.highlight_color = color[tipo]
            elif ln["linea"]:
                r.font.highlight_color = color[ln["linea"]]
    try:
        doc.save(destino)
    except PermissionError:  # el archivo esta abierto en Word
        destino = destino.with_name(destino.stem + time.strftime("_%H%M%S") + ".docx")
        doc.save(destino)
    return destino


# ------------------------------------------------------- pagina de revision
def escribir_revision(nombre, audio, dictado, palabras, marcado, destino):
    rel = os.path.relpath(audio, destino.parent).replace("\\", "/")
    pal = "".join(
        f'<span class="w{" baja" if w["conf"] < 0.5 else (" media" if w["conf"] < 0.8 else "")}" '
        f'onclick="ir({w["ini"]})" title="{w["ini"]:.1f}s">{html.escape(w["p"])}</span>' for w in palabras)
    doc = f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Revisión {html.escape(nombre)}</title>
<style>
:root{{--bg:#f6f6f4;--card:#fff;--tx:#1d1d1b;--mu:#6b6b66;--bd:#e3e2dd;--amarillo:#fbe7a6;--rojo:#f8c9c4;
--naranja:#2aa6a6;--naranja-bg:#e2f5f5;--gris:#b9b8b2}}
@media(prefers-color-scheme:dark){{:root{{--bg:#161615;--card:#20201f;--tx:#ecebe6;--mu:#a3a29c;--bd:#34332f;
--amarillo:#5c4d1a;--rojo:#6b2a25;--naranja:#4fc4c4;--naranja-bg:#173535;--gris:#5a5954}}}}
body{{margin:0;background:var(--bg);color:var(--tx);font:15px/1.55 system-ui,Segoe UI,sans-serif;padding:20px 16px}}
main{{max-width:1200px;margin:auto}}h1{{font-size:20px;margin:0 0 8px}}
audio{{width:100%;position:sticky;top:0;z-index:2;background:var(--bg);padding:6px 0}}
.cols{{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-top:8px}}@media(max-width:800px){{.cols{{grid-template-columns:1fr}}}}
.box{{background:var(--card);border:1px solid var(--bd);border-radius:10px;padding:12px 14px}}
.box h2{{font-size:12px;text-transform:uppercase;letter-spacing:.05em;color:var(--mu);margin:0 0 8px}}
.w{{cursor:pointer;border-radius:3px}}.w:hover{{outline:1px solid var(--mu)}}.baja{{background:var(--rojo)}}.media{{background:var(--amarillo)}}
.mu{{color:var(--mu);font-size:13px}}
{N.CSS_MARCAS}
</style><script>function ir(t){{var a=document.getElementById('au');a.currentTime=Math.max(0,t-0.5);a.play();}}</script>
</head><body><main><h1>{html.escape(nombre)}</h1>
<audio id="au" controls src="{html.escape(rel)}"></audio>
<p class="mu">Clic en una marca o en una palabra del dictado para escuchar ese momento.
Rojo: dato no dictado o a completar · Amarillo: dudoso · Gris: frase de plantilla no dictada · Turquesa: línea no encontrada en el dictado.</p>
<div class="cols"><div class="box"><h2>Informe</h2>{N.a_html(marcado, palabras)}</div>
<div class="box"><h2>Dictado (Whisper)</h2>{pal}</div></div></main></body></html>"""
    destino.write_text(doc, encoding="utf-8")


# ------------------------------------------------------------------- main
def main():
    cfg = config()
    audios = juntar_audios(sys.argv[1:], cfg)
    if not audios:
        print(f"No hay audios. Arrastrá audios sobre informe.bat o dejalos en:\n  {cfg['carpeta_audios_nuevos']}")
        return
    sal = cfg["carpeta_informes"]
    (sal / "revision").mkdir(parents=True, exist_ok=True)
    (sal / "revision" / "datos").mkdir(exist_ok=True)

    try:  # primero aprender de los Word ya revisados
        from aprender import aprender
        aprender(cfg, silencioso=True)
    except Exception as ex:
        print("(no se pudo aprender de los informes revisados:", ex, ")")

    if N.ollama_modelos() is None:
        print("[ERROR] Ollama no está abierto. Abrí Ollama y volvé a intentar.")
        sys.exit(1)

    # 1) Whisper (primero se libera la placa de video)
    N.liberar_ia(cfg["modelo_ia"])
    t0 = time.time()
    modelo = cargar_modelo(cfg["modelo_whisper"], "cuda")
    trans = {}
    for k, a in enumerate(audios, 1):
        print(f"[{k}/{len(audios)}] Transcribiendo {a.name} ({duracion(a):.0f}s)...", flush=True)
        from fase1_transcribir import leer_vocabulario, cargar_audio, VOCAB_DEF
        import huecos as H
        prompt = leer_vocabulario(VOCAB_DEF)
        t = transcribir(modelo, a, prompt)
        pal, pend = H.reparar(modelo, cargar_audio(a), t["palabras"], prompt)
        trans[a] = {"texto": H.texto_de(pal), "palabras": pal, "huecos": pend}
        (sal / "revision" / "datos" / (a.stem + ".json")).write_text(
            json.dumps(trans[a], ensure_ascii=False, indent=1), encoding="utf-8")
    del modelo
    gc.collect()

    # 2) IA local -> informe
    banco = N.cargar_banco()
    hechos = []
    for k, a in enumerate(audios, 1):
        dic, pal = trans[a]["texto"], trans[a]["palabras"]
        print(f"[{k}/{len(audios)}] Armando informe de {a.name}...", end=" ", flush=True)
        ej = N.elegir_ejemplos(dic, banco, k=cfg["ejemplos_por_informe"], excluir=a.stem)
        salida, seg, _, _ = N.llamar_ia(cfg["modelo_ia"], N.armar_mensajes(dic, ej))
        marcado = N.marcar(salida, dic, pal)
        om = N.omisiones(dic, salida, pal)
        om += [{"dato": f"posible parte no transcrita {h['ini']:.0f}-{h['fin']:.0f}s", "seg": None}
               for h in trans[a].get("huecos", [])]
        if om:
            txt = "[REVISAR: dictado pero no incluido en el informe: " + ", ".join(
                o["dato"] + (f" (seg {o['seg']:.0f})" if o["seg"] is not None else "") for o in om) + "]"
            marcado += [{"segs": [("", None, None)], "linea": None, "titulo": False},
                        {"segs": [(txt, "completar", "Datos dictados que no aparecen en el informe")],
                         "linea": None, "titulo": False}]
        nombre = a.stem
        docx = escribir_docx(marcado, sal / f"{nombre}.docx", cfg)
        escribir_revision(nombre, a, dic, pal, marcado, sal / "revision" / f"{nombre}.html")
        (sal / "revision" / "datos" / (nombre + ".informe_ia.txt")).write_text(salida, encoding="utf-8")
        (sal / "revision" / "datos" / (nombre + ".dictado.txt")).write_text(dic, encoding="utf-8")
        (sal / "revision" / "datos" / (nombre + ".audio.txt")).write_text(str(a.resolve()), encoding="utf-8")
        c = N.contar_marcas(marcado)
        rojas = c.get("numero", 0) + c.get("completar", 0)
        print(f"{seg:.0f}s · marcas: {rojas} rojas, {c.get('dudoso',0)+c.get('bajaconf',0)} amarillas, "
              f"{c.get('verificar',0)} turquesa, {c.get('plantilla',0)} grises")
        hechos.append(docx)

    print(f"\nListo: {len(hechos)} informe(s) en {sal}  ({time.time()-t0:.0f}s en total)")
    if cfg["abrir_word_al_terminar"] and os.name == "nt":
        if len(hechos) <= 3:
            for d in hechos:
                os.startfile(d)
        else:
            os.startfile(sal)


if __name__ == "__main__":
    main()
