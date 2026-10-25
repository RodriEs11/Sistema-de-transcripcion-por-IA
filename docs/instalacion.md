# Instalación

## 1. Servidor

### Requisitos

- Windows 10/11 con placa NVIDIA de al menos 10 GB de VRAM y drivers actualizados.
- [Python](https://www.python.org/downloads/) 3.10–3.13 (recomendado 3.12, marcando *Add python.exe to PATH*).
- [Ollama](https://ollama.com/download).
- [Git](https://git-scm.com/download/win) (solo para clonar).
- Unos 15 GB libres (modelos de Whisper y Gemma).

### Pasos

```bat
mkdir "C:\Transcripcion" && cd /d "C:\Transcripcion"
git clone https://github.com/<usuario>/<repositorio>.git sistema
cd sistema
instalar.bat
ollama pull gemma4:12b
```

`instalar.bat`:
1. Busca Python (3.12, 3.11, 3.13 o 3.10) y crea el entorno virtual `.venv`.
2. Instala `requirements.txt`: `faster-whisper`, `av<16`, las bibliotecas CUDA (`nvidia-cublas-cu12`, `nvidia-cudnn-cu12` 9.x) y `python-docx`.
3. Descarga Whisper large-v3 (~3 GB) y prueba la GPU (`python fase1_transcribir.py --verificar`).

> `av` queda fijado en `<16` porque PyAV 16 es incompatible con faster-whisper; además el WAV se lee con código propio.

### Primer arranque

1. Abrir **Ollama**.
2. Ejecutar **`interfaz.bat`**. Se abre http://127.0.0.1:8765. No cerrar la ventana negra: es el servidor.
3. En el primer arranque se crean automáticamente:
   - `configuracion.json` desde `configuracion.ejemplo.json`.
   - `conocimiento\` desde `conocimiento.ejemplo\` (plantillas y reglas ficticias).
   - `..\Audios_nuevos\` e `..\Informes\`.
4. Cargar las plantillas del servicio: **Plantillas → "+ Nuevo estudio"** o **"Desde un Word…"**.
5. Cargar los médicos: **Médicos → "+ Agregar médico"**.

Arriba de la interfaz tiene que decir **"IA lista"**. Si dice que la IA está cerrada, abrir Ollama: los audios
que lleguen mientras tanto se transcriben y esperan.

### Opcional: informes de referencia

Si hay informes Word terminados sin audio (útiles para TC, PET u otros estudios con pocos ejemplos), ponerlos en
`..\Dataset\Informes word\` y usar **Plantillas → "Importar informes Word"** (o `python importar_informes.py <carpeta>`).

## 2. Acceso desde otras PC (opcional)

1. Ejecutar **`configurar_acceso.bat`** → opción 1 → elegir la contraseña de acceso remoto.
   Se crea `acceso_remoto.json` (secreto, no versionado) y `cliente\conexion.json` (canal de avisos para la app).
2. Ejecutar **`iniciar_servidor.bat`** en lugar de `interfaz.bat`. La primera vez descarga `cloudflared.exe`
   desde las *releases* oficiales de Cloudflare y abre el túnel.
3. La dirección pública (`https://….trycloudflare.com`) se publica sola en el canal secreto de ntfy.sh y se
   vuelve a publicar cada 3 horas.

Detalles de seguridad en [acceso-remoto.md](acceso-remoto.md).

## 3. PC del trabajo

1. Compilar la app (ver [compilacion.md](compilacion.md)) y dejar en `sistema\cliente\`:
   `Transcripcion.exe`, `Transcripcion.exe.config`, `Microsoft.Web.WebView2.Core.dll`,
   `Microsoft.Web.WebView2.WinForms.dll`, `runtimes\` y `conexion.json`.
2. Copiar la carpeta `cliente` completa a cada PC (por ejemplo a `Documentos\Transcripcion`). No requiere instalación
   ni permisos de administrador.
3. Abrir `Transcripcion.exe`, escribir el nombre de la PC y la contraseña de acceso remoto → **Conectar**.

Desde ese momento la app se actualiza sola cada vez que se reemplaza el `.exe` en `sistema\cliente\` del servidor.

Si la política del lugar bloquea ejecutables propios, se puede entrar desde Edge a la dirección del túnel con el
nombre de la PC y la contraseña, y subir los audios a mano.

## Solución de problemas

| Síntoma | Causa probable | Qué hacer |
|---|---|---|
| "No se pudo abrir el puerto 8765" | El servidor ya está abierto | Usar esa ventana o cerrarla. Otro puerto: variable `PUERTO_INTERFAZ` |
| La IA no responde | Ollama cerrado o modelo sin descargar | Abrir Ollama; `ollama pull gemma4:12b` |
| Error de memoria de la placa | Otro programa usa la GPU | Cerrar juegos/editores de video; ver `nvidia-smi` |
| "Método no encontrado" al abrir la app | Compilada con un método que .NET 4.8 no tiene | Ver [compilacion.md](compilacion.md#métodos-prohibidos) |
| "Windows protegió su PC" | El .exe vino de internet | *Más información → Ejecutar de todas formas*, o copiarlo desde un pendrive |
| La app no encuentra el servidor | Túnel caído o ntfy bloqueado | Revisar el panel `/admin`; en la app, *Opciones → Configuración… → Conexión → Cambiar dirección…* |
