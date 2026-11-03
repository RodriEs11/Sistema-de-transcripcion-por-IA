"""Exportación/reconciliación explícita del aprendizaje; no se ejecuta al iniciar el servidor."""
import argparse
import sqlite3
from pathlib import Path
from transcripcion.aprendizaje import aprender as A
from transcripcion.aprendizaje import almacen as AL
from transcripcion.base import registro as L


def main():
    p = argparse.ArgumentParser(description=__doc__)
    acciones = p.add_mutually_exclusive_group(required=True)
    acciones.add_argument('--exportar', type=Path, help='CSV nuevo, sin sobrescribir archivos existentes')
    acciones.add_argument('--respaldar', type=Path, help='Copia consistente SQLite nueva mediante backup API')
    acciones.add_argument('--reconciliar', action='store_true', help='Releer ejemplos editados/borrados fuera de la aplicación')
    args = p.parse_args()
    if args.reconciliar:
        A.analizar_correcciones(reconstruir=True)
    else:
        destino = args.exportar or args.respaldar
        if destino.exists():
            p.error('El destino ya existe: elegí otro nombre.')
        if args.exportar:
            AL.exportar_historial(A.HIST, destino)
        else:
            origen = sqlite3.connect(AL.ruta_base(A.HIST).resolve().as_uri()+'?mode=ro', uri=True)
            try:
                copia = sqlite3.connect(destino)
                try:
                    origen.backup(copia)
                finally:
                    copia.close()
            finally:
                origen.close()
    L.info('APRENDIZAJE', 'Mantenimiento solicitado completado.')


if __name__ == '__main__':
    main()
