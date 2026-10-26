# -*- coding: utf-8 -*-
"""Elegir el túnel para las PC del trabajo: el rápido de Cloudflare (sin cuenta, la dirección cambia en cada
reinicio) o Microsoft Dev Tunnels (con una cuenta de Microsoft o GitHub, la dirección es siempre la misma).
Se abre con configurar_tunel.bat (Windows) o configurar_tunel.sh (Linux). El cambio se toma al reiniciar
el servidor."""
import os
import re
import secrets
import string
import subprocess
import sys
import time
import urllib.request

import plataforma as P
import registro as L
import remoto as R

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

PUERTO_TUNEL = int(os.environ.get("PUERTO_TUNEL", str(int(os.environ.get("PUERTO_INTERFAZ", "8765")) + 1)))
EXE = P.ruta_devtunnel()


def descargar():
    if EXE.exists():
        return True
    url = P.descarga_devtunnel()
    print(f"\nDescargando el programa de Microsoft Dev Tunnels ({EXE.name}, una sola vez)…")
    tmp = EXE.with_name(EXE.name + ".descarga")
    try:
        with urllib.request.urlopen(url, timeout=120) as r, open(tmp, "wb") as f:
            n = 0
            while True:
                b = r.read(1 << 20)
                if not b:
                    break
                f.write(b)
                n += len(b)
                print(f"\r  {n / 1e6:5.1f} MB", end="", flush=True)
        print()
        if n < 1_000_000:
            raise RuntimeError("el archivo bajado es demasiado chico")
        tmp.replace(EXE)
        if not P.ES_WINDOWS:
            EXE.chmod(0o755)
        print("  Listo.")
        return True
    except Exception as ex:
        print(f"\nNo se pudo descargar: {ex}\nRevisá la conexión a internet. También se puede bajar a mano desde\n"
              f"  {url}\ny guardarlo como {EXE} .")
        try:
            tmp.unlink()
        except Exception:
            pass
        return False


def usuario():
    """Nombre de la cuenta con la que se inició sesión en devtunnel, o None."""
    cod, sal = R._correr([str(EXE), "user", "show"], timeout=60)
    if cod != 0 or re.search(r"not logged in", sal, re.I):
        return None
    m = re.search(r"Logged in as\s+(.+?)(?:\s+using\s+(\w+))?\.?\s*$", sal, re.M | re.I)
    return (m.group(1) + (f" ({m.group(2)})" if m.group(2) else "")) if m else "sesión iniciada"


def iniciar_sesion():
    print("\n¿Con qué cuenta querés entrar? (es solo para tu PC; en el trabajo no se pide nada)")
    print(" 1) Cuenta de Microsoft (Outlook, Hotmail, Live)")
    print(" 2) Cuenta de GitHub")
    op = input("Elegí 1 o 2: ").strip()
    args = [str(EXE), "user", "login"] + (["-g"] if op == "2" else [])
    if not P.ES_WINDOWS and not P.puede_abrir():
        args.append("-d")          # sin escritorio: código para escribir en el navegador de otro equipo
    print("\nSe abre el navegador para entrar. Cuando termines, volvé a esta ventana.\n")
    subprocess.call(args)
    u = usuario()
    print(("\nSesión iniciada: " + u) if u else "\nNo quedó la sesión iniciada. Probá de nuevo.")
    return u


def crear_tunel():
    tid = (R.config_tunel().get("devtunnel") or {}).get("id")
    if tid:
        cod, sal = R._correr([str(EXE), "show", tid], timeout=60)
        if cod == 0:
            if not re.search(rf"\b{PUERTO_TUNEL}\b", sal):
                R._correr([str(EXE), "port", "create", tid, "-p", str(PUERTO_TUNEL), "--protocol", "http"])
            print(f"\nEl túnel «{tid}» ya existe: se sigue usando (misma dirección).")
            return tid
        print(f"\nEl túnel «{tid}» ya no existe: creo uno nuevo.")
    nombre = "transcripcion-" + "".join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(8))
    print(f"\nCreando el túnel «{nombre}» (con acceso sin cuenta para las PC del trabajo; la contraseña del "
          f"sistema sigue protegiendo todo)…")
    completo, sal = R.crear_devtunnel(EXE, nombre, PUERTO_TUNEL)
    if not completo:
        print("No se pudo crear el túnel:\n" + sal.strip()[-600:])
        return None
    print(f"  Túnel creado: {completo}")
    return completo


def usar_devtunnel():
    if not descargar():
        return
    if not usuario() and not iniciar_sesion():
        return
    tid = crear_tunel()
    if not tid:
        return
    R.guardar_config_tunel(servicio="devtunnel", devtunnel={"id": tid, "creado": time.time()})
    L.ok("TÚNEL", f"Túnel cambiado a Microsoft Dev Tunnels («{tid}», puerto {PUERTO_TUNEL}) con configurar_tunel. "
                  "Se toma al reiniciar el servidor.")
    print(f"""
Listo: el servidor va a usar Microsoft Dev Tunnels.

 1. Reiniciá el servidor: botón «Reiniciar servidor» del panel de administración, o cerrá la
    ventana del servidor y abrí {P.script('iniciar_servidor')} de nuevo.
 2. La dirección aparece en la ventana del servidor (termina en devtunnels.ms) y queda SIEMPRE
    la misma, aunque reinicies.
 3. En cada PC del trabajo, la primera vez: Opciones → Configuración → Conexión → «Cambiar…»
    y pegá esa dirección. Desde la versión 1.12 la aplicación la encuentra sola.
""")


def usar_cloudflare():
    R.guardar_config_tunel(servicio="cloudflare")
    L.ok("TÚNEL", "Túnel cambiado al rápido de Cloudflare con configurar_tunel. Se toma al reiniciar el servidor.")
    print(f"\nListo: el servidor va a usar el túnel rápido de Cloudflare. Reinicialo para que lo tome.")


def main():
    while True:
        dt = R.config_tunel().get("devtunnel") or {}
        print("\n=== Túnel para las PC del trabajo ===")
        print("En uso:", R.nombre_servicio())
        if EXE.exists():
            u = usuario()
            print("Microsoft Dev Tunnels:", ("sesión de " + u) if u else "sin sesión iniciada",
                  "· túnel " + dt["id"] if dt.get("id") else "· sin túnel creado")
        print("\n 1) Usar Microsoft Dev Tunnels (descarga el programa, iniciás sesión y se crea el túnel)")
        print(" 2) Volver al túnel rápido de Cloudflare")
        print(" 3) Iniciar sesión de nuevo en Microsoft Dev Tunnels (si venció)")
        print(" 4) Salir")
        op = input("\nElegí una opción: ").strip()
        if op == "1":
            usar_devtunnel()
        elif op == "2":
            usar_cloudflare()
        elif op == "3":
            if descargar():
                iniciar_sesion()
        elif op in ("4", ""):
            return


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        print()
