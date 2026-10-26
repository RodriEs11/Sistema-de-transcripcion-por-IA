# Historial de cambios

El formato sigue [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/).
El servidor se versiona por fecha; la app del trabajo, con [versionado semántico](https://semver.org/lang/es/).

## [Servidor 2026.10.30] — 2026-10-26

### Agregado
- **Microsoft Dev Tunnels como alternativa al túnel rápido de Cloudflare** (temporal, mientras `api.trycloudflare.com`
  no resuelve desde la PC del servidor). Se elige con `configurar_tunel.bat` / `.sh` (nuevo): descarga `devtunnel.exe`
  de Microsoft, inicia sesión con una cuenta de Microsoft o GitHub (solo en la PC del servidor) y crea un túnel
  persistente con acceso anónimo. La dirección (`https://<túnel>-8766.<región>.devtunnels.ms`) es **siempre la misma**.
  La opción 2 vuelve a Cloudflare. Queda en `acceso_remoto.json` → `tunel`.
- Puerto propio del túnel de Microsoft (`PUERTO_TUNEL`, 8766 por defecto, solo en 127.0.0.1): todo lo que entra por
  ahí cuenta como remoto (llave o sesión obligatoria), sin depender de los encabezados que agregue Microsoft.
- Si el túnel de Microsoft ya no existe (Microsoft los borra tras 30 días sin uso), el servidor lo crea de nuevo con
  el mismo nombre. Si la sesión venció, lo avisa (panel: «Sin sesión en Microsoft») y reintenta cada 5 minutos o al
  tocar «Reiniciar túnel».
- Panel: renglón «Servicio» en la tarjeta del túnel y estados nuevos (falta devtunnel, sin sesión, sin configurar,
  puerto ocupado).

### Arreglado
- Con `api.trycloudflare.com` sin resolver, el servidor tomaba `https://api.trycloudflare.com` como dirección del
  túnel, la publicaba en ntfy.sh cada 10 s (ntfy respondía 429) y la app del trabajo la podía adoptar. Ahora esa
  línea no cuenta como dirección, la espera entre intentos crece (10 s → 5 min), se avisa una sola vez que el DNS
  no encuentra el servicio y la misma dirección no se vuelve a publicar antes de una hora (salvo el botón del panel
  y la republicación cada 3 h).
- El botón «Volver a publicar» del panel de un dispositivo remoto comprueba el Origin también contra
  `X-Forwarded-Host`.

## [Servidor 2026.10.29] — 2026-10-26

### Agregado
- **Pausar una transcripción en curso** (solo en la PC del servidor): botón **Pausar** en el audio que se está
  transcribiendo, en la lista de informes y en la cola del panel de administración. Whisper se detiene al terminar
  el tramo actual y conserva lo transcrito; **Reanudar** sigue desde ahí. Mientras tanto los audios que siguen en
  la cola esperan. Las PC del trabajo ven el estado «en pausa» pero no tienen el botón (el servidor responde 403).
- Mientras transcribe, la lista muestra por dónde va («Transcribiendo el audio · 1:10 de 3:20»).
- Título de la ventana del servidor: «transcripción EN PAUSA».

### Cambiado
- Un caso en pausa se puede borrar (el trabajador lo deja y sigue con el próximo).
- El reinicio desde el panel no espera a una transcripción en pausa: ese audio queda «sin procesar» y lo demás
  de la cola se retoma.
- El tiempo de Whisper de `actividad.csv` y de las estadísticas no cuenta el rato en pausa.

## [Servidor 2026.10.28] — 2026-10-26

### Agregado
- **El servidor corre en Linux** ([docs/linux.md](docs/linux.md)): `instalar.sh` (entorno, dependencias, placa de video, Ollama y modelo, Whisper), `interfaz.sh`, `iniciar_servidor.sh` (baja `cloudflared` para Linux) y `configurar_acceso.sh`, equivalentes a los .bat, con el reinicio desde el panel (código 75).
- `servicio.sh`: el servidor como servicio de systemd del usuario (arranca solo, se vuelve a abrir si se cae, el panel lo puede reiniciar).
- `plataforma.py`: lo que cambia entre Windows y Linux en un solo lugar (nombres de los scripts, cloudflared, abrir archivos, rutas).
- `dispositivo_whisper` en `configuracion.json` (opcional, `"cpu"` sin placa NVIDIA).

### Cambiado
- En Linux, las rutas de `configuracion.json` con barras de Windows (`..\\Informes`) se leen como `../Informes`.
- Bibliotecas de CUDA instaladas con pip: en Linux se agregan a `LD_LIBRARY_PATH` (scripts) o se cargan a mano.
- Panel y página de informes nombran los scripts del sistema donde corre el servidor (.sh en Linux) y esconden «Abrir…» en un Linux sin escritorio.
- Linux: `kill`/`systemctl stop` apagan en orden (cierran el túnel), igual que Ctrl+C.
- Windows: sin cambios de comportamiento.

## [Servidor 2026.10.27] — 2026-10-26

### Agregado
- Panel de administración, tarjeta **Mantenimiento**: archivos que cambiaron desde que arrancó el servidor («cambios sin tomar»), commit en uso y en la carpeta, archivos sin commitear, y botón **Reiniciar servidor** (ahora, en 1 o en 5 minutos; espera a que termine lo que se procesa, prueba antes el código nuevo, retoma la cola al volver).
- **Mensaje a las PC del trabajo**: cartel en la página de informes, con duración; el aviso de reinicio muestra la cuenta regresiva.
- **Cola de procesamiento** en vivo: etapa, cuánto lleva, orden y cuánto falta.
- **Casos abiertos ahora** con botón **Liberar** (la PC que lo tenía deja de poder guardar y su página se cierra con un aviso).
- Página **Correcciones** (`/admin/correcciones`): lo más corregido de lo que escribe la IA, en general o por médico, con **Convertir en regla** (agrega a `reglas_dictado.md`, con copia).
- Estadísticas: **tiempos de procesamiento** (IA, Whisper por minuto de audio, total, por semana, los más lentos y errores).

### Cambiado
- `iniciar_servidor.bat` e `interfaz.bat` vuelven a abrir el servidor cuando termina con el código 75 (reinicio desde el panel).
- La página de informes avisa «El servidor se está reiniciando» en lugar de «Sin conexión» durante un reinicio pedido desde el panel.

## [Servidor 2026.10.26] — 2026-10-26

### Cambiado
- Lista de informes angosta: los íconos del pie (Configuración y Administración) pasan a una segunda fila en lugar de salirse de la columna.
- Panel de administración y estadísticas: un solo botón «Salir del panel» (con aspecto de botón) en lugar de «Salir del panel» y «Volver a los informes»; desde una PC del trabajo además cierra la sesión del panel.
- Página de contraseña del panel y avisos del panel: «Volver a los informes» es un botón, no un enlace subrayado.
- Estadísticas: «Por médico» y «Por estudio» van una debajo de la otra a todo el ancho; los estudios combinados se cortan solo entre estudio y estudio (cada uno con su «+»).

## [Servidor 2026.10.25] — 2026-10-25

### Agregado
- Barra del informe compacta para pantallas de 1366 × 768: dos filas finas que se achican por pasos (menú «Más», sin teclas, solo íconos) en lugar de encimarse; botón «?» con los colores y los atajos.
- Botón para ocultar la lista de informes (queda un riel con el estado de la IA, los informes para revisar y la configuración).
- Ventana de Configuración: tema, lista, tamaño del texto, referencias y atajos, paneles, velocidad inicial, saltos, retroceso al reanudar, seguir el audio, explicación de las marcas, y las opciones de la app del trabajo.
- Panel de administración local (`/admin`): estado del servidor, túnel, PC vinculadas, errores y avisos recientes, acciones de mantenimiento.
- Página de estadísticas (`/admin/estadisticas`): % corregido, tiempo de revisión, desglose por semana, médico y estudio.
- Acceso al panel desde las PC del trabajo con contraseña propia, sesión atada a la PC y bloqueo por intentos.
- Medición del tiempo activo de revisión por caso.
- Nombre del paciente, estudios y duración del audio en la lista de casos.
- Vista previa idéntica al Word (F9) con editor de formato (negrita, cursiva, subrayado, color, alineación).
- Hoja A4 con márgenes configurables y títulos centrados.
- Borrado de informes (individual y en lote) con permisos por PC.
- Paneles ajustables, ventanas modales propias y estados vacíos/de espera en toda la interfaz.
- Autocorrecciones de Word (Normal.dotm) en el editor, aplicadas con su formato.
- Archivos de ejemplo (`configuracion.ejemplo.json`, `conocimiento.ejemplo/`) para arrancar desde un clon limpio.

### Cambiado
- Mensajes de error técnicos traducidos a mensajes claros para el usuario.
- La subida de audios nunca interpreta como JSON una página HTML de error del túnel.

## [Servidor 2026.10.24] — 2026-10-24

### Agregado
- Interfaz web de revisión con audio sincronizado, forma de onda y explicación de cada marca.
- Detección de tramos no transcritos y segunda pasada de Whisper.
- Orden automático de estudios y controles de Bi-Rads, ACR, lateralidad y términos clave.
- Aprendizaje a partir de informes revisados y correcciones frecuentes.
- Acceso remoto por túnel de Cloudflare con descubrimiento por ntfy.sh y autenticación por PC.
- Consola con eventos por área, registro diario y `actividad.csv`.

## App del trabajo

### [1.12] — 2026-10-26
- Acepta direcciones de Microsoft Dev Tunnels (`*.devtunnels.ms`) publicadas en el canal de avisos, además de las de
  Cloudflare; ya no acepta `api.trycloudflare.com`.
- Saltea la página de aviso («anti-phishing») de Dev Tunnels: encabezado `X-Tunnel-Skip-AntiPhishing-Page` en los
  pedidos de la app y, en WebView2, en todo lo que pide la pantalla del Servidor.
- Textos: «termina en devtunnels.ms o en trycloudflare.com»; el error 530 ya no nombra a Cloudflare.

### [1.11] — 2026-10-26
- Si el Servidor está caído o reiniciándose, la ventana ya no muestra la página de error de Cloudflare (ni la de Edge sin conexión): muestra un cartel propio con lo que pasó (el programa del Servidor no responde, el canal está cerrado, la dirección cambió, sin internet), recuerda que los audios se siguen tomando, y vuelve sola a la pantalla cuando el Servidor responde. Botón «Reintentar ahora». Queda anotado en el registro.
- Las notificaciones de Windows muestran el ícono nuevo: la app tiene una identidad propia para Windows (`Transcripcion.Informes.2`, registrada con un PNG del ícono) en lugar de la que Windows tenía guardada con el ícono viejo, y el globo lleva el ícono de la app en grande en lugar de la «i». Los accesos directos anclados se marcan con la misma identidad para que la barra de tareas no muestre dos botones.

### [1.10] — 2026-10-26
- La barra de tareas muestra el ícono nuevo: la primera vez que abre cada versión, la app le pide a Windows que vuelva a leer el ícono de `Transcripcion.exe` y de sus accesos directos (el anclado a la barra de tareas seguía con el ícono viejo en la memoria de íconos de Windows).
- Se quitó de la barra superior la casilla «Tomar los audios del sistema automáticamente»: está en Configuración (y en el menú del ícono junto al reloj).

### [1.9] — 2026-10-25
- «Configuración…» en Opciones (y en el ícono junto al reloj): abre la ventana de Configuración de la pantalla con las opciones de esta PC (abrir con Windows, toma de audios, avisos de informe listo, modo compacto, carpeta de los Word, registro de envíos, autocorrección, dirección del Servidor, desconectar, actualización). Sin pantalla cargada, abre una ventana propia.
- Carpeta de los Word descargados configurable y aviso de «informe listo» que se puede apagar.
- El menú Opciones queda con Configuración, Cargar audio y Volver a cargar la pantalla.

### [1.8] — 2026-10-25
- Ícono nuevo ("Marcas de revisión") en el .exe, la ventana y junto al reloj; el estado de la conexión se muestra con un punto de color sobre el ícono.
- La interfaz web muestra el mismo ícono en la pestaña del navegador.

### [1.7] — 2026-10-25
- Créditos solo en el menú Opciones; la línea de versión muestra únicamente el número.

### [1.6] — 2026-10-25
- "Cargar audio" pasa por la cola cifrada de la app: funciona sin conexión y se envía al volver.
- Nuevo ícono de "sin conexión".

### [1.5] — 2026-10-25
- Lectura de las autocorrecciones con formato del Normal.dotm de Word (lector ZIP propio, compatible con .NET 4.8).

### [1.4] — 2026-10-25
- Menú de Opciones que se cierra al hacer clic fuera (incluida la vista web).
- Tamaño compacto por defecto de 320 × 620 y botón de actualizar como ícono.

### [1.3] — 2026-10-25
- Botones con íconos en modo compacto.
- Cambio de dirección del servidor con conexión inmediata.

### [1.2] — 2026-10-24
- Actualización automática: manifiesto con SHA-256, autoprueba de la versión nueva contra el .NET de la PC,
  instalación cuando la app no se usa y vuelta atrás automática si la versión nueva falla.

### [1.1] — 2026-10-24
- Modo compacto siempre visible y tema claro/oscuro sincronizado con la página.

### [1.0] — 2026-10-24
- Primera versión: toma automática de audios desde `%TEMP%`, cola cifrada con DPAPI, notificaciones y descarga del Word.
