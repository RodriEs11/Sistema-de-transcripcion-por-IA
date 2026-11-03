"""Controles clínicos extra: Bi-Rads y ACR distintos de lo dictado, y términos clave (sólida/quística, lado,
márgenes…) que no se dictaron junto a ese hallazgo.

Viene de nucleo.py (docs/refactor.md, etapa 3).
"""
import difflib
import re
from transcripcion.texto.normalizacion import sin_acentos


# ------------------------------------------------- controles clinicos extra
# Terminos que cambian el sentido clinico: si la IA los escribe tienen que haberse
# dictado CERCA del hallazgo (alrededor de sus medidas / hora / nivel).
TERMINOS_CLAVE = ("solid", "quist", "liquid", "ovalad", "redond", "irregular", "circunscrip", "espicul",
                  "lobulad", "anecoic", "hiperecog", "isoecog", "hipoecog", "calcific", "sombra",
                  "vasculariz", "sospech", "benign", "mioma", "intramural", "subseros", "submucos",
                  "derech", "izquierd", "bilateral", "denso", "densa", "asimetr", "persist", "estable",
                  "sin cambios", "periareolar", "periferic")


# como suele deformar Whisper algunos terminos ("impecogénica", "el otro" = el otro ovario)
VARIANTES_WHISPER = {"hipoecog": ("cogenic", "ecogen"), "periareolar": ("perio", "areol"),
                     "izquierd": ("otro",), "derech": ("otro",)}


MOTIVO_CONTEXTO = "No se dictó junto a este hallazgo: verificar que corresponda"


def _bi_rads_dictados(nd):
    nd = re.sub(r"\bbirr?astre\w*", "birads 3", nd)          # "un birrastre" = Bi-Rads 3
    pat = r"(?:bi\W?rr?ads?\w*|vrads?\w*|birra\w*|ponemos un|poner un|ponemos|es un)\W{0,3}(\d)\b"
    return set(re.findall(pat, nd))


def _acr_dictados(nd):
    return set(re.findall(r"\b(?:acr|acdr|acrd?|crd?|r)\W{0,3}([abcd])\b", nd)) | \
        set(re.findall(r"\bacr([abcd])\b", nd))


def partir(segs, patron, tipo, motivo, filtro=lambda m: True):
    """Marca dentro de los segmentos sin marca las coincidencias de 'patron'.
    'motivo' puede ser un texto o una funcion que recibe la coincidencia."""
    out = []
    for t, tp, mot in segs:
        if tp:
            out.append((t, tp, mot)); continue
        pos = 0
        for m in re.finditer(patron, t, flags=re.I):
            if not filtro(m):
                continue
            g = m.span(1) if m.groups() else m.span()
            if pos < g[0]:
                out.append((t[pos:g[0]], None, None))
            out.append((t[g[0]:g[1]], tipo, motivo(m) if callable(motivo) else motivo))
            pos = g[1]
        if pos < len(t):
            out.append((t[pos:], None, None))
    return out


# familias de terminos: si el informe dice "quístico" y cerca se dicto "sólido", se muestra "sólido"
FAMILIAS = (("solid", "quist", "liquid", "anecoic", "mixt"),
            ("anecoic", "hiperecog", "isoecog", "hipoecog", "heterog"),
            ("ovalad", "redond", "irregular", "lobulad"),
            ("circunscrip", "espicul", "irregular", "lobulad", "microlobul"),
            ("derech", "izquierd", "bilateral"),
            ("intramural", "subseros", "submucos"),
            ("benign", "sospech"),
            ("persist", "estable", "sin cambios", "nuev"))


def _y(xs):
    xs = list(xs)
    return xs[0] if len(xs) == 1 else ", ".join(xs[:-1]) + " y " + xs[-1]


def controles_clinicos(salida, nd, formas=None):
    formas = formas or {}
    toks = nd.split()
    birads = _bi_rads_dictados(nd)
    acr = _acr_dictados(nd)
    for ln in salida:
        texto = "".join(t for t, _, _ in ln["segs"])
        low = sin_acentos(texto.lower())
        # Bi-Rads: el numero tiene que estar dictado como Bi-Rads ("le ponemos un 3", "birads 3")
        if "bi-rads" in low or "birads" in low:
            dict_br = ("Dictado: Bi-Rads " + _y(sorted(birads))) if birads else \
                "No encontré un Bi-Rads en el dictado (suele estar al final)"
            nuevos = []
            for t, tp, mot in ln["segs"]:
                if re.fullmatch(r"\d", t.strip()) and t.strip() not in birads:
                    nuevos.append((t, "numero", (dict_br + f" / Informe: Bi-Rads {t.strip()}") if birads
                                   else dict_br + f" · Informe: Bi-Rads {t.strip()}"))
                elif re.fullmatch(r"\d", t.strip()) and tp == "numero":
                    nuevos.append((t, None, None))      # dictado como Bi-Rads ("un birrastre" = 3)
                else:
                    nuevos.append((t, tp, mot))
            ln["segs"] = nuevos
        # ACR: la letra tiene que estar dictada
        if re.search(r"\bacr\b", low):
            dict_acr = ("Dictado: ACR " + _y(sorted(x.upper() for x in acr))) if acr else \
                "No encontré la categoría ACR en el dictado"
            ln["segs"] = partir(ln["segs"], r"\bACR:?\s*([ABCD])\b", "numero",
                                 lambda m: dict_acr + (" / " if acr else " · ") + f"Informe: ACR {m.group(1)}",
                                 lambda m: m.group(1).lower() not in acr)
        # descripciones decisivas cerca de las medidas del hallazgo
        if not texto.startswith("-"):
            continue
        anclas = [t.strip().lower().replace(",", ".") for t, tp, _ in ln["segs"]
                  if tp in (None, "bajaconf") and re.fullmatch(r"\s*(\d+(?:[.,]\d+)?|[HhCcDdLl]\d{1,2})\s*", t)]
        anclas = [a.replace("-", "") for a in anclas]
        idx = [i for i, w in enumerate(toks) if w.strip(".,;:") in anclas]
        if not idx:
            continue
        orden = []
        for i in idx:
            orden += [re.sub(r"[^a-z]", "", w) for w in toks[max(0, i - 30): i + 25]]
        orden = [w for w in dict.fromkeys(orden) if w]
        ventana = set(orden)

        def falta(m):
            w = sin_acentos(m.group(0).lower())
            raiz = next((r for r in TERMINOS_CLAVE if w.startswith(r)), None)
            if not raiz:
                return False
            if any(v.startswith(raiz) for v in ventana):
                return False
            if any(x in v for x in VARIANTES_WHISPER.get(raiz, ()) for v in ventana):
                return False
            return not difflib.get_close_matches(w, list(ventana), n=1, cutoff=0.7)

        def motivo(m):
            w = sin_acentos(m.group(0).lower())
            raiz = next((r for r in TERMINOS_CLAVE if w.startswith(r)), "")
            fam = {r for f in FAMILIAS if raiz in f for r in f} - {raiz}
            otros = [formas.get(v, v) for v in orden if any(v.startswith(r) for r in fam)]
            txt = f"Informe: «{m.group(0)}» · no se dictó junto a este hallazgo"
            if otros:
                txt += ". Cerca se dictó: " + ", ".join(dict.fromkeys(otros[:4]))
            return txt + ". Verificá que corresponda"
        ln["segs"] = partir(ln["segs"], r"[A-Za-zÁÉÍÓÚáéíóúñÑüÜ]{5,}", "verificar", motivo, falta)
