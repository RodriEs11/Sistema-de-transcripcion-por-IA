#!/usr/bin/env bash
# Instalación del sistema de transcripción en Linux (una sola vez). Equivale a instalar.bat.
#   ./instalar.sh          pregunta antes de instalar Ollama o bajar el modelo
#   ./instalar.sh --si     responde que sí a todo (sin preguntas)
cd "$(dirname "$(readlink -f "$0")")" || exit 1
source linux/comun.sh

SI=0
PENDIENTE=()
[ "${1:-}" = "--si" ] && SI=1

preguntar() {   # preguntar "texto" [S|N]  -> 0 = sí
  local def="${2:-S}" r
  [ "$SI" = 1 ] && return 0
  if [ ! -t 0 ]; then
    [ "$def" = S ]; return
  fi
  read -r -p "$1 [$( [ "$def" = S ] && echo 'S/n' || echo 's/N' )] " r
  r="${r:-$def}"
  case "$r" in s|S|si|sí|Si|Sí|y|Y) return 0 ;; *) return 1 ;; esac
}

echo "=========================================================="
echo "  Instalación del sistema de transcripción (una sola vez)"
echo "=========================================================="
echo

# ---------------------------------------------------------------- Python
PYSIS=""
for v in 3.12 3.11 3.13 3.10; do
  if command -v "python$v" >/dev/null 2>&1; then PYSIS="python$v"; break; fi
done
if [ -z "$PYSIS" ] && command -v python3 >/dev/null 2>&1 \
   && python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'; then
  PYSIS=python3
fi
if [ -z "$PYSIS" ]; then
  error "No encontré Python 3.10 o más nuevo."
  echo "En Ubuntu/Debian:  sudo apt install python3 python3-venv python3-pip"
  exit 1
fi
echo "Usando: $PYSIS ($($PYSIS --version 2>&1))"

if [ ! -x "$PY" ]; then
  echo "Creando el entorno de Python en $VENV ..."
  if ! "$PYSIS" -m venv "$VENV"; then
    rm -rf "$VENV"
    error "No se pudo crear el entorno."
    echo "En Ubuntu/Debian falta un paquete:  sudo apt install ${PYSIS}-venv   (o python3-venv)"
    exit 1
  fi
fi

"$PY" -m pip install --upgrade pip
echo
echo "Instalando Whisper y las bibliotecas de la placa de video (puede tardar varios minutos)..."
if ! "$PY" -m pip install -r requirements.txt; then
  error "Falló la instalación de las bibliotecas."
  exit 1
fi

# configuracion.json y conocimiento/ (se crean desde los ejemplos si faltan)
"$PY" -c "import informe; from transcripcion.conocimiento import archivos; informe.config(); archivos.preparar_conocimiento()" || { error "No se pudo preparar la configuración."; exit 1; }
chmod +x ./*.sh 2>/dev/null

# ---------------------------------------------------------------- placa de video
DISP=cuda
if command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi -L >/dev/null 2>&1; then
  ok "Placa de video: $(nvidia-smi --query-gpu=name --format=csv,noheader | head -1)"
  "$PY" - <<'PYEOF'
import json, pathlib
p = pathlib.Path("configuracion.json"); c = json.loads(p.read_text(encoding="utf-8-sig"))
if c.get("dispositivo_whisper", "cuda") != "cuda":
    c["dispositivo_whisper"] = "cuda"; p.write_text(json.dumps(c, ensure_ascii=False, indent=2), encoding="utf-8")
PYEOF
else
  aviso "No encontré una placa NVIDIA (o falta su driver: nvidia-smi no responde)."
  echo "Whisper puede usar el procesador, pero es mucho más lento (varios minutos por audio)."
  if preguntar "¿Usar el procesador?" N; then
    DISP=cpu
    "$PY" - <<'PYEOF'
import json, pathlib
p = pathlib.Path("configuracion.json"); c = json.loads(p.read_text(encoding="utf-8-sig"))
c["dispositivo_whisper"] = "cpu"; p.write_text(json.dumps(c, ensure_ascii=False, indent=2), encoding="utf-8")
PYEOF
  else
    DISP=ninguno
    echo "Instalá el driver de NVIDIA (en Ubuntu: sudo ubuntu-drivers install), reiniciá y volvé a ejecutar ./instalar.sh"
    PENDIENTE+=("driver de NVIDIA (o elegir el procesador volviendo a ejecutar ./instalar.sh)")
  fi
fi

# ---------------------------------------------------------------- Ollama (la IA)
MODELO=$("$PY" -c "import informe; print(informe.config()['modelo_ia'])")
if ! command -v ollama >/dev/null 2>&1; then
  aviso "Falta Ollama (la IA que arma los informes)."
  if preguntar "¿Instalarlo ahora? (pide la contraseña de administrador)" S; then
    if ! (set -o pipefail; curl -fsSL https://ollama.com/install.sh | sh); then
      error "No se pudo instalar Ollama. Instalalo a mano: https://ollama.com/download/linux"
    fi
  fi
fi
if command -v ollama >/dev/null 2>&1; then
  if ollama list 2>/dev/null | awk 'NR>1{print $1}' | grep -qx "$MODELO"; then
    ok "Ollama listo con el modelo $MODELO."
  elif ! ollama list >/dev/null 2>&1; then
    aviso "Ollama está instalado pero no responde. Inicialo con:  sudo systemctl start ollama"
    echo "Después bajá el modelo con:  ollama pull $MODELO"
    PENDIENTE+=("iniciar Ollama (sudo systemctl start ollama) y bajar el modelo: ollama pull $MODELO")
  elif preguntar "¿Bajar el modelo $MODELO ahora? (varios GB)" S; then
    ollama pull "$MODELO" || { error "No se pudo bajar el modelo. Probá más tarde con: ollama pull $MODELO"
                               PENDIENTE+=("bajar el modelo de la IA: ollama pull $MODELO"); }
  else
    echo "Bajalo cuando quieras con:  ollama pull $MODELO"
    PENDIENTE+=("bajar el modelo de la IA: ollama pull $MODELO")
  fi
else
  PENDIENTE+=("instalar Ollama: https://ollama.com/download/linux")
fi

# ---------------------------------------------------------------- Whisper
if [ "$DISP" != ninguno ]; then
  echo
  echo "Descargando el modelo de Whisper (~3 GB, solo la primera vez) y probándolo..."
  preparar_cuda
  if ! "$PY" fase1_transcribir.py --verificar --device "$DISP"; then
    PENDIENTE+=("que Whisper funcione (ver el error de arriba)")
  fi
fi

echo
if [ ${#PENDIENTE[@]} -eq 0 ]; then
  ok "Instalación terminada."
else
  aviso "Instalación terminada, pero falta:"
  for p in "${PENDIENTE[@]}"; do echo "  - $p"; done
  echo "El sistema abre igual; lo que falta se puede resolver después."
fi
echo "  Solo esta PC:                      ./interfaz.sh"
echo "  Esta PC + las PC del trabajo:      ./iniciar_servidor.sh"
echo "  Que arranque solo con la PC:       ./servicio.sh instalar"
