"""Sistema de transcripción de informes médicos: paquete con los módulos del sistema.

Se reorganiza por etapas (docs/refactor.md). Los puntos de entrada (servidor.py, informe.py, los .bat) siguen
en la carpeta del sistema y se ejecutan desde ahí.
"""
from pathlib import Path

# Carpeta del sistema (la de servidor.py), no la de este paquete. Todo lo que es de la instalación
# (registros/, usuarios.json, conocimiento/, cloudflared, configuracion.json…) se ubica a partir de acá.
RAIZ = Path(__file__).resolve().parent.parent
