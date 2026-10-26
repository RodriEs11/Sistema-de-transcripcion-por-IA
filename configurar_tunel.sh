#!/usr/bin/env bash
# Elegir el túnel para las PC del trabajo (Cloudflare o Microsoft Dev Tunnels). Equivale a configurar_tunel.bat.
cd "$(dirname "$(readlink -f "$0")")" || exit 1
source linux/comun.sh
falta_instalar
exec "$PY" configurar_tunel.py
