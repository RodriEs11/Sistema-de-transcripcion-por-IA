#!/usr/bin/env bash
# El servidor como servicio de Linux (systemd, del usuario): arranca solo al prender la PC, se vuelve a
# abrir si se cae y el panel de administración lo puede reiniciar.
#   ./servicio.sh instalar [--sin-tunel]   lo instala y lo inicia (con túnel salvo --sin-tunel)
#   ./servicio.sh estado                   cómo está
#   ./servicio.sh registro                 lo que va mostrando (Ctrl+C para salir)
#   ./servicio.sh reiniciar | detener | iniciar
#   ./servicio.sh quitar                   lo desinstala (no borra nada del sistema de transcripción)
cd "$(dirname "$(readlink -f "$0")")" || exit 1
source linux/comun.sh

NOMBRE=transcripcion
UNIDAD="$HOME/.config/systemd/user/$NOMBRE.service"
SC=(systemctl --user)

if ! command -v systemctl >/dev/null 2>&1; then
  error "Este Linux no usa systemd. Abrí el servidor con ./iniciar_servidor.sh (por ejemplo dentro de tmux o screen)."
  exit 1
fi

case "${1:-}" in
  instalar)
    falta_instalar
    ARGS="--tunel"
    [ "${2:-}" = "--sin-tunel" ] && ARGS=""
    if [ -n "$ARGS" ]; then
      if [ ! -f acceso_remoto.json ]; then
        echo "Falta la contraseña del acceso remoto."
        "$PY" scripts/configurar_acceso.py
      fi
      asegurar_cloudflared || exit 1
    fi
    preparar_cuda
    DIR="$(pwd)"
    mkdir -p "$(dirname "$UNIDAD")"
    cat > "$UNIDAD" <<UNIT
[Unit]
Description=Transcripción de informes médicos (servidor)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$DIR
Environment=PYTHONIOENCODING=utf-8
Environment=PYTHONUTF8=1
Environment=TRANSCRIPCION_REINICIO=1
Environment="LD_LIBRARY_PATH=${LD_LIBRARY_PATH:-}"
Environment="PATH=$DIR:/usr/local/bin:/usr/bin:/bin"
ExecStart=$DIR/$PY servidor.py $ARGS --sin-navegador
# El panel reinicia con el código 75; cualquier otra caída también se vuelve a abrir.
Restart=always
RestartSec=3
KillSignal=SIGTERM
TimeoutStopSec=60

[Install]
WantedBy=default.target
UNIT
    "${SC[@]}" daemon-reload
    "${SC[@]}" enable --now "$NOMBRE"
    # que arranque al prender la PC aunque nadie inicie sesión
    if ! loginctl enable-linger "$USER" 2>/dev/null; then
      aviso "Para que arranque sin iniciar sesión, ejecutá una vez:  sudo loginctl enable-linger $USER"
    fi
    ok "Servicio instalado e iniciado."
    echo "Interfaz en esta PC: http://127.0.0.1:8765   ·   Ver lo que hace: ./servicio.sh registro"
    ;;
  quitar)
    "${SC[@]}" disable --now "$NOMBRE" 2>/dev/null
    rm -f "$UNIDAD"
    "${SC[@]}" daemon-reload
    ok "Servicio quitado. Se puede seguir abriendo a mano con ./iniciar_servidor.sh"
    ;;
  estado)    "${SC[@]}" status "$NOMBRE" --no-pager ;;
  registro)  journalctl --user -u "$NOMBRE" -f -n 50 ;;
  reiniciar) "${SC[@]}" restart "$NOMBRE" && ok "Reiniciado." ;;
  detener)   "${SC[@]}" stop "$NOMBRE" && ok "Detenido." ;;
  iniciar)   "${SC[@]}" start "$NOMBRE" && ok "Iniciado." ;;
  *)
    sed -n '2,8p' "$0" | sed 's/^# \{0,1\}//'
    exit 1 ;;
esac
