#!/usr/bin/env bash
# Contraseña del acceso remoto y PC del trabajo autorizadas. Equivale a configurar_acceso.bat.
cd "$(dirname "$(readlink -f "$0")")" || exit 1
source linux/comun.sh
falta_instalar
exec "$PY" scripts/configurar_acceso.py
