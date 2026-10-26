# API HTTP

El servidor escucha en `http://127.0.0.1:8765`. Todas las respuestas son JSON (salvo páginas y archivos) y llevan
`Cache-Control: no-store`. Los pedidos que llegan por el túnel requieren autenticación ([acceso-remoto.md](acceso-remoto.md#autenticación)).

Los casos se identifican con el parámetro o campo `nombre` (validado: sin rutas ni caracteres especiales).

## Páginas

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/` | Interfaz de revisión (`web/index.html`) |
| GET | `/admin` | Panel de administración (solo local o con contraseña del panel) |
| GET | `/admin/estadisticas` | Estadísticas |
| GET | `/admin/correcciones` | Lo más corregido |
| GET/POST | `/entrar` | Entrada desde la app (código de un solo uso) o desde un navegador (PC + contraseña) |
| GET | `/salir` | Cierra la sesión del navegador |

## Casos

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/api/casos` | Lista de casos con estado, avisos, paciente, estudios, duración y permisos |
| GET | `/api/caso?nombre=` | Caso completo: dictado con palabras y tiempos, informe/borrador, marcas, avisos |
| GET | `/api/onda?nombre=` | Picos de la forma de onda |
| GET | `/api/word?nombre=` | Descarga del Word generado |
| POST | `/api/subir` | Subida de un audio desde la interfaz |
| POST | `/api/procesar` | Regenerar el informe con la IA |
| POST | `/api/borrador` | Autoguardado del borrador |
| POST | `/api/caso/bloquear` | Toma o renueva el bloqueo del caso (y suma tiempo de revisión `rev`) |
| POST | `/api/caso/soltar` | Libera el bloqueo |
| POST | `/api/caso/pausar`, `/api/caso/reanudar` | Pausa o reanuda la transcripción en curso `{nombre}` (solo local; por el túnel, 403) |
| POST | `/api/caso_medico` | Cambia el médico de un caso |
| POST | `/api/paciente` | Corrige el nombre del paciente |
| POST | `/api/finalizar` | Guarda el Word, aprende y registra estadísticas |
| POST | `/api/borrar` | Borra uno o varios casos `{"nombres": [...]}` |
| POST | `/api/abrir` | Abre el Word en la PC del servidor (solo local) |

## Formato y vista previa

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/api/formato` | Reglas de negrita y palabras que identifican títulos de estudio |
| POST | `/api/vista_previa` | Párrafos con formato tal como saldrán en el Word |
| POST | `/api/formato_caso` | Guarda (o borra con `null`) el formato manual de un caso |
| POST | `/api/formato_caso/agregar` | Agrega párrafos con formato (autocorrecciones de Word) |

## Conocimiento

| Método | Ruta | Descripción |
|---|---|---|
| GET/POST | `/api/plantillas` | Lee / guarda `plantillas.md` (con copia previa) |
| POST | `/api/plantilla_word` | Convierte un `.docx` en una sección de plantilla |
| POST | `/api/importar` | Importa informes Word como referencias |
| GET | `/api/medicos` | Médicos y sus notas |
| POST | `/api/medico` | Crea o actualiza las notas de un médico |
| GET | `/api/mi_pc` | Identidad de quien consulta (local/remoto, PC, permisos de panel) |
| POST | `/api/mi_medico` | Médico predeterminado de la PC |

## App del trabajo

| Método | Ruta | Descripción |
|---|---|---|
| POST | `/api/cliente/vincular` | Vincula una PC con la contraseña y devuelve su llave |
| POST | `/api/cliente/sesion` | Código de un solo uso para abrir la interfaz |
| GET | `/api/cliente/estado` | Estado del servidor y `app: {version, huella}` |
| POST | `/api/cliente/audio` | Envío de un audio tomado de `%TEMP%` o de la cola |
| GET | `/api/cliente/actualizacion` | Manifiesto de la carpeta `cliente\` (SHA-256 por archivo) |
| GET | `/api/cliente/archivo?ruta=` | Descarga de un archivo del manifiesto |
| POST | `/api/cliente/aviso` | La app informa un problema (queda en el registro) |

## Administración

Solo locales (`127.0.0.1` con `Host` local) o con sesión del panel remoto. Los POST exigen `X-Panel: 1` y un
`Origin` de la misma página.

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/api/admin/estado` | Estado completo para el panel |
| GET | `/api/admin/estadisticas?dias=N` | Estadísticas del período (`0` = todo) |
| POST | `/api/admin/entrar`, `/api/admin/salir` | Sesión del panel desde el trabajo |
| POST | `/api/admin/tunel/reiniciar` | Reinicia `cloudflared` (dirección nueva) |
| POST | `/api/admin/tunel/publicar` | Vuelve a publicar la dirección en ntfy |
| POST | `/api/admin/pc/anular` | Anula una PC vinculada |
| POST | `/api/admin/contrasena` | Cambia la contraseña de acceso remoto |
| POST | `/api/admin/contrasena_admin`, `/api/admin/contrasena_admin/quitar` | Contraseña del panel remoto (solo local) |
| POST | `/api/admin/sesiones_admin/cerrar` | Cierra las sesiones del panel remoto (solo local) |
| POST | `/api/admin/abrir` | Abre el registro o una carpeta en el Explorador (solo local) |
| GET | `/api/admin/correcciones?dias=N&medico=X&puntuacion=1` | Cambios más repetidos entre la IA y el informe final |
| POST | `/api/admin/reinicio` | Programa el reinicio `{en: segundos, avisar, texto}` (prueba antes el código) |
| POST | `/api/admin/reinicio/cancelar`, `/api/admin/reinicio/ya` | Cancela el reinicio o lo hace sin esperar |
| POST | `/api/admin/mensaje`, `/api/admin/mensaje/quitar` | Cartel en las PC `{texto, minutos, tipo: aviso\|info}` |
| POST | `/api/admin/caso/liberar` | Saca un caso abierto a la PC que lo tiene `{nombre}` |
| POST | `/api/admin/caso/pausar`, `/api/admin/caso/reanudar` | Pausa o reanuda la transcripción en curso `{nombre}` (solo local) |
| POST | `/api/admin/correcciones/regla` | Agrega un renglón a `reglas_dictado.md` `{texto}` (solo local) |
