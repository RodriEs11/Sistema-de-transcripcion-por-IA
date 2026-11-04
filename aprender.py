# -*- coding: utf-8 -*-
"""Lanzador de consola: `python aprender.py` guarda como ejemplos los Word ya revisados y muestra el resumen.
El código está en transcripcion/aprendizaje/aprender.py (docs/refactor.md, etapa 6b)."""

if __name__ == "__main__":
    import sys

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")   # acentos en la consola de Windows
    except Exception:
        pass
    from informe import config
    from transcripcion.aprendizaje.aprender import aprender, resumen
    from transcripcion.conocimiento import archivos as CON

    cfg = config()
    CON.preparar_conocimiento()
    aprender(cfg)
    resumen()
