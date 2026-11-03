# -*- coding: utf-8 -*-
"""Lanzador de consola: `python aprender.py` guarda como ejemplos los Word ya revisados y muestra el resumen.
El código está en transcripcion/aprendizaje/aprender.py (docs/refactor.md, etapa 6b)."""

if __name__ == "__main__":
    from informe import config
    from transcripcion.aprendizaje.aprender import aprender, resumen
    from transcripcion.conocimiento import archivos as CON

    cfg = config()
    CON.preparar_conocimiento()
    aprender(cfg)
    resumen()
