# Funciones comunes de los scripts de Linux (instalar.sh, interfaz.sh, iniciar_servidor.sh,
# configurar_acceso.sh, servicio.sh). No se ejecuta solo: lo cargan esos scripts con "source".
# Cada script hace antes: cd a la carpeta sistema.

export PYTHONIOENCODING=utf-8
export PYTHONUTF8=1

# Entorno de Python. Si la carpeta viene de Windows (".venv" con Scripts\ y sin bin/), se usa otro
# para no mezclarlos: ".venv-linux".
if [ -x .venv/bin/python ]; then
  VENV=.venv
elif [ -d .venv/Scripts ]; then
  VENV=.venv-linux
else
  VENV=.venv
fi
PY="$VENV/bin/python"

if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then _A=$'\033[33m' _E=$'\033[31m' _O=$'\033[32m' _N=$'\033[0m'
else _A='' _E='' _O='' _N=''; fi
aviso() { printf '%s%s%s\n' "$_A" "$*" "$_N"; }
error() { printf '%s[ERROR]%s %s\n' "$_E" "$_N" "$*" >&2; }
ok()    { printf '%s%s%s\n' "$_O" "$*" "$_N"; }

titulo() {   # título de la ventana de la terminal
  [ -t 1 ] && printf '\033]0;%s\007' "$1"
  return 0
}

hay_pantalla() { [ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]; }

falta_instalar() {
  if [ ! -x "$PY" ]; then
    error "Primero tenés que ejecutar ./instalar.sh"
    exit 1
  fi
}

# Bibliotecas de CUDA/cuDNN instaladas con pip (paquetes nvidia-*): Whisper las busca en LD_LIBRARY_PATH.
preparar_cuda() {
  local d
  d=$("$PY" - <<'PYEOF' 2>/dev/null
import glob, os, site, sys
bases = set(site.getsitepackages()) | {sys.prefix}
ds = sorted({d for b in bases for d in glob.glob(os.path.join(b, "nvidia", "*", "lib"))})
print(":".join(ds))
PYEOF
)
  if [ -n "$d" ]; then
    export LD_LIBRARY_PATH="$d${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
  fi
}

# cloudflared (túnel de Cloudflare para las PC del trabajo). Usa el que esté instalado en el sistema o lo
# baja una sola vez a esta carpeta.
asegurar_cloudflared() {
  if [ -x ./cloudflared ] || command -v cloudflared >/dev/null 2>&1; then
    return 0
  fi
  local arq
  case "$(uname -m)" in
    x86_64|amd64)  arq=amd64 ;;
    aarch64|arm64) arq=arm64 ;;
    armv7l|armv6l) arq=arm ;;
    i386|i686)     arq=386 ;;
    *) error "No sé qué cloudflared bajar para $(uname -m). Instalalo a mano (https://github.com/cloudflare/cloudflared/releases) y volvé a intentar."
       return 1 ;;
  esac
  echo "Descargando cloudflared (el túnel de Cloudflare, una sola vez)..."
  local url="https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-$arq"
  if command -v curl >/dev/null 2>&1; then
    curl -L --fail -o cloudflared.descarga "$url"
  elif command -v wget >/dev/null 2>&1; then
    wget -O cloudflared.descarga "$url"
  else
    error "Falta curl (o wget) para descargar cloudflared. Instalalo con: sudo apt install curl"
    return 1
  fi || { rm -f cloudflared.descarga; error "No se pudo descargar cloudflared. Revisá la conexión a internet."; return 1; }
  chmod +x cloudflared.descarga && mv cloudflared.descarga cloudflared
  ok "cloudflared listo."
}

# Abre el servidor y lo vuelve a abrir cuando el panel de administración lo reinicia (código 75).
# REINICIO-DESDE-EL-PANEL
bucle_servidor() {
  export TRANSCRIPCION_REINICIO=1
  local extra=() c
  hay_pantalla || extra=(--sin-navegador)     # sin escritorio: no intentar abrir un navegador
  while true; do
    "$PY" servidor.py "$@" "${extra[@]}"
    c=$?
    if [ "$c" -ne 75 ]; then
      return "$c"
    fi
    echo
    echo "Reiniciando el servidor..."
    extra=(--sin-navegador)
  done
}
