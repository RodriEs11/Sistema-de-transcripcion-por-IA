# Historial de cambios

El formato sigue [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/).
El servidor se versiona por fecha; la app del trabajo, con [versionado semántico](https://semver.org/lang/es/).

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
