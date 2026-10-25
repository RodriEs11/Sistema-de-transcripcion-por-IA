# Historial de cambios

El formato sigue [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/).
El servidor se versiona por fecha; la app del trabajo, con [versionado semántico](https://semver.org/lang/es/).

## [Servidor 2026.10.25] — 2026-10-25

### Agregado
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
