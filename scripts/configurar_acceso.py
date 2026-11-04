# -*- coding: utf-8 -*-
"""Contraseña del acceso remoto y PC del trabajo autorizadas. Se abre con configurar_acceso.bat (Windows)
o configurar_acceso.sh (Linux)."""
from pathlib import Path
import getpass
import sys

RAIZ = Path(__file__).resolve().parents[1]     # carpeta del sistema (este archivo está en scripts/)
sys.path.insert(0, str(RAIZ))                  # para importar transcripcion

from transcripcion.base import plataforma as P
from transcripcion.base import registro as L
from transcripcion.acceso import remoto as R

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def pcs():
    return R._leer().get("clientes", {})


def main():
    while True:
        print("\n=== Acceso desde las PC del trabajo ===")
        print("Contraseña:", "configurada" if R.configurado() else "TODAVÍA NO CONFIGURADA")
        v = pcs()
        print("PC autorizadas:", ", ".join(sorted({c['pc'] for c in v.values()})) or "ninguna")
        print("\n 1) Poner o cambiar la contraseña")
        print(" 2) Anular una PC (si se perdió o ya no se usa)")
        print(" 3) Salir")
        op = input("\nElegí una opción: ").strip()
        if op == "1":
            c1 = getpass.getpass("Contraseña nueva (mínimo 8 caracteres, no se ve al escribir): ")
            if len(c1) < 8:
                print("Muy corta. Usá al menos 8 caracteres."); continue
            if getpass.getpass("Repetila: ") != c1:
                print("No coinciden."); continue
            ya = R.configurado()
            R.poner_contrasena(c1)
            L.ok("ACCESO", "Contraseña del acceso remoto " + ("cambiada" if ya else "configurada")
                 + " desde " + P.script("configurar_acceso") + ".")
            print("\nListo. La carpeta 'cliente' tiene el archivo conexion.json que va junto a")
            print("Transcripcion.exe en las PC del trabajo. Las PC ya vinculadas siguen funcionando.")
        elif op == "2":
            nombre = input("Nombre de la PC a anular (ej. info-02): ").strip()
            n = R.anular_pc(nombre)
            if n:
                L.aviso("ACCESO", f"PC anulada desde {P.script('configurar_acceso')}: {nombre} ({n} llaves).")
            print(f"Anuladas {n} llaves de {nombre}." if n else "No encontré esa PC.")
        elif op == "3":
            return


if __name__ == "__main__":
    L.configurar(consola=False, programa="configurar_acceso")
    main()
