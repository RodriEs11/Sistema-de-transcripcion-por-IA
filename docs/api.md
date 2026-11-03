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
| GET/POST | `/entrar` | Entrada desde la app (código de un solo uso) o desde un navegador. Con transcriptores: usuario + contraseña (y la PC si no se conoce); sin ninguno: PC + contraseña del sistema. Ver [usuarios.md](usuarios.md) |
| GET/POST | `/ingresar` | Usuario y contraseña cuando la PC ya está identificada (después del código de la app o de «Salir»). No es `/entrar` porque la app intercepta esa dirección |
| GET | `/salir` | Cierra la sesión. En el trabajo la PC queda identificada y la página pide solo usuario y contraseña |

## Casos

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/api/casos` | Lista de casos con estado, avisos, paciente, estudios, duración y permisos |
| GET | `/api/caso?nombre=` | Caso completo: dictado con palabras y tiempos, informe/borrador, marcas, avisos |
| GET | `/api/onda?nombre=` | Picos de la forma de onda |
| GET | `/api/word?nombre=` | Descarga del Word generado |
| POST | `/api/subir` | Subida de un audio desde la interfaz |
| POST | `/api/procesar` | Registra duraderamente la solicitud y regenera con la IA; falla con 503 si no puede confirmar la cola. Recuperación, pausas y límites en [cola del servidor](cola-servidor.md). |
| POST | `/api/borrador` | Guarda `{nombre, html, omisiones_ok?, revision?}`; responde `{ok:true, revision}`. Revisión obsoleta: 409; escritura fallida: 503; datos inválidos: 400. GET del caso incluye `borrador_revision`. Ver [compatibilidad](persistencia.md). |
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
| GET/POST | `/api/plantillas` | GET: secciones como las ve el transcriptor con `origen` (`general`, `propia`, `nueva`). POST `{secciones, destino: "mio" \| "todos"}`: lo cambiado va a sus plantillas propias o a `plantillas.md` (con copia previa) |
| POST | `/api/plantillas/general` | `{nombre}`: deja de usar la versión propia de una plantilla |
| POST | `/api/plantilla_word` | Convierte un `.docx` en una sección de plantilla |
| POST | `/api/importar` | Importa informes Word como referencias |
| GET | `/api/medicos` | Médicos y sus notas (las propias del transcriptor si tiene: `propias`, `generales`) |
| POST | `/api/medico` | Crea o actualiza las notas de un médico. `destino`: `todos` (por defecto), `mio` (solo para el transcriptor) o `general` (quita las propias) |
| GET | `/api/mi_pc` | Identidad de quien consulta (local/remoto, PC, permisos de panel, `con_usuarios`, `usuario`, `preferencias`) |
| GET | `/api/usuario/estilo` | Formato del Word propio y el general, fuentes permitidas, reglas propias, plantillas y médicos propios |
| POST | `/api/usuario/contrasena` | `{actual, nueva}` |
| POST | `/api/usuario/preferencias` | `{preferencias: {clave: valor}}` (las mismas claves que la página guarda en `localStorage`) |
| POST | `/api/usuario/formato` | `{formato: {opción: valor \| null}}` (`null` = usar el general) |
| POST | `/api/usuario/reglas` | `{reglas}`: reglas de dictado propias (se suman a las generales) |
| POST | `/api/mi_medico` | Médico predeterminado de la PC (vacío = automático por la voz) |
| GET | `/api/voces`, `/api/voces/muestras`, `/api/voces/agrupar` | Reconocimiento por la voz (ver [voz.md](voz.md)) |
| POST | `/api/voces/etiquetar`, `/api/voces/quitar` | Etiquetar audios con su médico / quitar una muestra |

## App del trabajo

| Método | Ruta | Descripción |
|---|---|---|
| POST | `/api/cliente/vincular` | `{pc, usuario, contrasena}`: vincula una PC con el usuario y la contraseña de un transcriptor (sin transcriptores: `usuario` vacío y la contraseña del sistema) y devuelve su llave (con usuario, también `codigo`: entrada de un solo uso que abre la página ya con ese transcriptor). La llave sola solo sirve para enviar audios, consultar el estado y actualizarse |
| GET | `/api/cliente/estado` | Estado del servidor y `app: {version, huella}` |
| POST | `/api/cliente/audio` | Envío de un audio tomado de `%TEMP%` o de la cola. Recibo confirmado: `{ok:true, nombre, duplicado}` después de publicar audio/metadatos, huella y encolado; la cola conserva el cifrado si falta esa confirmación. |
| GET | `/api/cliente/actualizacion` | Manifiesto de la carpeta `cliente\` (SHA-256 por archivo) |
| GET | `/api/cliente/archivo?ruta=` | Descarga de un archivo del manifiesto |
| POST | `/api/cliente/sesion` | Código de entrada de un solo uso (con la llave). `{"reconectar": true}`: con la persona que tenía la sesión abierta en esa PC |
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
| POST | `/api/admin/usuarios/crear` | `{nombre, contrasena}`: alta de un transcriptor (la contraseña inicial se cambia al entrar) |
| POST | `/api/admin/usuarios/contrasena` | `{usuario, contrasena}`: restablece la contraseña y cierra sus sesiones |
| POST | `/api/admin/usuarios/activo` | `{usuario, activo}`: desactiva (cierra sus sesiones) o reactiva |
| POST | `/api/admin/usuarios/nombre` | `{usuario, nombre}`: cambia el nombre visible (la carpeta de su estilo no cambia) |
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
