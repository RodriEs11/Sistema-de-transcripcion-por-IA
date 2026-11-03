"""Normalización del texto dictado para comparar con el informe: números en palabras a cifras ("veintitrés" -> 23),
horas ("hora 11" -> h11), niveles vertebrales ("L5, S1" -> l5s1), sin acentos; y los datos críticos (números,
horas, niveles) de un texto.

Viene de fase1_transcribir.py (docs/refactor.md, etapa 4).
"""
import re
import unicodedata


# ----------------------------------------------------------- normalizacion texto
def sin_acentos(t):
    return "".join(c for c in unicodedata.normalize("NFD", t)
                   if unicodedata.category(c) != "Mn")


UNIDADES = {
    "cero": 0, "uno": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5,
    "seis": 6, "siete": 7, "ocho": 8, "nueve": 9, "diez": 10, "once": 11,
    "doce": 12, "trece": 13, "catorce": 14, "quince": 15, "dieciseis": 16,
    "diecisiete": 17, "dieciocho": 18, "diecinueve": 19, "veinte": 20,
    "veintiun": 21, "veintiuno": 21, "veintiuna": 21, "veintidos": 22,
    "veintitres": 23, "veinticuatro": 24, "veinticinco": 25,
    "veintiseis": 26, "veintisiete": 27, "veintiocho": 28, "veintinueve": 29,
}


DECENAS = {"treinta": 30, "cuarenta": 40, "cincuenta": 50, "sesenta": 60,
           "setenta": 70, "ochenta": 80, "noventa": 90}


CENTENAS = {"cien": 100, "ciento": 100, "doscientos": 200, "trescientos": 300,
            "cuatrocientos": 400, "quinientos": 500, "seiscientos": 600,
            "setecientos": 700, "ochocientos": 800, "novecientos": 900}


def es_num(p):
    return p in UNIDADES or p in DECENAS or p in CENTENAS or p == "mil"


def palabras_a_numeros(texto):
    """'veintitres por cuatro coma cinco' -> '23 por 4.5'"""
    toks = re.findall(r"[a-z0-9]+(?:[.,][0-9]+)?|[^a-z0-9\s]", texto)
    out, i = [], 0
    while i < len(toks):
        if not es_num(toks[i]):
            out.append(toks[i]); i += 1; continue
        total = actual = 0
        ult = None
        while i < len(toks):
            p = toks[i]
            if p in CENTENAS:
                actual += CENTENAS[p]
            elif p in DECENAS:
                actual += DECENAS[p]
            elif p in UNIDADES:
                if ult == "unidad":
                    break
                actual += UNIDADES[p]; ult = "unidad"; i += 1; continue
            elif p == "mil":
                total += (actual or 1) * 1000; actual = 0
            elif (p == "y" and ult == "decena" and i + 1 < len(toks)
                  and toks[i + 1] in UNIDADES):
                i += 1; continue
            else:
                break
            ult = "decena" if p in DECENAS else "otro"
            i += 1
        out.append(str(total + actual))
        # decimales: "coma" / "punto" seguido de numero
        if (i + 1 < len(toks) and toks[i] in ("coma", "punto")
                and toks[i + 1] in UNIDADES):
            out[-1] += "." + str(UNIDADES[toks[i + 1]]); i += 2
    return " ".join(out)


def normalizar(texto):
    t = sin_acentos(texto.lower())
    t = palabras_a_numeros(t)
    t = re.sub(r"(\d),(\d)", r"\1.\2", t)
    t = re.sub(r"(\d)\s*[x×]\s*(?=\d)", r"\1 x ", t)   # "29x17" -> "29 x 17"
    # letras dictadas: "hache 12" -> "h 12", "ele 5 ese 1" -> "l 5 s 1"
    t = re.sub(r"\b(hache|ele|ese|ce|hora|horas|nora)\s+(?=\d)",
               lambda m: {"hache": "h", "ele": "l", "ese": "s", "ce": "c", "hora": "h", "horas": "h",
                          "nora": "h"}[m.group(1)] + " ", t)
    # "h 12" -> "h12", "l5 - s1" -> "l5s1"
    t = re.sub(r"\b([hcdlst])\s*(\d{1,2})\b", r"\1\2", t)
    t = re.sub(r"\b([cdls]\d{1,2})\s*[-,]?\s*([cdls]\d{1,2})\b", r"\1\2", t)
    return t


def datos_criticos(texto, es_informe=False):
    """Medidas, numeros y codigos (H12, L5-S1, C3...) de un texto."""
    if es_informe:  # se ignora el parrafo tecnico fijo de la mamografia
        texto = "\n".join(l for l in texto.splitlines()
                          if not l.strip().lower().startswith("hemos obtenido"))
    t = normalizar(texto)
    codigos = set(re.findall(r"\b[hcdlst]\d{1,2}(?:[cdls]\d{1,2})?\b", t))
    nums = set(re.findall(r"(?<![a-z0-9.])\d+(?:\.\d+)?", t))
    return codigos | nums
