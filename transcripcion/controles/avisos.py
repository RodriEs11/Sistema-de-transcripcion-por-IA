"""Avisos de arriba del informe: datos dictados que no quedaron en el informe y estudios sin plantilla.

Viene de nucleo.py (docs/refactor.md, etapa 3).
"""

import re

from transcripcion.conocimiento import plantillas as PL
from transcripcion.controles import marcas as MAR
from transcripcion.informe import formato as FMT
from transcripcion.texto.normalizacion import datos_criticos, sin_acentos


def estudios_sin_plantilla(informe):
    """Titulos del informe que no corresponden a ninguna plantilla conocida."""
    conocidos = PL.titulos_conocidos()
    ls = [linea.strip() for linea in MAR.texto_limpio(informe).splitlines()]
    out = []
    for i, linea in enumerate(ls):
        low = sin_acentos(linea.lower())
        if (
            not linea
            or linea.startswith("-")
            or linea.endswith((".", ":"))
            or low.startswith(MAR.LINEAS_FIJAS + ("categorizacion", "nota"))
        ):
            continue
        if PL.es_linea_fija(linea) or linea.rstrip(":") in FMT.NEGRITA_EXACTAS:
            continue  # texto fijo o subtitulo (Tórax / Abdomen / Pelvis)
        rodeada = (i == 0 or not ls[i - 1]) and (i + 1 >= len(ls) or not ls[i + 1])
        if not (PL.es_titulo(linea) or rodeada):
            continue
        clave = PL.clave_titulo(linea)
        if not clave or (
            low.startswith("rx ") and "rx osteoarticular" in " ".join(n.lower() for n, _ in PL.todas_las_secciones())
        ):
            continue  # cualquier RX de una region usa la plantilla osteoarticular
        if low.startswith("tc ") and any(
            n.lower().startswith("tc osteo") or "texto común" in n.lower() for n, _ in PL.todas_las_secciones()
        ):
            continue  # cualquier TC usa el texto comun de tomografia
        if not any(
            clave == k
            or clave.split()[0] == k.split()[0]
            and (len(clave.split()) == 1 or len(k.split()) == 1 or clave.split()[1][:4] == k.split()[1][:4])
            for k in conocidos
        ):
            out.append(linea)
    return out


# ------------------------------------------------------------- omisiones
def omisiones(dictado, informe, palabras=None):
    """Datos dictados (medidas, numeros, H12, L5-S1...) que no aparecen en el informe."""
    crudos = set(re.findall(r"\d+", dictado))
    dic = {
        x for x in datos_criticos(dictado) if not (x.isdigit() and int(x) <= 2 and x not in crudos)
    }  # "dos puntos", "un"
    faltan = sorted(
        dic - datos_criticos(MAR.texto_limpio(informe), True),
        key=lambda x: (MAR.buscar_tiempo(x, palabras) or 0) if palabras else 0,
    )
    out = []
    for x in faltan:
        etiqueta = x.upper() if x[0].isalpha() else x
        etiqueta = re.sub(r"^([CDLS]\d+)([CDLS]\d+)$", r"\1-\2", etiqueta)
        out.append({"dato": etiqueta, "seg": MAR.buscar_tiempo(x, palabras) if palabras else None})
    return out
