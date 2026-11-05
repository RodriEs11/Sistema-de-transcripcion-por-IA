# Historial de cambios

El formato sigue [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/).
El servidor se versiona por fecha; la app del trabajo, con [versionado semántico](https://semver.org/lang/es/).
Cada PR fusionado deja sus notas en «Sin publicar», bajo `### App` y/o `### Servidor` con categorías `####`
(Agregado, Cambiado, Corregido, Quitado, Interno). Al preparar una entrega, `herramientas/subir_version.py` las pasa
a las entradas fechadas. Ver [docs/versiones.md](docs/versiones.md).

## Sin publicar

### App

#### Cambiado
- Botón de administración (#37): ahora lleva un escudo con tilde en lugar del engranaje, para no confundirlo con
  «Configuración». Lo mismo en el acceso rápido «Administración» del Inicio.

### Servidor

#### Cambiado
- Página principal: el ícono del botón de administración (ver App). Sin cambios en la API ni en el procesamiento.

#### Agregado
- Panel de administración → Mantenimiento: al lado del commit «En uso» y «En la carpeta» aparece la etiqueta de la
  entrega publicada (por ejemplo `servidor-v2026.11.16`), para saber qué entrega está corriendo. Funciona con git
  instalado y también leyendo la carpeta `.git` directamente.

#### Interno
- Versiones por entrega ([docs/versiones.md](docs/versiones.md)): los PR ya no suben números; se suben juntos en una
  rama `release/…` con `herramientas/subir_version.py`, y cada entrega queda marcada con etiquetas `app-vX` /
  `servidor-vY`. `herramientas/verificar_versiones.py` comprueba además el esquema, el mes del servidor, que ninguna
  versión sea anterior a la última etiqueta y, con `--entrega`, que no queden notas en «Sin publicar».

## [App 1.28] — 2026-11-05

Acompaña al Servidor 2026.11.15.

### Cambiado
- Pantalla de Inicio (#29): «Para revisar» ahora va del estudio más nuevo al más antiguo. La tarjeta de arriba
  («El más reciente») y el botón de la cifra «para revisar» abren el último que llegó, y uno que entra con la app
  abierta aparece arriba sin reiniciar. La lista lateral no cambia (ya mostraba primero el más nuevo).

## [Servidor 2026.11.15] — 2026-11-05

Sirve la página de la App 1.28.

### Cambiado
- Página principal: el orden de «Para revisar» en el Inicio (ver App 1.28). Sin cambios en la API ni en el procesamiento.

### Pruebas
- Nueva `pruebas/orden_inicio.cjs`, incluida en la regresión de navegador del CI: orden inicial, tarjeta, cifra y
  llegada de un estudio nuevo.

## [App 1.27] — 2026-11-05

Acompaña al Servidor 2026.11.14.

### Quitado
- Barra lateral de la página principal: la lista desplegable «Médico de los audios que subas» (#30). Los audios que
  se cargan desde la página llegan sin médico y lo reconoce el servidor por la voz; si hace falta, se cambia en la
  barra del informe como siempre. Los audios que ya estaban esperando sin conexión se envían igual, sin médico.

## [Servidor 2026.11.14] — 2026-11-05

Sirve la página de la App 1.27.

### Quitado
- El médico fijo por PC (#30): la ruta `POST /api/mi_medico`, el campo `medico` de `GET /api/mi_pc` y de las PC en el
  estado del panel, y la columna «Médico de sus audios» de la tabla de PC del panel de administración. Los audios que
  manda la app sola tampoco reciben ya ese médico: todos se reconocen por la voz.
- El valor `medico_pc` que quedó guardado en `acceso_remoto.json` se borra solo en la próxima escritura del archivo.
  Una página o app anterior que todavía llame a `/api/mi_medico` recibe 404, sin otro efecto.

## [App 1.26] — 2026-11-04

Acompaña al Servidor 2026.11.13. Es la entrega de los ajustes de interfaz del 04/11 (grupo #42): reúne en esta misma
versión los cambios de la página principal que se sumen antes de distribuirla.

### Agregado
- Selector de volumen en el reproductor (#31): en la barra, un parlante a la derecha de **+3s** que silencia y vuelve
  al nivel anterior (el ícono cambia con el nivel y en 0 % se ve tachado). Al pasar el mouse aparece debajo, flotando,
  un deslizador de 0 % a 100 % con el porcentaje (de a 5 %, también con la rueda del mouse; con el teclado, Tab desde
  el parlante y las flechas). Como flota, no ocupa lugar en la barra ni se encima con los otros controles. El volumen se guarda en cada PC (no sigue al transcriptor, porque depende de sus
  parlantes o auriculares), se mantiene al pasar de un informe a otro y vuelve al 100 % con «Volver a la configuración
  original de la pantalla». También se aplica al arrastrar sobre la onda y a las muestras de voz de Médicos.

## [Servidor 2026.11.13] — 2026-11-04

Sirve la página de la App 1.26 (entrega de ajustes de interfaz del 04/11, grupo #42). Sin cambios de API ni de datos.

### Agregado
- Selector de volumen en el reproductor de la página de revisión (#31); ver App 1.26.

## [Servidor 2026.11.12] — 2026-11-03

Etapa 9 del [refactor por etapas](docs/refactor.md). Reorganización interna, sin cambios visibles (contratos, suite y
pruebas de navegador en verde sin regenerar).

### Cambiado
- Todo el paquete `transcripcion/` tiene formato automático (`ruff format`) y reglas de calidad más estrictas
  (imports ordenados, nombres claros, líneas largas partidas, funciones en lugar de lambdas asignadas).
- El CI revisa también los tipos (mypy) y la cobertura de las pruebas, con un piso que no puede bajar.

## Instalación — 2026-11-03 (scripts y herramientas)
- Etapa 2b del [refactor por etapas](docs/refactor.md): los scripts de operación pasaron a `scripts/`
  (`configurar_acceso`, `configurar_tunel`, mantenimiento de la cola y del aprendizaje, activación, rollback,
  `crear_entorno_pruebas`) y las herramientas de desarrollo a `herramientas/` (`fase1_transcribir`,
  `verificar_versiones`, mediciones, GPU, `comparar_il`). Los `.bat`/`.sh` siguen con el mismo nombre y en el mismo
  lugar. Desde consola: `python scripts/mantenimiento_cola.py …`, `python herramientas/verificar_versiones.py`.
  Sin cambios de versión: no cambia lo que corre en el servidor ni en la app.

## [App 1.25] — 2026-11-03

Acompaña al Servidor 2026.11.11 (etapas 7 y 8 del [refactor por etapas](docs/refactor.md)).

### Cambiado
- La página que muestra la app (revisión) tiene sus estilos y su programa en `web/css/principal/` y
  `web/js/principal/`, separados por tema. Se ve y funciona igual; la versión nueva sigue la regla de que todo cambio
  de la página que usa la app lleva versión de la app.
- El código de la ventana principal (`VentanaPrincipal.cs`, ~1.500 líneas) quedó partido por responsabilidad en
  `VentanaPrincipal.<Parte>.cs` (barra, conexión, página, mensajes con la página, aviso, ícono junto al reloj,
  actualización, modo compacto, audios, autocorrección, tema, configuración, acciones) y `RelojUi.cs`. Mismo
  programa: la compilación de antes y la de después tienen el mismo IL (etapa 8 del refactor).

## [Servidor 2026.11.11] — 2026-11-03

Etapa 7 del [refactor por etapas](docs/refactor.md). Reorganización interna, sin cambios visibles: la página de
revisión se ve y funciona igual (mismas capturas de la lista, de un caso abierto y de la vista previa). No requiere
versión nueva de la app: el ejecutable no cambia.

### Cambiado
- Los estilos y el script de la página de revisión salieron de `web/index.html` a `web/css/principal/` y
  `web/js/principal/`, en partes por área (lista, inicio, cargar audios, marcas, audio, atajos, borrador, médicos,
  voces, plantillas, onda, configuración, Mi cuenta…). El servidor las une en orden y las envía como
  `/css/principal.css` y `/js/principal.js`, un único script como antes.

## [Servidor 2026.11.10] — 2026-11-03

Etapa 6c del [refactor por etapas](docs/refactor.md). Reorganización interna, sin cambios visibles: mismas rutas y
mismas respuestas (contratos en verde sin regenerar; un servidor simulado de antes y de después respondió igual a 36
pedidos de la página, la app del trabajo y el panel).

### Cambiado
- Las rutas HTTP salieron de `servidor.py` a `transcripcion/http/`: una tabla (`tabla.py`) con cada ruta y la función
  que la atiende, agrupadas por área (casos, edición, audios, app del trabajo, conocimiento, voces, usuario, panel,
  acceso). `servidor.py` queda con el arranque (~310 líneas).
- Las páginas de entrar y del panel desde el trabajo pasaron a `web/plantillas/`.
- `transcripcion/http/` se revisa con reglas más estrictas de ruff y con `ruff format` en el CI.

## [Servidor 2026.11.9] — 2026-11-03

Etapa 6b del [refactor por etapas](docs/refactor.md). Reorganización interna, sin cambios visibles (contratos en
verde sin regenerar; panel, estadísticas, correcciones y actualización de la app probados con un servidor simulado).

### Cambiado
- Los módulos de la raíz que usa el servidor pasaron al paquete: `remoto` y `admin` a `transcripcion/acceso/`;
  `mantenimiento`, `estadisticas` y `app_cliente` a `transcripcion/operacion/`; `aprender` y `correcciones` a
  `transcripcion/aprendizaje/`; `importar_informes` a `transcripcion/conocimiento/importar.py`. Los datos
  (contraseñas, sesiones, historial, ejemplos, referencias) siguen en los mismos archivos de la carpeta del sistema.
- `aprender.py` e `importar_informes.py` siguen en la raíz como lanzadores de consola: se usan igual que antes.

## [Servidor 2026.11.8] — 2026-11-03

Etapa 6a del [refactor por etapas](docs/refactor.md). Reorganización interna, sin cambios visibles (contratos en
verde sin regenerar; probado además con un servidor simulado: subir, pausar, reanudar, panel y mensajes).

### Cambiado
- Los servicios salieron de `servidor.py` a objetos del paquete que reciben lo que usan: el trabajador
  (`procesamiento/trabajador.py`), la lista y el caso abierto (`casos/vista.py`), el borrado (`casos/borrado.py`), la voz
  (`voz/servicio.py`; `voces.py` pasa a `voz/huellas.py`), el estado de la IA (`operacion/ia.py`), el reinicio y los
  mensajes (`operacion/reinicio.py`) y «Guardar Word y aprender» (`informe/guardado.py`, con el Word en `informe/word.py`).
  `servidor.py` baja a ~1.700 líneas: arranque, HTTP y panel.

## [Servidor 2026.11.7] — 2026-11-03

Etapa 5 del [refactor por etapas](docs/refactor.md). Reorganización interna, sin cambios visibles: mismas
pantallas, mismas respuestas HTTP, misma cola y mismas pausas (contratos en verde sin regenerar).

### Cambiado
- Los archivos de cada caso (nombre, origen, médico, transcriptor, estudios, duración, tiempo de revisión, voz,
  avisos) los maneja un objeto `Casos` (`transcripcion/casos/repositorio.py`), y el estado del procesamiento (etapa
  de cada caso, cola, pausas, tiempos estimados) un objeto `Procesamiento` (`transcripcion/procesamiento/estado.py`).
  Los crea el arranque; antes eran unas 20 variables globales de `servidor.py`.

## [Servidor 2026.11.6] — 2026-11-03

Etapa 4 del [refactor por etapas](docs/refactor.md). Reorganización interna: mismas transcripciones, marcas y
respuestas HTTP (contratos en verde sin regenerar).

### Cambiado
- Whisper (CUDA, carga del modelo, lectura de audio, vocabulario, transcripción) pasa a
  `transcripcion/asr/whisper.py`, la segunda pasada a `transcripcion/asr/huecos.py` y la normalización de números,
  horas y niveles a `transcripcion/texto/normalizacion.py`. `fase1_transcribir.py` queda solo como herramienta de
  evaluación y prueba de la GPU (`--verificar`, la usan los instaladores).
- La caché de transcripción se firma con el código nuevo: tras actualizar, **«Regenerar» un caso que ya existía
  vuelve a pasar una vez por Whisper** (tarda lo mismo que la primera vez). Los casos nuevos no cambian.

## [Servidor 2026.11.5] — 2026-11-03

Etapa 3 del [refactor por etapas](docs/refactor.md). Reorganización interna, sin cambios visibles: mismo prompt,
mismas marcas y mismos avisos (contrato del núcleo en verde sin regenerar).

### Cambiado
- `nucleo.py` se partió en `transcripcion/conocimiento/` (archivos, plantillas, médicos), `transcripcion/ia/`
  (prompt, ejemplos, cliente de Ollama), `transcripcion/controles/` (marcas, controles clínicos, avisos, orden de
  estudios), `transcripcion/informe/formato.py` (negritas) y `transcripcion/texto/palabras.py`.
- `instalar.sh` (Linux) prepara la carpeta `conocimiento/` llamando a `preparar_conocimiento()`. Antes lo hacía
  importando `nucleo`, que desde el Servidor 2026.11.3 ya no tiene ese efecto (el servidor la creaba igual al arrancar).

## [Servidor 2026.11.4] — 2026-11-03

Etapa 2a del [refactor por etapas](docs/refactor.md). Reorganización interna, sin cambios visibles: mismas
pantallas, mismas respuestas HTTP y mismos archivos de datos (contratos en verde sin regenerar).

### Cambiado
- Nuevo paquete `transcripcion/` con los módulos que ya eran independientes: `base/` (plataforma, persistencia,
  registro), `ajustes`, `casos/` (borradores, paciente, índice), `procesamiento/` (cola, lotes, caché de
  transcripción), `aprendizaje/` (almacén, cola pendiente) y `acceso/` (usuarios). La tabla de equivalencias está
  en `docs/refactor.md`. Los registros, `usuarios.json`, `conocimiento/` y demás datos siguen en la carpeta del sistema.
- El aviso del panel «código cambiado: hace falta reiniciar» y la prueba previa al reinicio incluyen el paquete.

### Corregido
- `pruebas/validar_gpu_real.py` y `pruebas/comparar_cpu_gpu.py` no arrancaban desde que `nucleo.py` importa los
  usuarios: copiaban una lista fija de archivos sin `usuarios.py`. Ahora copian el paquete.

## [Servidor 2026.11.3] — 2026-11-03

Etapa 1 del [refactor por etapas](docs/refactor.md). Reorganización interna, sin cambios visibles: mismas
pantallas, mismas respuestas HTTP (contratos en verde sin regenerar) y misma configuración.

### Cambiado
- Importar `servidor.py` ya no lee `configuracion.json` ni crea `Audios_nuevos` e `Informes/revision/datos`, e
  importar `nucleo.py` ya no crea `conocimiento/`. Ahora lo hace el arranque: `ajustes.cargar()` (configuración
  + `PUERTO_INTERFAZ`, `PUERTO_TUNEL`, `SIMULAR_IA`), `ajustes.preparar_carpetas()` y
  `nucleo.preparar_conocimiento()`; `servidor.configurar(ajustes)` reemplaza la lectura al importar.
- La prueba del código antes de reiniciar desde el panel también lee la configuración: un `configuracion.json`
  roto no deja reiniciar (antes lo detectaba al importar el servidor).

### Corregido
- Varias pruebas automáticas (`test_usuarios`, `test_cola_procesamiento`, `test_aprendizaje_pendiente`,
  `medicos.cjs`, `usuarios.cjs`) usaban, sin querer, las carpetas reales de la instalación: corridas dentro de
  `sistema\` podían escribir un Word de prueba en `Informes`, registros en `registros/`, `cliente/conexion.json`, y
  leían las plantillas reales. Ahora trabajan en carpetas temporales; una prueba nueva verifica que ningún módulo
  escriba nada al importarse.

## Pruebas y herramientas — 2026-11-03
- Red de seguridad para el refactor por etapas ([plan](docs/refactor.md), [ADR 0001](docs/adr/0001-modularizar-por-etapas.md)):
  contrato HTTP de caja negra (servidor real en subproceso y modo simulado, flujo completo de un caso) y contrato del
  núcleo (marcas, prompt, normalización, orden de estudios y párrafos del Word sobre casos ficticios).
- Lint con ruff en el CI (`pyproject.toml`): por ahora solo errores reales. Se quitaron 2 imports y 3 variables sin
  usar y 2 `f` de cadenas sin variables; sin cambios funcionales ni de versión.
- Registro de decisiones de arquitectura en `docs/adr/`.

## [Servidor 2026.11.2] — 2026-11-03

### Corregido
- Con transcriptores, cuando el servidor se caía o se reiniciaba, la app volvía a abrir la pantalla con un código de entrada nuevo y esa sesión sin usuario reemplazaba a la de la persona: había que volver a entrar. Ahora, si la pantalla ya tiene la sesión de un transcriptor, se conserva (también con la App 1.23).
- `/api/cliente/sesion` acepta `{"reconectar": true}`: el código abre la pantalla con la persona que tenía la sesión abierta en esa PC (para cuando cambia la dirección del túnel y la pantalla pierde su cookie). Después de «Cerrar sesión» o de vencer la sesión no devuelve a nadie.

## [App 1.24] — 2026-11-03

### Corregido
- Al reconectarse (servidor caído o reiniciado, dirección nueva) pide la entrada con `reconectar`: la pantalla vuelve con la misma persona sin pedir usuario y contraseña. Al abrir la app de cero se sigue pidiendo.

## Instalación — 2026-11-03
- `iniciar_servidor.bat` e `interfaz.bat` ponen `.venv\Scripts` al principio del PATH después de activar el entorno.
  Si la carpeta se mueve de unidad (D: → E:), `activate.bat` conserva la ruta vieja y `python` terminaba siendo el
  del sistema (`No module named 'numpy'`). El arreglo ya estaba aplicado a mano en la instalación desde el 01/11.
  Sin cambios de versión.

## [Servidor 2026.11.1] — 2026-11-02

Promovido desde la rama `experimental` (PR #9, probado en el entorno de pruebas). Sin transcriptores
creados el comportamiento es el de antes: se activa recién al crear el primero en el panel.

### Agregado
- Transcriptores: cada persona entra con su usuario y su contraseña (PBKDF2, `usuarios.json`), también en la PC del servidor. Altas, restablecer contraseña, cambiar nombre y desactivar desde Panel → Transcriptores; la contraseña inicial se cambia en la primera entrada. Con transcriptores, la contraseña compartida ya no sirve para entrar ni para vincular PC; la llave de cada PC queda solo para enviar audios, consultar el estado y actualizarse.
- Estilo propio en `conocimiento/usuarios/<clave>/`: plantillas y notas de cada médico que reemplazan a las generales, reglas de dictado que se suman, formato del Word y preferencias de pantalla. Al guardar plantillas o notas se pregunta «¿Solo para mí o para todos?»; botón «Volver a la general».
- La IA usa primero los ejemplos del mismo transcriptor y marca los de otro como ajenos. Una corrección repetida por una sola persona queda en su `correcciones_aprendidas.md`; pasa a general cuando la hacen dos.
- Cada caso se arma con el estilo de quien usa la página en esa PC; si lo abre otra persona, aviso y «Regenerar con mi estilo».
- Página: Mi cuenta (contraseña, formato del Word, reglas propias en lista con «Añadir regla»), «Cerrar sesión» y nombre de quien transcribe arriba de la lista. `/ingresar` pide el usuario cuando la PC ya está identificada.
- Sesiones guardadas por huella en `sesiones.json` (un reinicio no obliga a volver a entrar); se renuevan con el uso y se cierran tras 12 h sin consultas.
- Columna `usuario` en `registros/actividad.csv` y tabla `ejemplo_usuario` en el historial (se crean solas).

### Corregido
- Las confirmaciones de la página mostraban un campo de texto vacío.
- «Cambiar dirección» rechazaba direcciones como `http://127.0.0.1:8865`.

## [App 1.23] — 2026-11-02

### Agregado
- Al conectar la PC pide solo usuario y contraseña: el nombre de la PC sale del nombre de Windows, y la pantalla abre ya con esa persona (no pide el usuario dos veces).
- Opciones ▾ y el ícono junto al reloj: «Cerrar sesión» (para cambiar de persona sin cerrar la app) y «Salir» (cierra la app enseguida, cerrando la sesión por detrás). Cerrar la ventana no cierra la sesión.
- Perfil de pruebas (`cliente/perfil_pruebas.txt`, lo crea `crear_entorno_pruebas.py`): otra carpeta de datos, otra instancia y otra clave de inicio con Windows, para probar junto a la app de producción. No se distribuye a las PC.
- Una dirección sin `http` de esta PC o de la red local se usa con http.

Compatible con Servidor 2026.10.47 (sin transcriptores) y con 2026.11.1. La App 1.22 sigue funcionando con el Servidor 2026.11.1, pero no puede vincular PC nuevas una vez creados los transcriptores: actualizar las PC antes de crear el primero.

## Herramientas de desarrollo — 2026-11-02
- Rama permanente `experimental` y ramas `exp/<tema>` para cambios de prueba que pueden no llegar
  a la versión final; reglas de promoción a `main` en `AGENTS.md` y `docs/experimentos.md`.
- `crear_entorno_pruebas.py` crea una copia aislada (repositorio propio, puerto 8865, sin túnel,
  `Audios_nuevos`/`Informes` propios, IA simulada por defecto) sin modificar la instalación en uso.
  Pruebas en `pruebas/test_entorno_pruebas.py`. El CI también corre en los push a `experimental`.
  Sin cambios funcionales ni de versión.

## Documentación — 2026-10-31
- Índice `docs/README.md` completo: agrega las etapas de la entrega 1.22 que faltaban
  (`ci-listado`, `editor-audio`, `word-aprendizaje`, `aprendizaje-incremental`, `ia-lotes`) y
  `comparacion-cpu-gpu`, indica las versiones actuales y describe el CI como implementado.
- README, `docs/instalacion.md` y `docs/linux.md` usan la dirección real del repositorio para clonar.
  Sin cambios funcionales ni de versión.

## Documentación y herramientas — 2026-10-30
- Comparación aislada de Whisper GPU/Gemma CPU en paralelo contra los lotes GPU actuales,
  con cuatro dictados ficticios, seis ensayos y guardas de actividad de producción.
  Herramienta opt-in, pruebas CPU y protocolo en `docs/comparacion-cpu-gpu.md`;
  sin cambios de configuración, versiones de aplicación ni distribución.

## [Servidor 2026.10.47] — 2026-10-30

### Corregido
- El panel y la consola muestran los datos de la GPU cuando NVIDIA devuelve temperaturas decimales. Se conserva el aviso por temperatura alta o memoria casi llena; antes se descartaba la lectura completa y se anunciaba incorrectamente que `nvidia-smi` no respondía.

## [Servidor 2026.10.46] — 2026-10-30

Activación comprobada en el proceso real el 30 de octubre: cola vacía, sin pausas ni
estudios abiertos. El proceso ya cargaba esta versión; no se reinició durante la publicación.

### Corregido
- Cola de procesamiento SQLite con confirmación antes de encolar, recuperación FIFO tras caídas, pausas duraderas, protección de borrados y revisión humana. Publicación atómica de resultados y comprobante por ejecución para reconocer informes completos; migración única de pendientes antiguos y respaldo consistente sin detener el servidor.
- Persistencia revisada: validación del contenido de borradores guardados sin sobrescribir archivos corruptos; publicación atómica de formato, audio recibido e índice de huellas. Recepciones simultáneas del mismo audio se serializan y un reintento recupera el encolado pendiente tras recepción duradera.
- Lotes FIFO acotados por cantidad/duración, sin espera fija inicial; fallos aislados por caso y limpieza de Whisper al terminar. Reutilización ASR por contenido/parámetros, banco de ejemplos cacheado con invalidación y perfiles por revisión de plantillas. Métricas locales de carga y generación para validar el resultado en GPU real.
- Correcciones incrementales por ejemplo con conteos transaccionales y consulta indexada de las 40 reglas principales. Historial y registro de Word procesados pasan a SQLite, con importación única de los formatos anteriores, exportación CSV y respaldo consistente explícitos.
- Guardado Word mediante archivo completo y reemplazo atómico; ejemplos, historial, muestras de voz y correcciones se procesan en una cola de aprendizaje persistida, con reintentos y agrupación del análisis global fuera del bloqueo de finalización.
- Editor A4 con reconstrucción desde la hoja anterior al cambio, conservación del prefijo y búsqueda indexada de párrafos. Reproducción con fondo de onda reutilizable, pausa de animación en pestañas ocultas y liberación/cancelación del audio de arrastre al cambiar de caso.
- Índice de metadatos del listado por firma de archivos, permisos/estado siempre frescos, una sola instantánea por consulta de escritorio y consultas web sin solapamiento.
- Borrador y omisiones aceptadas se guardan juntos mediante un archivo atómico; se leen los borradores anteriores sin migración masiva.
- Autoguardado y formato comparten una cola de escrituras; los errores se muestran y se reintentan sin anunciar éxito ni cerrar el caso.
- Navegación y cierre conservan cambios no confirmados; se elimina el envío sin confirmación al abandonar la página.

## [App 1.22] — 2026-10-30

Publicada en la distribución del servidor mediante reemplazo atómico del candidato ya
probado, conservando App 1.21 y respaldo privado reciente. Las PC estaban desconectadas:
la publicación no confirma su instalación ni sustituye el ensayo funcional en pc-test.

### Corregido
- Se conserva un borrador vacío al reabrirlo y se exige confirmación válida de borrador/formato. La cola no elimina audios ante respuestas HTTP 200 ambiguas; la captura conserva WAV incompletos y archivos bloqueados para reintento, registra huellas por reemplazo atómico y mantiene la confirmación aunque falle el aviso visual posterior.
- Al confirmar Word se informa que el aprendizaje continúa en segundo plano cuando el servidor devuelve ese estado.
- Interfaz compartida con paginación A4 parcial y reproducción de audio con menos trabajo por frame.
- La interfaz comparte una única consulta activa del listado.
- La captura confirma la huella solo después de persistir el audio cifrado. Si falla, conserva el candidato para reintento.
- Los audios se publican completos por renombrado; los temporales completos se recuperan al iniciar y los ilegibles/rechazados se conservan para recuperación.
- Salir y actualizar requieren cerrar el estudio primero; una ventana oculta con un caso abierto ya no habilita una actualización que pueda perder cambios.
- Interfaz de borradores con estado de guardado y reintento.

### Documentación y herramientas — 2026-10-29
- Preparación de activación coordinada 1.22/2026.10.46 con piloto pc-test, respaldos privados verificados, artefactos de candidato/rollback por hashes y conversión de datos antiguos ensayada únicamente en copias ficticias. La preparación no publica ni reinicia.
- Validación manual RTX 3080 con nueve ensayos y 36 informes sintéticos: lotes 1/2/4, tiempos hasta listo, capacidad y cargas de modelos. Herramientas de ensayo aislado/reanudación y resumen validado, con ocho pruebas CPU. Se recomienda 2/180 para uso diario; no se cambió configuración ni se reiniciaron servicios.
- CI Windows/Python 3.12 con pruebas CPU y navegador, cola cifrada, compilación/autoprueba y candidato por despacho manual; dependencias de pruebas fijadas y lock npm. Activación remota y promoción a producción pendientes.
- Auditoría de rendimiento y fiabilidad del servidor, web y cliente Windows, con 19 hallazgos priorizados y medición sintética del listado.
- Plan de CI/CD con pruebas aisladas, dependencias reproducibles, candidato inmutable, promoción y rollback; workflows aún pendientes de implementación.
- Microbenchmark aislado `pruebas/medir_listado.py` y corrección de la arquitectura documentada: el trabajador procesa lotes por etapas.
- La auditoría y el microbenchmark no modifican por sí mismos el comportamiento de producción.

## [Servidor 2026.10.45] — 2026-10-29

### Corregido
- Pegar desde Word, con Ctrl+V o desde el menú contextual, conserva el formato de los párrafos y tramos de texto del origen: alineación, negrita, cursiva, subrayado, tachado, fuente, tamaño y colores.
- El texto pegado sin formato deja de heredar la negrita y el centrado del título donde está el cursor.

### Agregado
- Botón para ocultar y mostrar la barra de formato en la edición con audio, con preferencia recordada en esa PC. La vista ampliada mantiene sus herramientas visibles.

## [App 1.21] — 2026-10-29

### Corregido
- Pegado desde Word con formato original en el editor de revisión.

### Agregado
- Control para ocultar y recuperar las herramientas de formato durante la revisión con audio.

## [Servidor 2026.10.44] — 2026-10-29

### Corregido
- El médico seleccionado conserva el fondo azul y una tilde de confirmación en la lista.
- El hover y la navegación con teclado usan un resaltado gris independiente de la selección.

## [App 1.20] — 2026-10-29

### Corregido
- Diferenciación visual entre médico asignado y opción bajo el mouse o el teclado en el visor.

## [Servidor 2026.10.43] — 2026-10-29

### Corregido
- El menú de médicos resalta cada opción al pasar el mouse.
- El desplegable ocupa como máximo 320 px o la mitad de la altura de la ventana,
  con desplazamiento interno y buscador siempre visible.
- La flecha del selector queda alineada al extremo derecho, con espacio reservado
  incluso cuando el nombre del médico es largo.

## [App 1.19] — 2026-10-29

### Corregido
- Resaltado, altura del desplegable y posición de la flecha del selector de médicos del visor.

## [Servidor 2026.10.42] — 2026-10-29

### Corregido
- Ícono «+» centrado horizontal y verticalmente en el botón para agregar médicos del visor,
  con tamaño fijo e independiente de la fuente y del tema de pantalla.

## [App 1.18] — 2026-10-29

### Corregido
- Alineación del botón para agregar médicos en la interfaz de revisión.

## [Servidor 2026.10.41] — 2026-10-29

### Agregado
- Buscador dentro del selector de médicos del visor del estudio: filtra por nombre o apellido,
  sin distinguir tildes ni mayúsculas, con selección por teclado y aviso cuando no hay resultados.
- Botón pequeño «+» junto al selector para agregar y asignar un médico; el alta ya no aparece
  como opción al final de la lista del visor.

## [App 1.17] — 2026-10-29

### Cambiado
- Interfaz de revisión con búsqueda de médicos y botón de alta junto al selector.

## [Servidor 2026.10.40] — 2026-10-29

### Agregado
- Pestaña Médicos del panel con listado, alta, modificación de nombre y notas, y eliminación confirmada.
- Validación de nombres duplicados en el servidor y la interfaz, ignorando mayúsculas, tildes y espacios.
- El alta desde la revisión también valida duplicados en el servidor para evitar sobrescribir notas.
- La gestión del listado conserva las asignaciones y los registros históricos de informes y voz.

## [App 1.16] — 2026-10-29

### Cambiado
- Versión de escritorio sincronizada con la nueva gestión de médicos de la interfaz compartida.

## [Servidor 2026.10.39] — 2026-10-29

### Cambiado
- Atajos predeterminados: F5 reproducir/pausa, F6 atrás, F7 adelante, F10 está bien y F9 vista previa.
- F3 y F4 reducen y aumentan la velocidad de reproducción en 0,25×, entre 0,25× y 2,50×.
- Nueva pestaña de configuración de atajos, con persistencia local, detección de teclas duplicadas,
  restablecimiento de valores predeterminados y ayudas actualizadas según las preferencias.
- El menú contextual conserva la selección y permanece abierto al aplicar formato; se cierra al hacer clic fuera.
- Acciones Copiar selección y Pegar en el menú contextual del editor.

### Desarrollo
- Instrucciones persistentes para versionar, respaldar, documentar y verificar futuras entregas.
- Compilación de Windows con validación de versiones y autoprueba antes de reemplazar el ejecutable,
  más un verificador de coherencia entre fuentes, documentación, ejecutable y manifiesto.

## [App 1.15] — 2026-10-29

### Cambiado
- Número de versión de la app de escritorio actualizado de 1.14 a 1.15 para reflejar los cambios
  recientes en la interfaz de revisión que carga del Servidor: editor A4, formato, menú contextual
  y atajos configurables. Se sincronizan la versión visible y las versiones del ensamblado y del archivo.

## [Servidor 2026.10.38] — 2026-10-29

### Cambiado
- Atajos del editor: Ctrl+S subraya; Ctrl+Q/T/D/J alinean a la izquierda, centran, alinean
  a la derecha y justifican. Se mantienen los atajos alternativos anteriores para dar formato.
- Alineación del menú contextual mediante iconos con descripciones y atajos al pasar el mouse.
- Paleta compartida de 12 colores estándar en la barra y en el menú de clic derecho, con selector adicional.
- Margen superior de 2,5 cm, sin renglones adicionales reservados para encabezado, tanto en la configuración
  de ejemplo como en esta instalación. El editor y el Word exportado usan esos mismos valores.

## [Servidor 2026.10.37] — 2026-10-28

### Cambiado
- El editor A4 se abre directamente en la pantalla de revisión, junto al reproductor, el dictado
  y la forma de onda. Comparte el mismo texto, formato y autoguardado con la presentación ampliada.
- F9 amplía o reduce el editor sin pausar la reproducción. F4, F3, F2 y F8 funcionan desde las hojas.
- Las hojas muestran las marcas pendientes, sus explicaciones y la línea que corresponde al audio.
  El cursor resalta su tramo del dictado; Alt+clic permite escucharlo.
- Las autocorrecciones de Word también funcionan al escribir en las hojas A4.
- El zoom se ajusta al cambiar el ancho del panel del informe.

## [Servidor 2026.10.36] — 2026-10-28

### Agregado
- Editor de Word (F9): escritura y pegado de texto, hojas A4 de tamaño fijo, separación visual y
  numeración de páginas. Los párrafos largos continúan en las hojas siguientes sin recortar el texto.
- Barra de formato con fuente, tamaño de 6 a 96 puntos, negrita, cursiva, subrayado, tachado,
  color, resaltado, alineación, deshacer y rehacer. Menú contextual con clic derecho que conserva la selección.
- Fuente, tamaño, tachado y resaltado se conservan en el Word y en «Copiar para Word».
- Pruebas con datos ficticios del editor en navegador y de la exportación a Word.

### Corregido
- El zoom del editor escala las hojas sin cambiar sus cortes de página.
- Los renglones vacíos consecutivos dentro del informe se conservan al exportar a Word.

## [Servidor 2026.10.35] — 2026-10-26

### Corregido
- **«Reiniciar servidor» desde el panel no volvía a abrir el servidor** (había que abrirlo a mano). Con Whisper
  (CUDA) cargado, el cierre normal de Python en Windows podía colgarse o terminar con otro código, y el .bat no lo
  reabría. Ahora el reinicio sale con `os._exit(75)` después de cerrar todo en orden, y si el cierre se traba más
  de 30 s sale igual.
- Error `WinError 10038` en el hilo «puerto-tunel» al reiniciar o apagar con Microsoft Dev Tunnels: el puerto del
  túnel se cerraba mientras todavía atendía. Ahora primero deja de atender y después se cierra.
- Al cerrarse el servidor, el hilo del túnel ya no avisa «Lo vuelvo a abrir en 10 s».

## [Servidor 2026.10.34] — 2026-10-26

### Agregado
- **Médico reconocido por la voz** (`voces.py`, [docs/voz.md](docs/voz.md)). Después de Whisper se calcula la huella
  de voz del audio (WeSpeaker ResNet34 en ONNX, en el procesador, 1 a 2 s) y se compara con las muestras de cada
  médico. **Seguro** → se asigna solo y la IA usa sus estilos, notas y ejemplos. **Dudoso** → se sugiere y la IA
  usa la plantilla general sin estilos de médico. **Sin reconocer** → sin médico. Con 3 muestras un médico ya se
  puede reconocer solo.
- La voz de cada audio queda como **muestra** de su médico al «Guardar Word y aprender» (o al cambiar el médico de
  un informe ya guardado). Al arrancar se calcula la huella de los casos anteriores y los ya guardados con médico
  suman su voz.
- Barra del caso: botón de la voz junto al médico (*por la voz · 82 %*, *¿Pérez? 64 %* con un clic para
  elegirlo, *voz sin reconocer*, *elegido a mano*). Al cambiar el médico, si la IA usó otro, el aviso ofrece
  «Regenerar con este médico».
- Lista: «🎙 Médico» si se reconoció por la voz, «¿Médico?» si es dudoso, «médico sin reconocer».
- Médicos: cantidad de muestras de voz por médico, lista de muestras con ▶ y «Quitar», y la vista
  **Agrupar voces** para etiquetar de a grupos los audios sin médico.
- Estadísticas: sección **Médico reconocido por la voz** (reconocidos solos, acierto, dudosos, sin reconocer,
  equivocados, por médico).
- `actividad.csv`: columnas `medico_voz`, `voz_estado`, `voz_puntaje`. Registro: área VOZ.
- API: `/api/voces`, `/api/voces/muestras`, `/api/voces/agrupar`, `/api/voces/etiquetar`, `/api/voces/quitar`;
  `voz` en `/api/casos`, `/api/caso` y `/api/caso_medico` (+ `regenerar`); `voz` (muestras) en `/api/medicos`.
- `configuracion.json` → `voces` (opcional) para ajustar los umbrales.

### Cambiado
- «Médico de los audios que subas»: la opción vacía ahora se llama **Automático (por la voz)**.
- `nucleo.armar_mensajes(..., sin_estilos=True)` no manda las variantes «(estilo X)» de otros médicos.
- El modelo de voz (`modelos/`) y las huellas (`voces/`) no se suben al repositorio.

## [Servidor 2026.10.33] — 2026-10-26

### Arreglado
- **El panel de administración no se podía abrir desde el trabajo con Microsoft Dev Tunnels**: al escribir la
  contraseña decía «Pedido rechazado». Dev Tunnels reescribe los encabezados Host y Origin a
  `localhost:<puerto del túnel>`, y el control de origen de los botones del panel esperaba la dirección pública.
  Ahora, en el puerto propio del túnel se acepta ese Origin reescrito (además de Host, X-Forwarded-Host y la dirección
  del túnel). Siguen exigiéndose `X-Panel`, `Sec-Fetch-Site` y la cookie SameSite=Strict. Cuando se rechaza un pedido,
  el registro dice el motivo con los encabezados recibidos.

## [Servidor 2026.10.32] — 2026-10-26

### Agregado
- **Pantalla de inicio y botón «Inicio»** en el pie de la lista (junto a Plantillas y Médicos) y en el riel de la
  lista oculta. Muestra la fecha, el estado de la IA, cifras (para revisar, en proceso, revisados hoy, con error), la
  tarjeta de «qué hacer ahora» que ya existía, la lista de informes para revisar (del más antiguo al más nuevo),
  los últimos revisados con «Abrir Word» (o «Descargar Word» en las PC del trabajo) y accesos rápidos (Cargar
  audio, Plantillas, Médicos, Configuración, Administración). Respeta la pestaña «Esta PC» / «Todas». El botón de la
  vista actual queda marcado. Ir al inicio con un informe abierto lo cierra (queda como borrador y libre).
- `/api/casos` trae `revisado_en` (cuándo se guardó el Word) para contar los «revisados hoy».

### Cambiado
- **Al «Guardar Word y aprender» el informe se cierra y se vuelve al inicio.** El aviso trae «Abrir Word» (en la PC
  del servidor) y «Revisar el siguiente» si queda otro para revisar.

## [Servidor 2026.10.31] — 2026-10-26

### Arreglado
- **Pegar en el editor del informe ponía todo en negrita y centrado.** Al pegar varios renglones (por ejemplo,
  copiados del sistema de gestión) el navegador copiaba la clase del renglón donde estaba el cursor —casi siempre
  el título— a todos los renglones nuevos. Ahora el texto pegado queda con el formato normal del informe y solo los
  renglones que parecen título de estudio quedan centrados en negrita (misma regla que el Word). Solo cambia
  `web/index.html`: no hace falta reiniciar el servidor ni actualizar la app.
- **El servidor se trababa al cargar Whisper** y las PC del trabajo veían «Sin conexión con el servidor ·
  reintentando» en la pantalla, aunque la barra de la app dijera «Conectado» y los audios se enviaran. La carga de
  Whisper desvía `print` al registro con `redirect_stdout`, que cambia `sys.stdout` para todos los hilos: la consola,
  el encabezado fijo o el título escribían ahí con el candado del registro tomado y el propio hilo quedaba esperando
  ese candado para siempre. Desde ese momento todo pedido que anotara algo en el registro (la lista de casos, el
  panel, las transcripciones) quedaba colgado. Ahora la ventana se escribe siempre en la salida real
  (`sys.__stdout__`), `SalidaAlRegistro` solo captura lo que imprime el hilo que la puso y el candado es reentrante.

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

### [1.14] — 2026-10-26
- Opción nueva en Configuración → Esta PC: **Notificaciones de Windows** (los carteles junto al reloj: informe listo,
  avisos con la ventana escondida). **Apagada por defecto**; se guarda en `config.json` como `notificaciones_windows`.
  El aviso dentro de la ventana sigue funcionando igual. También aparece en la configuración propia de la app (sin
  conexión). La pantalla del Servidor muestra el interruptor solo si la app lo informa (1.14 en adelante).

### [1.13] — 2026-10-26
- La autocorrección de Word encuentra el Normal.dotm con Office en español (`%APPDATA%\Microsoft\Plantillas`) y en
  otros idiomas (Modelos, Modèles, Vorlagen, Modelli, Sjablonen); como último recurso usa el Normal.dotm más reciente
  de cualquier carpeta de `%APPDATA%\Microsoft`. Antes solo miraba `Templates` y la carpeta del registro (USER-DOTS),
  que Word anota solo si se cambió a mano.

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
