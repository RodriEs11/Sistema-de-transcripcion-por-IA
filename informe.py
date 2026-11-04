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
import sys
import time
from pathlib import Path

from transcripcion import ajustes
from transcripcion.casos.repositorio import EXT_AUDIO
from transcripcion.conocimiento import archivos as CON
from transcripcion.controles import avisos as AV
from transcripcion.controles import marcas as MAR
from transcripcion.ia import ejemplos as EJEM
from transcripcion.ia import ollama as OLL
from transcripcion.ia import prompt as PR
from transcripcion.base import plataforma as P
from transcripcion.asr.whisper import cargar_modelo, transcribir, duracion
from transcripcion.informe.word import escribir_docx

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

AQUI = Path(__file__).resolve().parent


def config():
    """configuracion.json (la crea desde el ejemplo la primera vez). Ver ajustes.leer_config."""
    return ajustes.leer_config(AQUI)


def juntar_audios(args, cfg):
    rutas = []
    for a in args or [str(cfg["carpeta_audios_nuevos"])]:
        p = Path(a)
        if p.is_dir():
            rutas += sorted(x for x in p.iterdir() if x.suffix.lower() in EXT_AUDIO)
        elif p.suffix.lower() in EXT_AUDIO and p.exists():
            rutas.append(p)
    return rutas


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
{MAR.CSS_MARCAS}
</style><script>function ir(t){{var a=document.getElementById('au');a.currentTime=Math.max(0,t-0.5);a.play();}}</script>
</head><body><main><h1>{html.escape(nombre)}</h1>
<audio id="au" controls src="{html.escape(rel)}"></audio>
<p class="mu">Clic en una marca o en una palabra del dictado para escuchar ese momento.
Rojo: dato no dictado o a completar · Amarillo: dudoso · Gris: frase de plantilla no dictada · Turquesa: línea no encontrada en el dictado.</p>
<div class="cols"><div class="box"><h2>Informe</h2>{MAR.a_html(marcado, palabras)}</div>
<div class="box"><h2>Dictado (Whisper)</h2>{pal}</div></div></main></body></html>"""
    destino.write_text(doc, encoding="utf-8")


# ------------------------------------------------------------------- main
def main():
    cfg = config()
    CON.preparar_conocimiento()
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

    if OLL.ollama_modelos() is None:
        print("[ERROR] Ollama no está abierto. Abrí Ollama y volvé a intentar.")
        sys.exit(1)

    # 1) Whisper (primero se libera la placa de video)
    OLL.liberar_ia(cfg["modelo_ia"])
    t0 = time.time()
    modelo = cargar_modelo(cfg["modelo_whisper"], cfg.get("dispositivo_whisper", "cuda"))
    trans = {}
    for k, a in enumerate(audios, 1):
        print(f"[{k}/{len(audios)}] Transcribiendo {a.name} ({duracion(a):.0f}s)...", flush=True)
        from transcripcion.asr.whisper import leer_vocabulario, cargar_audio, VOCAB_DEF
        from transcripcion.asr import huecos as H
        prompt = leer_vocabulario(VOCAB_DEF)
        t = transcribir(modelo, a, prompt)
        pal, pend = H.reparar(modelo, cargar_audio(a), t["palabras"], prompt)
        trans[a] = {"texto": H.texto_de(pal), "palabras": pal, "huecos": pend}
        (sal / "revision" / "datos" / (a.stem + ".json")).write_text(
            json.dumps(trans[a], ensure_ascii=False, indent=1), encoding="utf-8")
    del modelo
    gc.collect()

    # 2) IA local -> informe
    banco = EJEM.cargar_banco()
    hechos = []
    for k, a in enumerate(audios, 1):
        dic, pal = trans[a]["texto"], trans[a]["palabras"]
        print(f"[{k}/{len(audios)}] Armando informe de {a.name}...", end=" ", flush=True)
        ej = EJEM.elegir_ejemplos(dic, banco, k=cfg["ejemplos_por_informe"], excluir=a.stem)
        salida, seg, _, _ = OLL.llamar_ia(cfg["modelo_ia"], PR.armar_mensajes(dic, ej))
        marcado = MAR.marcar(salida, dic, pal)
        om = AV.omisiones(dic, salida, pal)
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
        c = MAR.contar_marcas(marcado)
        rojas = c.get("numero", 0) + c.get("completar", 0)
        print(f"{seg:.0f}s · marcas: {rojas} rojas, {c.get('dudoso',0)+c.get('bajaconf',0)} amarillas, "
              f"{c.get('verificar',0)} turquesa, {c.get('plantilla',0)} grises")
        hechos.append(docx)

    print(f"\nListo: {len(hechos)} informe(s) en {sal}  ({time.time()-t0:.0f}s en total)")
    if cfg["abrir_word_al_terminar"] and P.puede_abrir():
        try:
            if len(hechos) <= 3:
                for d in hechos:
                    P.abrir(d)
            else:
                P.abrir(sal)
        except OSError:
            pass


if __name__ == "__main__":
    main()
