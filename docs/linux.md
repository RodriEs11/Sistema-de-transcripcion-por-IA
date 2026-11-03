# Servidor en Linux

El servidor (Whisper, la IA, la interfaz web, el panel y el túnel) también corre en Linux. Las PC del
trabajo no cambian: siguen usando `Transcripcion.exe` en Windows y se conectan por el túnel igual que antes.

Probado en Ubuntu 22.04 con Python 3.10. Debería andar en cualquier distribución con systemd y Python ≥ 3.10.

## Requisitos

- Placa NVIDIA de al menos 10 GB con su driver (`nvidia-smi` tiene que responder). En Ubuntu:
  `sudo ubuntu-drivers install` y reiniciar. No hace falta instalar CUDA: las bibliotecas vienen por pip.
- Python 3.10 a 3.13 con venv: `sudo apt install python3 python3-venv curl git`.
- [Ollama](https://ollama.com/download/linux) (si falta, `instalar.sh` ofrece instalarlo).
- Unos 15 GB libres.

## Instalación

```bash
mkdir -p ~/Transcripcion && cd ~/Transcripcion
git clone https://github.com/RodriEs11/Sistema-de-transcripcion-por-IA.git sistema
cd sistema
bash instalar.sh            # o ./instalar.sh --si para no responder preguntas
```

`instalar.sh`:
1. Busca Python (3.12, 3.11, 3.13 o 3.10) y crea el entorno `.venv` (o `.venv-linux` si la carpeta trae el
   `.venv` de Windows, para no mezclarlos).
2. Instala `requirements.txt` (Whisper, las bibliotecas de CUDA y python-docx).
3. Crea `configuracion.json` y `conocimiento/` desde los ejemplos si faltan.
4. Revisa la placa de video. Sin NVIDIA pregunta si usar el procesador (`"dispositivo_whisper": "cpu"`,
   mucho más lento).
5. Instala Ollama si falta y baja el modelo de `configuracion.json` (`gemma4:12b`).
6. Descarga Whisper large-v3 (~3 GB) y lo prueba.

Al terminar dice qué quedó pendiente, si algo falló.

## Uso

| Windows | Linux | Para qué |
|---|---|---|
| `interfaz.bat` | `./interfaz.sh` | Solo esta PC |
| `iniciar_servidor.bat` | `./iniciar_servidor.sh` | Esta PC + las PC del trabajo (túnel) |
| `configurar_acceso.bat` | `./configurar_acceso.sh` | Contraseña del acceso remoto y anular PC |
| — | `./servicio.sh instalar` | Que arranque solo al prender la PC |

- `iniciar_servidor.sh` baja `cloudflared` para Linux la primera vez (a la carpeta `sistema`; si ya está
  instalado en el sistema, usa ese).
- Los dos scripts vuelven a abrir el servidor cuando el panel lo reinicia (código 75), igual que los .bat.
- Si la PC no tiene escritorio (sin `DISPLAY`/`WAYLAND_DISPLAY`) no se intenta abrir el navegador, y el
  panel esconde los botones «Abrir…» (no hay dónde abrir carpetas).
- Ctrl+C, `kill` o `systemctl stop` apagan en orden: cierran el túnel y anotan el resumen del día.

## Como servicio (arranca solo)

```bash
./servicio.sh instalar              # con túnel (pide la contraseña del acceso remoto si falta)
./servicio.sh instalar --sin-tunel  # solo esta PC
./servicio.sh estado | registro | reiniciar | detener | iniciar | quitar
```

Crea un servicio de systemd del usuario (`~/.config/systemd/user/transcripcion.service`) que se vuelve a
abrir si se cae y que el panel puede reiniciar. Para que arranque sin iniciar sesión hace falta, una vez,
`sudo loginctl enable-linger $USER` (el script avisa si no lo pudo hacer solo). Lo que muestra la ventana
del servidor queda en `./servicio.sh registro` y, como siempre, en `registros/`.

## PC sin pantalla (servidor remoto)

La interfaz y el panel de administración solo se abren desde la misma PC (127.0.0.1). Desde otra
computadora se puede llegar con un túnel SSH:

```bash
ssh -L 8765:127.0.0.1:8765 usuario@servidor
# y en esa computadora: http://127.0.0.1:8765  y  http://127.0.0.1:8765/admin
```

## Diferencias con Windows

| Tema | Windows | Linux |
|---|---|---|
| Entorno de Python | `.venv\Scripts` | `.venv/bin` (o `.venv-linux`) |
| Bibliotecas de CUDA | `os.add_dll_directory` | `LD_LIBRARY_PATH` (lo ponen los .sh) o carga directa en `fase1_transcribir.preparar_cuda` |
| Túnel | `cloudflared.exe` | `cloudflared` |
| Reinicio desde el panel | título de la ventana + marca en el .bat | variable `TRANSCRIPCION_REINICIO=1` (la ponen los .sh y el servicio) |
| «Abrir…» del panel, abrir el Word | Explorador / Word | `xdg-open` (solo con escritorio) |
| Rutas de `configuracion.json` | `..\\Informes` | se aceptan igual (`..\\Informes` = `../Informes`) |

Todo lo que depende del sistema está en `transcripcion/base/plataforma.py` (Python) y `linux/comun.sh` (scripts).

## Solución de problemas

- **`Library libcublas.so.12 is not found`**: abrir el servidor con los .sh (ponen `LD_LIBRARY_PATH`) y
  revisar que `instalar.sh` haya terminado sin errores.
- **`nvidia-smi` no responde**: falta el driver o hay que reiniciar después de instalarlo.
- **«Ollama cerrado»**: `sudo systemctl start ollama` (y `sudo systemctl enable ollama` para que arranque solo).
- **Permiso denegado al ejecutar un .sh**: `chmod +x *.sh` o `bash iniciar_servidor.sh`.
