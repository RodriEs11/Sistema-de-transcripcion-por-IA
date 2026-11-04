"""Respaldo consistente de la cola sin iniciar el servidor ni tomar su lock de propietario."""
import sys
import argparse
from pathlib import Path
RAIZ = Path(__file__).resolve().parents[1]     # carpeta del sistema (este archivo está en scripts/)
sys.path.insert(0, str(RAIZ))                  # para importar transcripcion

from transcripcion.procesamiento.cola import respaldar


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--base', type=Path, required=True, help='cola_procesamiento.sqlite3 de la instalación')
    p.add_argument('--respaldar', type=Path, required=True, help='Archivo nuevo en una carpeta existente del mismo volumen que su temporal')
    a = p.parse_args()
    try:
        respaldar(a.base, a.respaldar)
    except Exception as ex:
        p.exit(1, f'No se publicó el respaldo: {ex}\n')
    print(f'Respaldo verificado: {a.respaldar.resolve()}')
