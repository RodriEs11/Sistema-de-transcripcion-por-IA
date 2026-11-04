"""Orden estándar de los estudios de mama, ginecología y tiroides, aunque se dicten en otro orden.

Viene de nucleo.py (docs/refactor.md, etapa 3).
"""

from transcripcion.texto.normalizacion import sin_acentos
from transcripcion.conocimiento import plantillas as PL


# ---------------------------------------------------- orden de los estudios
ORDEN_MAMA = (("mamograf", 0), ("ecografia mamaria", 1), ("ginecolog", 3), ("transvaginal", 3), ("tiroid", 4))


def _rango(titulo):
    low = sin_acentos(titulo.lower())
    for clave, r in ORDEN_MAMA:
        if clave in low:
            return r
    return None


def ordenar_estudios(texto):
    """Ordena Mamografía -> Ecografía Mamaria -> Categorización -> Transvaginal -> Tiroides,
    aunque el médico (y la IA) los dicten en otro orden. Otros estudios no se tocan."""
    ls = texto.replace("\r", "").split("\n")
    cierre = []
    while ls and (not ls[-1].strip() or sin_acentos(ls[-1].strip().lower()).startswith("lo salud")):
        cierre.insert(0, ls.pop())
    bloques, pre, cat = [], [], None
    for l in ls:
        if sin_acentos(l.strip().lower()).startswith("categorizacion"):
            cat = l.strip()
            continue
        if PL.es_titulo(l):
            bloques.append([l])
        elif bloques:
            bloques[-1].append(l)
        else:
            pre.append(l)
    rangos = [_rango(b[0]) for b in bloques]
    if len(bloques) < 2 or None in rangos or rangos == sorted(rangos) and cat is None:
        return texto  # nada que ordenar (o no son estudios mamarios)
    orden = sorted(range(len(bloques)), key=lambda i: (rangos[i], i))
    out = list(pre)
    puesto = cat is None
    destino = max((i for i in orden if rangos[i] in (0, 1)), key=lambda i: rangos[i], default=None)
    for i in orden:
        b = list(bloques[i])
        while b and not b[-1].strip():
            b.pop()
        out += b + [""]
        if not puesto and i == destino:
            out += [cat, ""]
            puesto = True
    if not puesto:
        out += [cat, ""]
    while out and not out[-1].strip():
        out.pop()
    return "\n".join(out + ([""] + [c for c in cierre if c.strip()] if cierre else []))
