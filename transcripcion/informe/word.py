"""Word del informe (python-docx): hoja y márgenes, párrafos con su formato, formato manual de la vista previa y
escritura atómica del .docx. Lo usan el servidor (Guardar Word, vista previa) y el modo consola.

Viene de informe.py (docs/refactor.md, etapa 6a).
"""

import re
import time

from transcripcion.informe import formato as FMT

# ------------------------------------------------------------------- Word
COLORES = None


PAGINA_DEF = {
    "nombre": "A4",
    "ancho_cm": 21.0,
    "alto_cm": 29.7,
    "margen_superior_cm": 2.5,
    "margen_inferior_cm": 4.0,
    "margen_izquierdo_cm": 1.3,
    "margen_derecho_cm": 3.0,
}


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
        if vacia and not lineas:
            continue
        lineas.append(None if vacia else ln)
    while lineas and lineas[-1] is None:
        lineas.pop()
    if not cfg["linea_vacia_entre_titulo_y_texto"]:
        lineas = [
            x
            for i, x in enumerate(lineas)
            if not (x is None and i > 0 and lineas[i - 1] is not None and lineas[i - 1]["titulo"])
        ]
    out = []
    for ln in lineas:
        if ln is None:
            out.append(None)
            continue
        segs = ln["segs"]
        segs = [(segs[0][0].lstrip(), *segs[0][1:])] + list(segs[1:]) if segs else segs
        alin = "center" if ln["titulo"] and cfg.get("centrar_titulos", True) else ""
        out.append(
            {
                "segs": segs,
                "linea": ln["linea"],
                "alin": alin,
                "alin_def": alin,
                "negrita": FMT.debe_ir_en_negrita("".join(t for t, _, _ in ln["segs"]), ln["titulo"], cfg),
            }
        )
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
        k = next(
            (
                i
                for i in list(range(desde, len(lista))) + list(range(0, desde))
                if i not in usados and lista[i]["t"] == t
            ),
            None,
        )
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
            h = r.get("h") or ""
            fuente = r.get("f") or ""
            tamano = r.get("s")
            runs.append(
                {
                    "t": r["t"],
                    "b": bool(r.get("b")),
                    "i": bool(r.get("i")),
                    "u": bool(r.get("u")),
                    "x": bool(r.get("x")),
                    "c": c if isinstance(c, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", c) else "",
                    "h": h if isinstance(h, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", h) else "",
                    "f": fuente if isinstance(fuente, str) and re.fullmatch(r"[\w .-]{1,80}", fuente) else "",
                    "s": float(tamano)
                    if isinstance(tamano, (float, int)) and not isinstance(tamano, bool) and 6 <= tamano <= 96
                    else None,
                }
            )
        if runs and "".join(r["t"] for r in runs) == t:
            p["runs"] = runs
    return pars


def escribir_docx(marcado, destino, cfg, formato=None):
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH as A
    from docx.enum.text import WD_COLOR_INDEX as C
    from docx.oxml.ns import qn
    from docx.shared import Cm, Pt, RGBColor

    color = {
        "numero": C.RED,
        "completar": C.RED,
        "dudoso": C.YELLOW,
        "bajaconf": C.YELLOW,
        "plantilla": C.GRAY_25,
        "verificar": C.TURQUOISE,
    }

    doc = Document()
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
        if ln.get("runs"):  # formato elegido a mano en la vista previa
            for x in ln["runs"]:
                r = p.add_run(x["t"])
                r.bold = True if x["b"] else None
                r.italic = True if x["i"] else None
                r.underline = True if x["u"] else None
                r.font.strike = True if x.get("x") else None
                if x.get("f"):
                    r.font.name = x["f"]
                    for att in ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia"):
                        r._element.get_or_add_rPr().get_or_add_rFonts().set(qn(att), x["f"])
                if x.get("s"):
                    r.font.size = Pt(x["s"])
                if x.get("h"):
                    from docx.oxml import OxmlElement

                    fondo = OxmlElement("w:shd")
                    fondo.set(qn("w:fill"), x["h"][1:].upper())
                    r._element.get_or_add_rPr().append(fondo)
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
