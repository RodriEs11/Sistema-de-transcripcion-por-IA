# -*- coding: utf-8 -*-
"""
Importa informes ya terminados en Word (sin audio) como INFORMES DE REFERENCIA.
La IA los usa para copiar el formato y las frases de ese tipo de estudio
(TC, PET, ecografía abdominal...) cuando no hay ejemplos con audio.

  Carpeta de origen: Dataset\\Informes word   (o la que se pase como argumento)
  Destino:           sistema\\referencias\\NOMBRE.txt
"""
import re
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
ORIGEN = AQUI.parent / "Dataset" / "Informes word"
DESTINO = AQUI / "referencias"

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def texto_docx(ruta):
    from docx import Document
    d = Document(str(ruta))
    lineas = [p.text.replace("​", "").replace("\xa0", " ").rstrip() for p in d.paragraphs]
    t = "\n".join(lineas)
    t = re.sub(r"\n{3,}", "\n\n", t).strip()
    return t


def importar(origen=ORIGEN):
    origen = Path(origen)
    DESTINO.mkdir(exist_ok=True)
    ok, mal = [], []
    for f in sorted(origen.glob("*.docx")):
        if f.name.startswith("~$"):
            continue
        try:
            t = texto_docx(f)
        except Exception:
            mal.append(f.name); continue
        if len(t) < 40:
            mal.append(f.name); continue
        (DESTINO / (f.stem + ".txt")).write_text(t + "\n", encoding="utf-8")
        ok.append(f.name)
    return ok, mal


if __name__ == "__main__":
    ok, mal = importar(sys.argv[1] if len(sys.argv) > 1 else ORIGEN)
    print(f"Importados {len(ok)} informes a {DESTINO}")
    if mal:
        print("No se pudieron leer (vacíos o dañados):", ", ".join(mal))


def plantilla_desde_word(ruta_o_bytes):
    """Convierte una plantilla de Word (.docx) en una seccion de plantillas.md para revisar."""
    import io
    from docx import Document
    d = Document(io.BytesIO(ruta_o_bytes) if isinstance(ruta_o_bytes, (bytes, bytearray)) else str(ruta_o_bytes))
    ls = [p.text.replace("\u200b", "").replace("\xa0", " ").strip() for p in d.paragraphs]
    ls = [l for l in ls]
    while ls and not ls[0]:
        ls.pop(0)
    if not ls:
        raise ValueError("El Word está vacío")
    titulo = ls[0]
    fijo, vinetas, despues = [], [], []
    for l in ls[1:]:
        if re.match(r"(?i)^lo saluda", l):
            break
        if not l:
            continue
        if l.startswith("-"):
            vinetas.append(l)
        elif not vinetas:
            fijo.append(l)
        elif len(l) < 30 and not l.endswith("."):
            vinetas.append(l)                       # subtitulo (ej. "Tórax")
        else:
            despues.append(l)

    def huecos(t):
        t = t.replace("@", "<dato>")
        t = re.sub(r"(?i)(:|\bde|\bmide)\s+(mm|cc|g)\b", r"\1 <N>\2", t)
        t = re.sub(r"(?i)(bi-?rads:?)\s*\.", r"\1 <N>.", t)
        t = re.sub(r"(?i)(ACR:)\s*\.", r"\1 <letra>.", t)
        return t

    partes = [f"TITULO: {titulo}"]
    if fijo:
        partes += ["TEXTO FIJO:"] + [huecos(x) for x in fijo]
    partes += ["PROTOCOLO NORMAL:"] + ([huecos(x) for x in vinetas] or ["-"])
    if despues:
        partes += ["CIERRE / OTRAS LÍNEAS:"] + [huecos(x) for x in despues]
    nombre = re.sub(r"\(.*?\)", "", titulo).strip().upper()
    return {"nombre": nombre, "cuerpo": "\n".join(partes)}
