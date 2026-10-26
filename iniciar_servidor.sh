#!/usr/bin/env bash
# Abre el sistema para esta PC y para las PC del trabajo (túnel de Cloudflare). Equivale a iniciar_servidor.bat.
# REINICIO-DESDE-EL-PANEL: el panel cierra el servidor con el código 75 y acá se vuelve a abrir solo.
cd "$(dirname "$(readlink -f "$0")")" || exit 1
source linux/comun.sh
titulo "Transcripción - SERVIDOR (no cerrar)"
falta_instalar
if [ ! -f acceso_remoto.json ]; then
  echo "Falta la contraseña del acceso remoto."
  "$PY" configurar_acceso.py
fi
asegurar_cloudflared || exit 1
"$PY" -c "import docx" 2>/dev/null || "$PY" -m pip install -q python-docx
preparar_cuda
bucle_servidor --tunel "$@"
