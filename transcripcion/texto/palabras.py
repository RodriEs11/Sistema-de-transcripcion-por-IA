"""Palabras normalizadas de un texto (sin acentos, minúsculas, de 4 letras o más) para comparar textos.

Viene de nucleo.py (docs/refactor.md, etapa 3).
"""
import re
from fase1_transcribir import sin_acentos


def palabras_norm(t):
    return re.findall(r"[a-z]{4,}", sin_acentos(t.lower()))
