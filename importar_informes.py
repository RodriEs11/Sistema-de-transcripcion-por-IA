# -*- coding: utf-8 -*-
"""Lanzador de consola: `python importar_informes.py [carpeta]` importa informes Word como referencias.
El código está en transcripcion/conocimiento/importar.py (docs/refactor.md, etapa 6b)."""

if __name__ == "__main__":
    import sys

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")   # acentos en la consola de Windows
    except Exception:
        pass
    from transcripcion.conocimiento.importar import main

    main()
