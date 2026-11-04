# Guía de desarrollo

## Entorno

```bat
instalar.bat                         :: crea .venv e instala requirements.txt
.venv\Scripts\activate
python servidor.py                   :: igual que interfaz.bat
python servidor.py --tunel           :: igual que iniciar_servidor.bat
python servidor.py --sin-navegador   :: no abre el navegador al iniciar
```

No hay dependencias de JavaScript: las páginas de `web/` son HTML + CSS + JS sin compilar.

## Modo simulado (sin GPU ni Ollama)

Permite probar la interfaz, el acceso remoto, la cola y el panel en cualquier PC (incluso Linux):

```bash
SIMULAR_IA=1 SIMULAR_DEMORA=2 python servidor.py --sin-navegador
```

| Variable | Efecto |
|---|---|
| `SIMULAR_IA=1` | No carga Whisper ni llama a Ollama: usa transcripciones y salidas grabadas |
| `SIMULAR_SIN_IA=1` | Hace de cuenta que Ollama está cerrado hasta que exista el archivo `_ia_vuelve` |
| `SIMULAR_HUECOS='[...]'` | Lista JSON de huecos a informar en cada transcripción |
| `SIMULAR_DEMORA=N` | Segundos de espera simulados en cada etapa |

Con `SIMULAR_IA=1`, para un audio `X.wav` el servidor lee:
- `resultados/fase1/json/X.json` → clave `con_vocab` (`{"texto": ..., "palabras": [...]}`), y
- `resultados/fase2/gemma4_12b/X.json` → clave `salida` (texto del informe).

Estas carpetas no se versionan (salen de audios reales); para pruebas hay que generar datos ficticios con esa estructura.
Para probar el túnel sin Cloudflare se puede reemplazar `cloudflared.exe` por un script que imprima una dirección
`https://….trycloudflare.com` y simular los encabezados `Cf-Ray` / `Cf-Connecting-Ip` en los pedidos.

## Convenciones de código

### Contratos y lint

Dos pruebas fijan el comportamiento del sistema y son la red de seguridad del
[refactor por etapas](refactor.md):

- `pruebas/test_contrato_http.py`: arranca `servidor.py` en un subproceso, en modo simulado, sobre una copia del
  código en una carpeta temporal, y recorre el flujo completo por HTTP (subir, procesar, borrador, Word, borrar…).
- `pruebas/test_contrato_nucleo.py`: compara las salidas del núcleo (marcas, prompt, normalización, orden,
  párrafos del Word) para los casos ficticios de `pruebas/contratos/casos_nucleo.json` con `nucleo_esperado.json`.

Un refactor no los cambia. Si un cambio funcional deliberado cambia el núcleo, regenerar y revisar el diff:
`ACTUALIZAR_CONTRATOS=1 python -m unittest pruebas.test_contrato_nucleo`.

Calidad (el CI corre todo esto; versiones en `requirements-ci.txt`, detalle en
[refactor.md → Calidad del código](refactor.md#calidad-del-código)):

```bash
python -m ruff format transcripcion      # formato del paquete (antes de subir un cambio ahí)
python -m ruff check .                   # lint; transcripcion/ con reglas estrictas (transcripcion/ruff.toml)
python -m mypy                           # tipos del paquete
python -m coverage run -m unittest discover -s pruebas -p 'test_*.py' && python -m coverage report
```

### Aislamiento de pruebas y rendimiento

`python -m unittest discover -s pruebas -p test_placa_video.py` verifica la lectura
de GPU con temperaturas enteras/decimales, alertas y fallos de NVIDIA (`transcripcion/operacion/gpu.py`, sin importar
el servidor ni cargar configuración o datos de la instalación).

Importar un módulo del sistema no lee la configuración ni crea carpetas
(`pruebas/test_importar_sin_efectos.py`). Una prueba que usa el servidor lo configura con una carpeta
temporal y lo restaura al terminar:

```python
import servidor as S
from transcripcion import ajustes
aj = ajustes.para_pruebas(carpeta_temporal)        # Audios_nuevos e Informes adentro; configuración de ejemplo
ajustes.preparar_carpetas(aj)
self.addCleanup(S.configurar, S.configurar(aj))    # configurar devuelve los ajustes anteriores
```

`configurar` crea también `S.CASOS` (archivos de los casos) y `S.PROC` (estado del procesamiento) nuevos. Para otras
carpetas: `ajustes.para_pruebas(base, carpeta_informes=…, carpeta_audios_nuevos=…)`. Para cambiar un comportamiento,
parchear el método del objeto (`patch.object(S.CASOS, "ruta_audio", …)`), no reemplazar variables globales. Lo que
no necesita el servidor se prueba armando los objetos directamente: `Procesamiento(Casos(datos, nuevos))`.

Para probar rutas HTTP en el mismo proceso: después de `configurar`, `S.ThreadingHTTPServer(("127.0.0.1", 0), S.H)`
(`S.H` es el manejador del sistema configurado) y `patch.object(S.SIS, "puerto", servidor.server_port)` para que el
panel y los botones solo locales acepten ese puerto. Una ruta nueva se escribe como función `f(h, pedido)` en el
módulo de su área de `transcripcion/http/`, se registra en `transcripcion/http/tabla.py` y se agrega a la lista de
`pruebas/test_rutas.py`.

Lo que se lee del conocimiento (plantillas, reglas, médicos) también debe apuntar a la carpeta temporal
(`patch.object(CON, "CONOC", carpeta / "conocimiento")`, `patch.object(MED, "DIR_MED", …)` y
`CON.preparar_conocimiento()`, con `from transcripcion.conocimiento import archivos as CON, medicos as MED`).
`CONOC` siempre se usa como `CON.CONOC`, nunca importado suelto: así el reemplazo llega a todos. Igual que los registros
(`registro.CARPETA`) y la carpeta del cliente (`remoto.CARPETA_CLIENTE`): nunca los de la instalación.
Usar datos ficticios; no apuntar las pruebas HTTP o de carga al servidor en uso. Los scripts Playwright permiten
`PLAYWRIGHT_MODULE`, `BROWSER_CHANNEL` y, para `medicos.cjs`, `PYTHON`; este último necesita
crear previamente `respaldo/` en el checkout de ensayo.

El microbenchmark `python herramientas/medir_listado.py` prepara automáticamente una copia aislada
y mide el listado con 100 y 1.000 casos ficticios. No ejecuta HTTP ni IA y no reemplaza pruebas
de carga simultánea, navegador o GPU. Consultar [resultados y límites](auditoria-rendimiento-2026-10-29.md)
y [puertas CI/CD](ci-cd.md) antes de interpretar sus resultados.

La primera etapa de persistencia agrega `pruebas/test_borradores.py`, `pruebas/borradores.cjs`
y `pruebas/cola_audios.cs`. Ver [ejecución aislada, formatos y recuperación](persistencia.md).
La revisión posterior agrega `test_recepcion_audio.py`: publicación atómica con metadatos,
deduplicación concurrente, recuperación de encolado e índice de huellas ante fallos.
Las regresiones de borradores y cola incluyen respuestas HTTP 200 ambiguas, borrador vacío,
esquema inválido y WAV cuyo tamaño declarado aún no está completo.

`test_cola_procesamiento.py` usa SQLite real, procesos de ensayo que terminan abruptamente
y el trabajador simulado para verificar recuperación de tareas, pausas, borrados y resultados.
Ver [cola persistente, migración y respaldo en vivo](cola-servidor.md). No iniciar `servidor.main`
ni ejecutar la migración sobre la instalación en uso para probarla.

`test_preparacion_activacion.py` prueba copia verificada, backup SQLite e integridad del paquete,
además de rollback de borradores/historial únicamente en copias ficticias. `scripts/preparar_activacion.py`
no tiene una acción de despliegue. Ver [activación coordinada y criterios de ventana](activacion-coordinada.md).

Las pruebas `editor_word.cjs` y `revision_word.cjs` también verifican la paginación parcial,
equivalencia de cortes de hojas, reutilización del fondo de onda y cancelación/liberación de audio.
Ver [mediciones y límites del editor/audio](editor-audio.md).

`test_aprendizaje_pendiente.py` verifica Word válido, publicación fallida sin truncar el anterior,
cola recuperable, versiones concurrentes e idempotencia del historial. Ver [Word y aprendizaje](word-aprendizaje.md).

`test_almacen_aprendizaje.py` comprueba migración CSV, idempotencia, rollback, reglas incrementales,
reconciliación y estadísticas. `python herramientas/medir_aprendizaje.py` mide escrituras indexadas
en bases ficticias de 100/1.000/10.000 informes bajo `respaldo/`, sin importar el servidor.

`test_lotes_ia.py` prueba el trabajador completo con colas finitas, ASR/Ollama simulados, caché
fría/caliente, límites FIFO, aislamiento de fallos, banco y perfiles de ejemplos. No carga GPU.
Ver [condiciones de validación real de IA](ia-lotes.md).

`herramientas/validar_gpu_real.py --ejecutar` realiza una campaña manual con voz sintética,
daemon Ollama separado y cancelación conservadora ante trabajo de producción. Sin esa
opción no carga modelos. `herramientas/resumir_gpu_real.py` valida/agrega campañas completas y
`test_validacion_gpu.py` prueba guardas y métricas sin GPU. No ejecutar otros Python
durante la medición: la vigilancia los considera trabajo ajeno. Ver [resultados RTX 3080,
protocolo y límites](validacion-gpu.md). El benchmark real no corre automáticamente en CI.

`herramientas/comparar_cpu_gpu.py --ejecutar --corpus respaldo/gpu_real_FECHA_HORA`
compara el camino actual de lotes GPU con Whisper GPU/Gemma CPU en paralelo,
usando únicamente el corpus sintético verificado. Mantiene el servidor en uso,
espera la liberación natural de sus modelos y cancela el ensayo ante actividad.
Ver [protocolo, resultados y límites](comparacion-cpu-gpu.md). Ejecutar sus pruebas
`test_comparar_cpu_gpu.py` antes o después de medir, nunca durante la campaña.

### Convenciones generales

- **Idioma**: nombres, comentarios y mensajes en español rioplatense, como el resto del código y la interfaz.
- **Python**: biblioteca estándar siempre que se pueda; las únicas dependencias son las de `requirements.txt`.
  Todo lo que se muestra o registra pasa por `transcripcion/base/registro.py` (`L.ok/info/aviso/error`), nunca `print`.
- **Mensajes al usuario**: claros y sin jerga técnica (`mensaje_amigable`); el detalle técnico va al registro.
- **El script de la página principal es uno solo**, aunque se escriba en partes (`web/js/principal/010-base.js`,
  `020-lista.js`…): el servidor las une en orden de nombre y las envía como `/js/principal.js`. Las funciones son
  globales: dos `function` con el mismo nombre en partes distintas no dan error, la última pisa a la primera.
  `node pruebas/verificar_fuentes.cjs` lo detecta. Para agregar código: en la parte de su área; para un área nueva,
  un archivo con un número intermedio (p. ej. `155-…js` entre médicos y voces). Los estilos, igual en
  `web/css/principal/`. Las pruebas de Playwright con servidor propio arman esos archivos con `pruebas/web_pruebas.cjs`.

- `admin.html` y `estadisticas.html` comparten estilos y utilidades copiados: si se cambia el aspecto de una, revisar la otra.
- **Dónde va cada archivo**: lo que corre el servidor, en el paquete `transcripcion/`; scripts para operar la
  instalación, en `scripts/`; herramientas de desarrollo, evaluación y medición, en `herramientas/`; pruebas, en
  `pruebas/`. En la raíz solo `servidor.py`, `informe.py` y los lanzadores. Un script de `scripts/` o `herramientas/`
  que importa `transcripcion` empieza con `RAIZ = Path(__file__).resolve().parents[1]` y
  `sys.path.insert(0, str(RAIZ))` (`test_paquete.py` lo verifica).
- **App de Windows**: respetar las reglas de [compilacion.md](compilacion.md#métodos-prohibidos).
- **Respaldos locales**: antes de modificar archivos en la instalación en uso, copiarlos a
  `respaldo/respaldo_AAAAMMDD_antes_de_<cambio>/` (no versionado).

## Commits

La rama principal remota es `main`. `feat/admin-medicos` se integró mediante la PR #3
y fue eliminada del remoto. La entrega App 1.22 / Servidor 2026.10.46 se propone desde
`feat/persistencia-rendimiento-ci` hacia `main`; el workflow valida las PR y los pushes
a `main`. Crear ramas por tarea y abrir una PR contra la principal, conservando los
commits existentes y los artefactos de producción fuera de Git.

Las pruebas que quizá no lleguen a la versión final van en ramas `exp/<tema>` sobre la rama
permanente `experimental`, y se ejecutan en una copia aislada creada con `scripts/crear_entorno_pruebas.py`
(otro puerto, sin túnel, carpetas propias). Ver [ramas experimentales y entorno de pruebas](experimentos.md).

Se usa [Conventional Commits](https://www.conventionalcommits.org/es/v1.0.0/) en español:

```
<tipo>(<ámbito>): <resumen en imperativo, minúscula, sin punto>

<cuerpo opcional: qué cambia y por qué>
```

| Tipo | Uso |
|---|---|
| `feat` | Funcionalidad nueva |
| `fix` | Corrección de un error |
| `docs` | Solo documentación |
| `refactor` | Cambio de código sin cambiar el comportamiento |
| `perf` | Mejora de rendimiento |
| `test` | Pruebas |
| `build` | Compilación, dependencias, scripts de instalación |
| `chore` | Mantenimiento del repositorio |

Ámbitos habituales: `transcripcion`, `ia`, `informe`, `aprendizaje`, `servidor`, `interfaz`, `remoto`, `admin`, `cliente`.

Ejemplo: `fix(cliente): reemplazar TrimEnd(char) por la sobrecarga de .NET 4.8`.

## Checklist antes de publicar un cambio

Las instrucciones persistentes para agentes están en [AGENTS.md](../AGENTS.md).
Versionar es parte del cambio: si la interfaz web modifica la experiencia de la app,
actualizar tanto la versión del servidor como la de escritorio. Los cambios exclusivamente
de documentación, pruebas o herramientas de desarrollo no requieren subir esas versiones.
Al publicar, trasladar las notas entregadas de «Sin publicar» a las entradas fechadas correspondientes.

- [ ] `python -m ruff format transcripcion`, `python -m ruff check .` y `python -m mypy` sin errores; cobertura por encima del piso.
- [ ] Contratos (`test_contrato_http`, `test_contrato_nucleo`) en verde sin regenerar, salvo cambio funcional deliberado.
- [ ] `node pruebas/verificar_fuentes.cjs`: sintaxis y sin funciones repetidas en la página principal.
- [ ] Probado en modo simulado (y en la PC real si toca Whisper, Ollama o Windows).
- [ ] Si cambió la app: versión subida, API revisada contra .NET 4.8, autoprueba OK ([compilacion.md](compilacion.md)).
- [ ] `git status` sin datos de pacientes, secretos ni binarios.
- [ ] CHANGELOG actualizado.
- [ ] `python herramientas/verificar_versiones.py` sin errores; compilación y autoprueba del ejecutable si cambió la app.
- [ ] Distinguir archivos publicados de procesos reiniciados y PC efectivamente actualizadas.

## Lecciones aprendidas

| Problema | Solución |
|---|---|
| PyAV 16 rompe faster-whisper | Lector WAV propio y `av<16` |
| Un audio usado como su propio ejemplo daba 0 % de error en la evaluación | Se excluye siempre el mismo audio |
| La detección de "texto fijo" tomaba la línea de Bi-Rads como fija | Solo cuentan los bloques `TEXTO FIJO` |
| El historial duplicaba filas al volver a guardar | Se reemplaza la fila del mismo día |
| Un error de tipeo en una corrección se propagaba como ejemplo | Revisar `correcciones_aprendidas.md` |
| La IA seguía el orden del dictado | `ordenar_estudios` impone el orden estándar |
| Un estudio no reconocido producía "Protocolo normal." literal | Más sinónimos de reconocimiento y marca roja `[COMPLETAR]` |
| "un birrastre" quedaba en rojo aunque coincidía | Se desmarca si el número coincide con el Bi-Rads dictado |
| `String.TrimEnd(Char)` compilaba con Mono y fallaba en Windows | Reglas de API y autoprueba antes de instalar |
| Dos funciones `alinear` en `index.html` (una pisaba a la otra) | Renombrar y verificar nombres repetidos |
| Leer como JSON la página HTML de error del túnel (530) | `pedir()` nunca interpreta HTML: lo trata como "sin conexión" |

## Hoja de ruta

- Ajuste fino de Whisper con las voces de los médicos (con unos cientos de informes revisados).
- Detección de autocorrecciones del médico dentro del dictado ("perdón", "no, mejor").
- Controles de coherencia clínica (Bi-Rads contra hallazgos, lateralidad).
- Cálculos automáticos (volumen tiroideo y prostático, TI-RADS).
- Copia de seguridad automática y limpieza de audios antiguos.
- Ctrl+Enter para guardar y pasar al siguiente; deshacer en "Regenerar".
