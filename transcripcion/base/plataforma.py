# -*- coding: utf-8 -*-
"""Lo que cambia entre Windows y Linux, en un solo lugar.

- nombres de los scripts para abrir el servidor (.bat en Windows, .sh en Linux);
- dónde está cloudflared (cloudflared.exe en Windows; en Linux el que bajó instalar.sh en la carpeta
  sistema o el que esté instalado en el sistema);
- abrir un archivo o carpeta con el programa del escritorio (Explorador / xdg-open);
- rutas de configuracion.json escritas con barras de Windows ("..\\Informes") también valen en Linux.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path
from transcripcion import RAIZ

AQUI = RAIZ  # carpeta del sistema (no la del paquete)
ES_WINDOWS = os.name == "nt"
NOMBRE = "windows" if ES_WINDOWS else ("mac" if sys.platform == "darwin" else "linux")
EXT_SCRIPT = ".bat" if ES_WINDOWS else ".sh"


def script(nombre):
    """'iniciar_servidor' -> 'iniciar_servidor.bat' en Windows, 'iniciar_servidor.sh' en Linux."""
    return nombre + EXT_SCRIPT


def ruta_cloudflared():
    """Ruta de cloudflared que se va a usar (aunque todavía no exista, para los mensajes)."""
    if ES_WINDOWS:
        return AQUI / "cloudflared.exe"
    propio = AQUI / "cloudflared"
    if propio.exists():
        return propio
    otro = shutil.which("cloudflared")
    return Path(otro) if otro else propio


def ruta_devtunnel():
    """Ruta de devtunnel (Microsoft Dev Tunnels): devtunnel.exe en la carpeta sistema; en Linux, el de la
    carpeta o el del PATH."""
    if ES_WINDOWS:
        return AQUI / "devtunnel.exe"
    propio = AQUI / "devtunnel"
    if propio.exists():
        return propio
    otro = shutil.which("devtunnel")
    return Path(otro) if otro else propio


def descarga_devtunnel():
    """Dirección oficial de Microsoft para bajar devtunnel en este sistema."""
    import platform

    if ES_WINDOWS:
        return "https://aka.ms/TunnelsCliDownload/win-x64"
    arq = platform.machine().lower()
    return "https://aka.ms/TunnelsCliDownload/linux-" + ("arm64" if arq in ("aarch64", "arm64") else "x64")


def ruta_config(texto):
    """Ruta de configuracion.json -> Path. En Linux "..\\Audios_nuevos" se lee como "../Audios_nuevos"."""
    texto = str(texto)
    if not ES_WINDOWS and "\\" in texto and not texto.startswith("\\\\"):
        texto = texto.replace("\\", "/")
    return Path(texto)


def puede_abrir():
    """True si hay un escritorio donde abrir archivos y carpetas (no en un servidor sin pantalla)."""
    if ES_WINDOWS:
        return True
    if sys.platform == "darwin":
        return True
    return bool((os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")) and shutil.which("xdg-open"))


def abrir(ruta):
    """Abre una carpeta o archivo con el programa del escritorio. False si en esta PC no se puede."""
    if ES_WINDOWS:
        os.startfile(str(ruta))
        return True
    if not puede_abrir():
        return False
    prog = "open" if sys.platform == "darwin" else "xdg-open"
    subprocess.Popen(
        [prog, str(ruta)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    return True
