#!/usr/bin/env bash
# Abre el sistema solo para esta PC (sin acceso desde el trabajo). Equivale a interfaz.bat.
# REINICIO-DESDE-EL-PANEL: el panel cierra el servidor con el código 75 y acá se vuelve a abrir solo.
cd "$(dirname "$(readlink -f "$0")")" || exit 1
source linux/comun.sh
titulo "Transcripción - Servidor (no cerrar)"
falta_instalar
"$PY" -c "import docx" 2>/dev/null || "$PY" -m pip install -q python-docx
preparar_cuda
bucle_servidor "$@"
