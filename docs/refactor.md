# Plan de refactor: código modular, legible y mantenible

*Iniciado y terminado el 03/11/2026 (etapas 0 a 9). Decisión en [ADR 0001](adr/0001-modularizar-por-etapas.md).
**Documento histórico:** para trabajar en el código alcanza con [arquitectura.md](arquitectura.md) y
[desarrollo.md](desarrollo.md). Acá queda el porqué de cada cambio («Etapa N: qué quedó»), al que remiten
algunos comentarios del código.*

## Por qué

El sistema funciona y está en uso diario, pero el código creció rápido alrededor de pocos archivos:

| Archivo | Líneas | Qué mezcla hoy |
|---|---:|---|
| `servidor.py` | ~3.400 | Arranque, ~40 variables globales de estado, cola y trabajador, pausas, casos, voz, reinicio y mensajes, borrado, aprendizaje, ~100 rutas HTTP en dos cadenas de `if` (`do_GET` ~270 líneas, `do_POST` ~410), panel y 4 páginas HTML dentro de cadenas |
| `web/index.html` | ~3.570 | ~650 líneas de CSS y ~2.550 de JavaScript (167 funciones) dentro del HTML |
| `nucleo.py` | ~1.400 | Plantillas, selección de ejemplos, prompt, cliente de Ollama, marcas, controles clínicos, omisiones, orden de estudios y HTML |
| `fase1_transcribir.py` | ~470 | Whisper y lectura de audio, normalización de números (la usa todo el sistema) y reportes de la evaluación de la fase 1 |
| `cliente_codigo/VentanaPrincipal.cs` | ~1.460 | Ventana, bandeja, modo compacto, puente con la página, actualizaciones |

Además hay ~35 `.py` sueltos en la raíz (módulos del sistema mezclados con scripts de mantenimiento) y
**importar `servidor.py` tiene efectos**: lee `configuracion.json` (o lo crea), crea `../Audios_nuevos` y
`../Informes/revision/datos`. Correr las pruebas dentro de `sistema\` escribe al lado de los datos reales, y
por eso las pruebas reemplazan decenas de variables globales con `patch.object`.

Consecuencias: cada cambio obliga a entender archivos enormes, las pruebas se rompen al mover código y el
riesgo de un efecto colateral en producción es alto.

## Objetivo

1. **Módulos chicos con una sola responsabilidad**, agrupados en un paquete `transcripcion/`.
2. **Sin efectos al importar**: la configuración se lee en el arranque y se pasa como objeto (`Ajustes`).
3. **Estado explícito**: en lugar de variables globales sueltas, objetos (`Cola`, `Procesador`, `Casos`) que se
   crean en el arranque y se pasan a quien los usa. Así una prueba arma los suyos sin parchear nada.
4. **Rutas HTTP en una tabla** (`(método, ruta) → función`) separadas por área, con la lógica fuera del handler.
5. **La página principal en archivos separados** (CSS y módulos JS por función).
6. **Nada cambia para la transcriptora**: mismo comportamiento, mismas pantallas, mismos `.bat`.

## Estructura destino

```
sistema/
├── servidor.py                 punto de entrada fino (los .bat no cambian): from transcripcion.app import main
├── informe.py, aprender.py…    puntos de entrada de consola que se conservan (delegan en el paquete)
├── transcripcion/
│   ├── app.py                  arranque: Ajustes → objetos → hilos → servidor HTTP
│   ├── ajustes.py              Ajustes (dataclass): rutas, puertos, modo simulado, configuracion.json
│   ├── base/                   plataforma, persistencia (escritura atómica), registro
│   ├── casos/                  archivos de un caso, estado, listado, borradores, paciente, índice, borrado
│   ├── procesamiento/          cola SQLite, trabajador, lotes, pausas, tiempos, caché de transcripción
│   ├── asr/                    whisper (modelo, lectura de WAV, transcribir), huecos
│   ├── texto/                  normalización de números, horas y niveles; datos críticos; palabras
│   ├── conocimiento/           carpeta conocimiento/, plantillas por estudio, notas de los médicos
│   ├── ia/                     cliente de Ollama, ejemplos y referencias, prompt
│   ├── controles/              marcas, controles clínicos, omisiones, orden de estudios, alineación
│   ├── informe/                párrafos y Word (python-docx), formato
│   ├── aprendizaje/            ejemplos, historial, correcciones, cola de aprendizaje
│   ├── voz/                    huellas y reconocimiento del médico
│   ├── acceso/                 túnel, sesiones, llaves por PC, usuarios, permisos del panel
│   ├── operacion/              reinicio, mensajes a las PC, mantenimiento, estadísticas, GPU
│   └── http/                   manejador, tabla de rutas, una función por ruta agrupadas por área
├── web/                        index.html + css/principal/ + js/principal/ (partes por área), admin, estadísticas…
├── scripts/                    configurar_acceso, configurar_tunel, mantenimiento_*, activación, rollback…
├── herramientas/               evaluación (fase 1), verificación de versiones, mediciones, GPU, comparar_il
└── pruebas/                    unitarias por módulo + contratos (caja negra)
```

Los nombres son orientativos: cada etapa puede ajustarlos y lo deja escrito acá.

## Reglas de cada PR de refactor

1. **Rama `refactor/<etapa>-<tema>`** desde `main` actualizado; PR hacia `main` (no pasa por `experimental`:
   no es una prueba de idea sino una reorganización con red de seguridad).
2. **Un PR = una etapa o un módulo.** Separar en commits distintos *mover* (copiar/pegar sin tocar, revisable
   rápido) de *cambiar* (ajustar imports, firmas, estado).
3. **Sin cambios de comportamiento.** Tienen que pasar sin regenerar nada:
   - `pruebas/test_contrato_http.py`: el flujo completo por HTTP, contra un servidor real en modo simulado;
   - `pruebas/test_contrato_nucleo.py`: marcas, prompt, normalización, orden y párrafos del Word.

   Si un contrato falla, el refactor cambió algo: se corrige el refactor, no el contrato. El único archivo de los
   contratos que puede cambiar es `pruebas/contratos/calcular_nucleo.py`, y solo en sus imports y en `preparar()`
   (lo que un punto de entrada hace antes de usar el núcleo).
4. **Las pruebas existentes se migran en el mismo PR** que mueve lo que prueban (dejan de parchear globales y
   pasan a construir los objetos que necesitan).
5. **Versión**: un refactor no sube versiones por su cuenta ([ADR 0002](adr/0002-versiones-por-entrega.md)). Deja su
   nota en «Sin publicar» del CHANGELOG, bajo `#### Interno` de `### Servidor` (y de `### App` si toca la página
   principal o `cliente_codigo/`), como *reorganización interna, sin cambios visibles*, y sale con la próxima
   entrega. Qué código corre lo muestra el panel (commit y etiqueta en Mantenimiento). Hasta la etapa 9, cada etapa
   subía su versión; ver [versiones.md](versiones.md).
6. **Producción**: cada etapa que toca el servidor necesita reiniciarlo. Antes, etiqueta git del commit actual;
   se activa en una ventana sin trabajo; vuelta atrás = volver a la etiqueta y reiniciar. Las etapas marcadas
   como *riesgo alto* se prueban antes en `sistema_pruebas` (`crear_entorno_pruebas.py`).
7. **Calidad**: los módulos nuevos o terminados entran a reglas de ruff más estrictas (ver abajo).

## Etapas

| # | Etapa | Qué se hace | Riesgo | Versión |
|---|---|---|---|---|
| 0 | **Red de seguridad** | Contratos HTTP y del núcleo, ruff mínimo en el CI, este plan y el ADR 0001 | Nulo (solo pruebas y docs) | — |
| 1 | **Ajustes y arranque sin efectos** | `ajustes.py` (pasa a `transcripcion/` en la etapa 2); `servidor.py` y `nucleo.py` dejan de leer config y crear carpetas al importarse (todo pasa al arranque); prueba «importar no escribe nada» | Medio | Servidor |
| 2a | **Paquete con los módulos base** | Crear `transcripcion/` y mover los módulos que ya son independientes (plataforma, persistencia, registro, ajustes, borradores, paciente, índice, cola, lotes, caché, almacén y cola de aprendizaje, usuarios). Adaptar `mantenimiento.py` (detección de código cambiado y prueba previa al reinicio), las herramientas que copian el código y el CI | Medio (muchos imports) | Servidor |
| 2b | **Scripts y herramientas** | Scripts de operación a `scripts/` y herramientas de desarrollo y evaluación a `herramientas/`; los `.bat`/`.sh`, el CI y la documentación los llaman en su carpeta | Bajo | — |
| 3 | **Núcleo** | `nucleo.py` → `conocimiento/` (archivos, plantillas, médicos), `ia/` (ollama, ejemplos, prompt) y `controles/` (marcas, clínicos, avisos, orden). Guardia: contrato del núcleo | Bajo | Servidor |
| 4 | **Transcripción** | `fase1_transcribir.py` → `asr/whisper.py` y `texto/normalizacion.py`; `huecos.py` → `asr/huecos.py`. `fase1_transcribir.py` queda como herramienta de evaluación (pasa a `herramientas/` en la 2b) | Bajo | Servidor |
| 5 | **Estado del servidor en objetos** | De `servidor.py`: `Casos` (`casos/repositorio.py`: archivos de cada caso, cachés, índice del listado) y `Procesamiento` (`procesamiento/estado.py`: etapas, cola, pausas, tiempos) como objetos creados en `configurar()`, sin las globales sueltas | **Alto** | Servidor |
| 6a | **Servicios fuera de `servidor.py`** | Trabajador → `procesamiento/trabajador.py`; lista, caso abierto y borrado → `casos/`; voz → `voz/`; estado de la IA, reinicio y mensajes → `operacion/`; «Guardar Word» y Word → `informe/`. Cada uno recibe en su constructor los objetos que usa | **Alto** | Servidor |
| 6b | **Módulos de la raíz al paquete** | `remoto`, `admin` → `acceso/`; `mantenimiento`, `estadisticas`, `app_cliente` → `operacion/`; `aprender`, `correcciones` → `aprendizaje/`; `importar_informes` → `conocimiento/importar.py`. En la raíz quedan lanzadores de consola. Así el HTTP (6c) puede vivir en el paquete | Bajo | Servidor |
| 6c | **HTTP** | Tabla de rutas y handlers por área (casos, conocimiento, cliente, usuario, admin, páginas); páginas HTML fuera de las cadenas; `servidor.py` queda con el arranque | **Alto** | Servidor |
| 7 | **Página principal** | `web/index.html` → `css/principal/` y `js/principal/` en partes por área, que el servidor une en orden (un solo script, como antes) | Medio | Servidor + App |
| 8 | **App de escritorio** | `VentanaPrincipal.cs` partida por responsabilidad (partial class: barra, conexión, página, puente, bandeja, compacto, actualización…); `RelojUi` a su archivo | Bajo (IL idéntico) | App |
| 9 | **Calidad continua** | Reglas estrictas de ruff y `ruff format` en todo `transcripcion/`, mypy en el paquete, cobertura de las pruebas con piso en el CI | Bajo (AST verificado) | Servidor |

Orden recomendado: 0 → 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8, con la 9 en paralelo. Las etapas 3 y 4 son buenas
para tomar ritmo (riesgo bajo, contrato del núcleo como guardia) antes de las 5 y 6, que son el corazón.

## Estado

| Etapa | Rama / PR | Estado |
|---|---|---|
| 0 | `test/red-de-seguridad-refactor` · PR #13 | Hecha (fusionada el 03/11) |
| 1 | `refactor/1-ajustes-sin-efectos` · PR #14 · Servidor 2026.11.3 | Hecha (fusionada el 03/11) |
| 2a | `refactor/2-paquete-base` · PR #15 · Servidor 2026.11.4 | Hecha (fusionada el 03/11) |
| 3 | `refactor/3-nucleo` · PR #16 · Servidor 2026.11.5 | Hecha (fusionada el 03/11) |
| 4 | `refactor/4-transcripcion` · PR #17 · Servidor 2026.11.6 | Hecha (fusionada el 03/11) |
| 5 | `refactor/5-casos-procesamiento` · PR #18 · Servidor 2026.11.7 | Hecha (fusionada el 03/11) |
| 6a | `refactor/6a-servicios` · PR #20 · Servidor 2026.11.8 | Hecha (fusionada el 03/11) |
| 6b | `refactor/6b-raiz-al-paquete` · PR #21 · Servidor 2026.11.9 | Hecha (fusionada el 03/11) |
| 6c | `refactor/6c-http` · PR #22 · Servidor 2026.11.10 | Hecha (fusionada el 03/11) |
| 7 | `refactor/7-pagina-principal` · PR #23 · Servidor 2026.11.11 · App 1.25 | Hecha (fusionada el 03/11) |
| App 1.25 | `version/app-1.25` · PR #24 | Hecha (fusionada el 03/11) |
| 8 | `refactor/8-ventana-principal` · PR #25 · App 1.25 | Hecha (fusionada el 03/11) |
| 2b | `refactor/2b-scripts-herramientas` · PR #26 · sin versión nueva | Hecha (fusionada el 03/11) |
| 9 | `calidad/9-ruff-cobertura` · PR #27 · Servidor 2026.11.12 | Hecha (fusionada) |

### Etapa 1: qué quedó

- `ajustes.py`: `Ajustes` (dataclass inmutable con `cfg`, carpetas, puertos y modo simulado), `cargar()`,
  `leer_config(crear=False)` para validar sin escribir, `preparar_carpetas()` y `para_pruebas(carpeta)`.
- `servidor.configurar(ajustes)` completa las globales que antes se calculaban al importar (`CFG`, `NUEVOS`,
  `INFORMES`, `DATOS`, puertos, `SIMULAR`, `COLA_AL_REINICIAR`, `APRENDIZAJE`) y devuelve las anteriores.
  `main()` hace `configurar(ajustes.cargar())`, `preparar_carpetas()` y `nucleo.preparar_conocimiento()`.
  Las globales siguen existiendo: desaparecen en la etapa 5, cuando cada parte pase a ser un objeto.
- `nucleo.preparar_conocimiento()` (antes `_preparar_conocimiento()` al importar) la llaman `servidor`,
  `informe` y `aprender` al arrancar.
- `mantenimiento.prueba_de_arranque()` valida `configuracion.json` aparte, porque importar ya no lo hace.
- Lo que apareció: cinco pruebas usaban sin querer las carpetas reales (Word de prueba en `Informes`, registros,
  `cliente/conexion.json`, plantillas reales). Se corrigieron y ahora la suite completa no deja nada fuera de
  `respaldo/`. Queda para más adelante: `sys.stdout.reconfigure` al importar en algunos scripts (no escribe archivos).

### Etapa 2a: qué quedó

| Antes (raíz) | Ahora | Se importa como |
|---|---|---|
| `plataforma.py`, `persistencia.py`, `registro.py` | `transcripcion/base/` | `from transcripcion.base import registro as L` |
| `ajustes.py` | `transcripcion/ajustes.py` | `from transcripcion import ajustes` |
| `borradores.py`, `paciente.py`, `indice_casos.py` | `transcripcion/casos/` (`indice.py`) | `from transcripcion.casos.indice import IndiceCasos` |
| `cola_procesamiento.py`, `lotes_ia.py`, `cache_transcripcion.py` | `transcripcion/procesamiento/` (`cola.py`, `lotes.py`) | `from transcripcion.procesamiento import cola as CP` |
| `almacen_aprendizaje.py`, `aprendizaje_pendiente.py` | `transcripcion/aprendizaje/` (`almacen.py`, `pendiente.py`) | `from transcripcion.aprendizaje import almacen as AL` |
| `usuarios.py` | `transcripcion/acceso/usuarios.py` | `from transcripcion.acceso import usuarios as U` |

- Los alias de siempre (`L`, `P`, `U`, `CP`, `AL`…) se conservan: el código que los usa no cambió.
- `transcripcion.RAIZ` es la carpeta del sistema. `plataforma`, `registro`, `usuarios` y `ajustes` ubican los datos
  de la instalación (registros, usuarios.json, conocimiento, cloudflared, configuracion.json) desde ahí y no desde
  su propia carpeta: `pruebas/test_paquete.py` lo verifica. Los nombres de los archivos de datos no cambiaron.
- `mantenimiento.py`: el aviso «código cambiado, hace falta reiniciar» incluye los módulos del paquete
  (`transcripcion/base/registro.py`…) y la prueba previa al reinicio compila también el paquete
  (`pruebas/test_mantenimiento_codigo.py`).
- `pruebas/validar_gpu_real.py` y `pruebas/comparar_cpu_gpu.py` copian el paquete. Estaban rotas desde que
  `nucleo.py` importa `usuarios` (no lo copiaban). `medir_listado.py` y el artefacto del CI también lo incluyen.

### Etapa 3: qué quedó

`nucleo.py` (~1.400 líneas) ya no existe. Se partió por responsabilidad, sin ciclos entre módulos:

| Módulo | Alias | Contenido |
|---|---|---|
| `transcripcion/conocimiento/archivos.py` | `CON` | `CONOC`, `preparar_conocimiento`, `leer` |
| `transcripcion/conocimiento/plantillas.py` | `PL` | secciones generales y propias, categorías, títulos de estudio, texto fijo, plantillas relevantes |
| `transcripcion/conocimiento/medicos.py` | `MED` | `DIR_MED`, notas generales y propias, alta/baja/cambio |
| `transcripcion/ia/prompt.py` | `PR` | `SISTEMA`, `reglas_de`, `armar_mensajes` |
| `transcripcion/ia/ejemplos.py` | `EJEM` | banco de ejemplos, `elegir_ejemplos`, referencias de estilo |
| `transcripcion/ia/ollama.py` | `OLL` | `OLLAMA`, `ollama_modelos`, `llamar_ia`, `liberar_ia` |
| `transcripcion/controles/marcas.py` | `MAR` | `marcar` y sus motivos, alineación, palabras raras, `a_html`, `buscar_tiempo`, `texto_limpio` |
| `transcripcion/controles/clinicos.py` | `CLI` | Bi-Rads, ACR, términos clave |
| `transcripcion/controles/avisos.py` | `AV` | `omisiones`, `estudios_sin_plantilla` |
| `transcripcion/controles/orden.py` | `ORD` | `ordenar_estudios` |
| `transcripcion/informe/formato.py` | `FMT` | negritas del Word |
| `transcripcion/texto/palabras.py` | `PAL` | `palabras_norm` |

- Se partió con un script: cada definición fue a su módulo tal cual y las referencias cruzadas se calificaron con
  el alias del módulo dueño (usando los avisos `F821` de ruff, que dan la posición exacta). Así las variables que
  las pruebas reemplazan (`CON.CONOC`, `MED.DIR_MED`, `OLL.OLLAMA`, `OLL._post`) se leen siempre del módulo dueño.
- Tres auxiliares que se usan desde otros módulos dejaron de ser privados: `palabras_norm`, `clave_titulo`, `partir`.
- No se dejó un `nucleo.py` de compatibilidad: con uno así, `patch.object(N, "CONOC", …)` habría dejado de aislar
  las pruebas sin dar error. Todos los usos (`servidor`, `informe`, `aprender`, `estadisticas`, `correcciones`,
  pruebas, herramientas de GPU, `instalar.sh`) pasaron a los módulos nuevos.
- `instalar.sh` preparaba el conocimiento con `import nucleo` (efecto al importar, quitado en la etapa 1): ahora
  llama a `preparar_conocimiento()`.
- `.gitignore` excluye `conocimiento/` por nombre en cualquier carpeta: se agregó la excepción
  `!/transcripcion/conocimiento/` y `test_paquete.py` verifica que ningún archivo del paquete quede ignorado.
- `fase1_transcribir` sigue en la raíz (los módulos nuevos lo importan): pasa al paquete en la etapa 4.

### Etapa 9: qué quedó

- **Formato**: `ruff format` en todo `transcripcion/`, en un commit solo de formato (el AST de cada archivo es el mismo
  antes y después) que `git blame` saltea (`.git-blame-ignore-revs`; en local: `git config blame.ignoreRevsFile
  .git-blame-ignore-revs`).
- **Reglas estrictas en todo el paquete** (`transcripcion/ruff.toml`, antes solo `transcripcion/http/`): imports
  ordenados; variables `l` → `linea`/`renglon` (renombradas por función y verificadas comparando el AST); lambdas
  asignadas → funciones; líneas largas partidas sin cambiar el texto de los SQL ni de los mensajes. El texto del
  prompt de la IA (`ia/prompt.py`) no se reacomoda: cambiaría lo que se le manda a la IA.
- **Tipos**: mypy sin errores en el paquete, con anotaciones en las colecciones de módulo que no podía inferir.
- **Cobertura**: medida en el CI con piso (ver «Calidad del código»).
- De paso: `aprendizaje/aprender.py` y `conocimiento/importar.py` ya no reconfiguran `sys.stdout` al importarse (lo
  pendiente de la etapa 1); lo hacen sus lanzadores de la raíz.
- Sube el servidor (2026.11.12) porque cambió código que corre en él, aunque no su comportamiento: contratos, suite y
  pruebas de navegador en verde sin regenerar nada.

### Etapa 2b: qué quedó

En la raíz quedan solo los puntos de entrada: `servidor.py` (lo abren los `.bat`/`.sh`), `informe.py` (modo
consola) y los lanzadores `aprender.py` e `importar_informes.py`. `test_paquete.py` lo verifica.

| Carpeta | Archivos |
|---|---|
| `scripts/` (operación de la instalación) | `configurar_acceso`, `configurar_tunel`, `mantenimiento_cola`, `mantenimiento_aprendizaje`, `preparar_activacion`, `verificar_paquete`, `rollback_datos`, `crear_entorno_pruebas` |
| `herramientas/` (desarrollo y evaluación) | `fase1_transcribir`, `verificar_versiones` y, desde `pruebas/`, `medir_listado`, `medir_aprendizaje`, `validar_gpu_real`, `resumir_gpu_real`, `comparar_cpu_gpu`, `comparar_il` |

- **Sin lanzadores en la raíz** (el plan los preveía): los únicos que llaman a estos archivos son nuestros `.bat`/`.sh`,
  el CI, `compilar.ps1` y la documentación, y todos se actualizaron en el mismo PR. `configurar_acceso.bat`,
  `configurar_tunel.bat`, `instalar.bat` (y sus `.sh`, `iniciar_servidor.sh`, `servicio.sh`) siguen en la raíz con el
  mismo nombre; solo cambia la ruta del `.py` adentro. `iniciar_servidor.bat` no se tocó (Windows lo lee mientras
  corre el servidor).
- Se ejecutan igual que antes, con la carpeta: `python scripts/mantenimiento_cola.py …`,
  `python herramientas/verificar_versiones.py`. No son paquetes (sin `__init__.py`): cada uno que importa
  `transcripcion` agrega la carpeta del sistema a `sys.path` al empezar (`RAIZ = Path(__file__).resolve().parents[1]`);
  los que ubicaban la instalación por su propia carpeta (`crear_entorno_pruebas`, `preparar_activacion`,
  `verificar_versiones`, `fase1_transcribir`) ahora usan esa `RAIZ`. Los que venían de `pruebas/` ya usaban
  `parents[1]` y no cambiaron.
- `test_importar_sin_efectos.py` ahora también importa cada archivo de `scripts/` y `herramientas/` desde su carpeta
  (como al ejecutarlo): comprueba que encuentren el paquete solos y que importarlos no escriba nada.
- El artefacto del CI incluye `scripts/` y `herramientas/` (`instalar.bat` usa `herramientas/fase1_transcribir.py`).
- Sin versión nueva: no cambia código que corre en el servidor ni en la app. Al actualizar la instalación con
  `git pull` no hace falta reiniciar.
- De paso: la sugerencia de `fase1_transcribir` cuando falla la GPU nombraba un `fase1_transcribir.bat` que no existe;
  ahora dice `python herramientas\fase1_transcribir.py --device cpu`.

### Etapa 8: qué quedó

`VentanaPrincipal.cs` (~1.500 líneas) quedó en ~190: los campos, el arranque oculto y el constructor. El resto se
movió, sin cambiar líneas, a archivos de la misma clase (`partial class`), uno por sección de las que ya tenía:

| Archivo | Qué tiene |
|---|---|
| `VentanaPrincipal.Barra.cs` | Barra de estado propia: punto, textos, botones, menú Opciones |
| `VentanaPrincipal.Conexion.cs` | Consulta de estado al Servidor cada 10 s, casos listos |
| `VentanaPrincipal.Web.cs` | WebView2: iniciar, cartel propio si la página no carga, reintentar, entrar, abrir en Edge |
| `VentanaPrincipal.Puente.cs` | Mensajes con la página: `MensajeDeLaPantalla` (lo que pide la página), `AnunciarApp`, `EjecutarEnWeb` |
| `VentanaPrincipal.Aviso.cs`, `.Bandeja.cs`, `.Actualizacion.cs`, `.Compacto.cs` | Aviso abajo a la derecha; ícono junto al reloj; actualización automática; modo compacto y sus íconos |
| `VentanaPrincipal.Audios.cs`, `.Autocorreccion.cs`, `.Tema.cs`, `.Configuracion.cs`, `.Acciones.cs` | Audios desde la pantalla; autocorrección de Word; tema; configuración; acciones del menú |
| `RelojUi.cs` | El reloj que funciona con la ventana escondida (era otra clase dentro del mismo archivo) |

- **Mismo programa**: se compiló con Mono antes y después (misma versión) y el IL es el mismo instrucción por
  instrucción; solo cambian los nombres que inventa el compilador para lambdas y `async`. La comparación quedó como
  herramienta: `pruebas/comparar_il.py` (ver `docs/compilacion.md`). El CI compila en Windows con `dotnet build`.
- Los campos con valor inicial quedan todos en `VentanaPrincipal.cs`: entre archivos de una partial class, C# no
  garantiza en qué orden se inicializan.
- La única reubicación fuera de las secciones: `MensajeDeLaPantalla` (estaba en la sección de autocorrección) y
  `AnunciarApp`/`EjecutarEnWeb` (en la de audios) pasaron a `Puente`, que es lo que son.
- **Por qué partial y no clases separadas**: casi todos los métodos usan los mismos controles (barra, `web`,
  `bandeja`, estado de conexión). Sacar, por ejemplo, la bandeja a una clase propia obliga a definir eventos y
  referencias cruzadas, y eso necesita probar la app en Windows (WebView2 no corre en Linux). Queda como siguiente
  paso cuando se toque cada área por un cambio funcional; ahora cada área ya está aislada en su archivo.
- Versión: va en la App 1.25 (la misma entrega que la etapa 7, todavía sin publicar); el servidor no cambia.

### Etapa 7: qué quedó

`web/index.html` bajó de ~3.570 a ~370 líneas: queda el HTML. Los ~645 renglones de CSS pasaron a
`web/css/principal/` (7 partes) y los ~2.555 de JavaScript a `web/js/principal/` (26 partes: `010-base.js`,
`020-lista.js`, `030-preferencias-usuario.js`, … `220-onda.js`, `250-configuracion.js`, `260-mi-cuenta.js`), cortados
en las secciones que ya tenía el script, sin cambiar una línea (cada parte empieza con un comentario de qué tiene).

- **Un solo script, como antes.** El servidor une las partes en orden de nombre y las envía como `/js/principal.js`
  (y `/css/principal.css`); `index.html` las carga en el mismo lugar donde estaban. Se descartó cargar 26 `<script>`
  separados: en un único script todas las funciones existen antes de ejecutar el código de arranque (el de
  `050-inicio.js`, `cargarLista()` y `cargarMiPc()`, puede llamar a funciones de partes posteriores), y con archivos
  separados eso dependería del orden y de cuándo llega cada uno por el túnel. También se descartaron los módulos ES (`import`): la app del
  trabajo y los `onclick` del HTML llaman a funciones globales (`window.ponerApp`, `salirDeSesion`…).
- Verificado: las partes unidas dan el mismo árbol de sintaxis (AST) que el script original, y el CSS, el mismo texto
  salvo los comentarios de cada parte. Con un servidor simulado de antes y de después, las capturas de la lista, de un
  caso abierto y de la vista previa (F9) son idénticas píxel a píxel (salvo la hora del último audio), sin errores
  en la consola.
- Numeración con saltos de 10 para poder agregar una parte entre dos (`155-…js`). `verificar_fuentes.cjs` revisa cada
  parte, el script unido y las funciones repetidas en todo el script. Las pruebas de Playwright con servidor propio
  arman `/js/principal.js` y `/css/principal.css` igual que el servidor (`pruebas/web_pruebas.cjs`).
- **Versión**: Servidor 2026.11.11 y App 1.25. La App se subió aparte, después de fusionar el PR #23, a pedido del
  usuario: se mantiene la regla de `AGENTS.md` (todo cambio de la página que usa la app = versión nueva de la app,
  aunque el C# no cambie), que ahora cubre también `web/js/principal/` y `web/css/principal/`.
- **Activación**: después del `git pull` la página no carga hasta reiniciar el servidor (`index.html` ya pide
  `/js/principal.js` y el servidor viejo no tiene esa ruta). Reiniciar desde el panel enseguida, en un momento sin
  trabajo; el panel no cambia.
- Queda para más adelante: cada parte sigue usando globales compartidas (`actual`, `casosCache`, `MI`…). Pasar a
  módulos con dependencias explícitas es un trabajo aparte, conviene hacerlo área por área con pruebas de Playwright.

### Etapa 6c: qué quedó

Las ~100 rutas que estaban en dos cadenas de `if` dentro de la clase `H` de `servidor.py` (~880 líneas) pasaron a
`transcripcion/http/`. `servidor.py` bajó de ~1.700 a ~310 líneas: `configurar`, `abrir_tunel`, el encabezado de la
consola y `main`.

| Módulo | Qué tiene |
|---|---|
| `manejador.py` | `Manejador` (antes `H`): respuestas comunes (`_json`, `_html`, `_redirigir`, `_enviar_archivo`), autorización y despacho; `ManejadorTunel` (antes `HTunel`) |
| `rutas.py` | `Rutas` (exactas antes que prefijos, sin repetidas), `Ruta` (función, fase, `libre`), `Pedido` (ruta, `q`, `datos`, `nombre`) |
| `tabla.py` | Todas las rutas: `RUTAS.get("/api/casos", casos.lista)`, `RUTAS.post("/api/borrador", edicion.borrador, "caso", libre=True)`… |
| `sistema.py` | `Sistema`: ajustes, servicios (`casos`, `proc`, `vista`…), `tunel`, `visto`, candados. Lo arma `configurar` con los mismos objetos que `S.CASOS`, `S.PROC`… |
| `acceso`, `paginas`, `casos`, `edicion`, `audios`, `cliente`, `conocimiento`, `voces`, `usuario` | Una función `f(h, pedido)` por ruta |
| `panel`, `panel_estado`, `panel_acciones` | Páginas y permisos del panel; `estado_admin` y la cola en vivo; `accion_admin` (los botones) |

- **Despacho de un POST, igual que antes**: las rutas «crudas» leen el cuerpo a su manera (audios, Word, formulario
  de entrar); el resto se lee como JSON; desde la fase «caso» se valida `nombre` (400 si no es válido, también para
  una ruta desconocida, antes del 404) y las rutas `libre=True` responden 409 si otra PC tiene el caso abierto
  (`edicion.caso_ocupado`). Los errores (cola, Word abierto, otros) se responden igual que antes.
- **Sin globales en las rutas**: cada sistema configurado tiene su clase de manejador, `Manejador.para(sis)`; las
  funciones leen `h.sis`. `S.H` es esa clase (la usan `main`, el túnel y las pruebas).
- Las funciones se generaron con un script (en la sesión): el cuerpo de cada `if` pasó tal cual, cambiando solo
  nombres (`self` → `h`, `CASOS` → `sis.casos`, `u.path` → `pedido.ruta`), y después se les aplicó `ruff format`.
- **Páginas fuera de las cadenas**: entrar, panel desde el trabajo, panel no habilitado y «solo en el servidor»
  están en `web/plantillas/` (marcadores `{{…}}`). Se leen como texto en cada pedido: el resultado es idéntico al de
  antes byte a byte, también con los fines de línea de Windows. `verificar_fuentes.cjs` saltea esa carpeta.
- `placa_de_video` → `transcripcion/operacion/gpu.py`, con una lectura compartida cada 3 s para el panel y la consola.
- **Calidad**: `transcripcion/http/` es el primer paquete con reglas estrictas (`E`, `W`, `I`, `B`, `UP` en
  `transcripcion/http/ruff.toml`) y `ruff format`; el CI corre `ruff format --check transcripcion/http`.
- Pruebas: `pruebas/test_rutas.py` fija la tabla (ruta → función), las fases de los POST y el despacho (nombre
  inválido antes del 404, JSON inválido, caso abierto en otra PC, páginas). Las pruebas que levantan el servidor en el
  mismo proceso parchean `S.SIS.puerto` en lugar de `S.PUERTO`; `test_medicos.py` ahora configura el servidor.
- Además de la suite y los contratos, se comparó un servidor simulado de antes y de después con 36 pedidos (panel,
  páginas del trabajo, vincular, mensajes, reinicio, voces, rutas desconocidas, subir, bloquear, paciente, médico,
  formato, pausa, audio, caso, borrar): mismas respuestas, salvo el número de puerto.
- Queda para más adelante: `servidor.py` → `transcripcion/app.py` con `servidor.py` de pocas líneas. Hoy las
  pruebas usan `S.configurar`, `S.CASOS`, `S.H`…; conviene hacerlo junto con un objeto `App` que reemplace esas
  globales.

### Etapa 6b: qué quedó

La etapa 6 se partió en tres: el HTTP (ahora 6c) necesita usar `remoto`, `admin`, `estadisticas`… y el paquete no
importa nada de la raíz. Primero se movieron esos módulos, sin cambiar su código (salvo `AQUI = RAIZ`):

| Antes (raíz) | Ahora | Alias de siempre |
|---|---|---|
| `remoto.py`, `admin.py` | `transcripcion/acceso/` | `R`, `ADM` |
| `mantenimiento.py`, `estadisticas.py`, `app_cliente.py` | `transcripcion/operacion/` | `M`, `EST`, `A` |
| `aprender.py`, `correcciones.py` | `transcripcion/aprendizaje/` | `APRENDER` (`A` en las pruebas), `CORR` |
| `importar_informes.py` | `transcripcion/conocimiento/importar.py` (`main(argv)` nuevo) | — |

- En la raíz quedan `aprender.py` e `importar_informes.py` como **lanzadores de consola** (solo un
  `if __name__ == "__main__":` que llama al paquete), para quien los corre a mano o los tiene en la documentación.
  `test_paquete.py` verifica que no definan nada: así `patch.object(aprender, …)` sobre el lanzador falla en vez de
  no reemplazar lo que usa el sistema.
- Cada módulo movido ubica sus datos desde `RAIZ` (`acceso_remoto.json`, `sesiones.json`, `cliente/`,
  `resultados/historial.csv`, `ejemplos/`, `referencias/`, `.git` para la versión del código): `test_paquete.py`
  lo verifica archivo por archivo. `MOVIDOS` incluye los seis que ya no tienen lanzador.
- `mantenimiento` sigue viendo el código cambiado del paquete (ya lo hacía desde la 2a) y la prueba previa al
  reinicio compila la raíz y el paquete igual que antes.
- Los servicios que recibían estos módulos en el constructor (`VistaCasos`, `Borrado`, `Operacion`, `Guardado`)
  los siguen recibiendo: es la misma inyección de dependencias, y las pruebas pueden pasar dobles.
- Usos actualizados: `servidor.py`, `informe.py`, `configurar_acceso.py`, `configurar_tunel.py`,
  `mantenimiento_aprendizaje.py`, `verificar_versiones.py`, pruebas (`usuarios.cjs` arma el servidor con Python
  embebido) y la documentación.

### Etapa 6a: qué quedó

`servidor.py` bajó de ~2.910 a ~1.700 líneas. `configurar(ajustes)` arma los objetos en orden de dependencia, cada
uno con lo que usa en su constructor (sin buscar globales):

```python
CASOS = Casos(DATOS, NUEVOS)
PROC = Procesamiento(CASOS)
IA = EstadoIA(CFG, SIMULAR, AQUI, CASOS, PROC)                       # transcripcion/operacion/ia.py
VOCES = ServicioVoz(CFG, CASOS, PROC)                                # transcripcion/voz/servicio.py
VISTA = VistaCasos(CASOS, PROC, VOCES, INICIO, R)                    # transcripcion/casos/vista.py
BORRADO = Borrado(CASOS, PROC, INFORMES, R)                          # transcripcion/casos/borrado.py
OPER = Operacion(CASOS, PROC, COLA_AL_REINICIAR, TUNEL, SRV, FIN_LOCK, M)   # transcripcion/operacion/reinicio.py
TRAB = Trabajador(CFG, SIMULAR, AQUI, INFORMES, COLA_AL_REINICIAR, CASOS, PROC, IA, VOCES, VISTA, OPER)
GUARDADO = Guardado(CFG, INFORMES, CASOS, VOCES, FIN_LOCK, APRENDER, EST)   # transcripcion/informe/guardado.py
APRENDIZAJE = ColaAprendizaje(..., GUARDADO.aplicar_aprendizaje, GUARDADO.analizar_aprendizaje)
GUARDADO.aprendizaje = APRENDIZAJE
```

- También se movieron: `voces.py` → `transcripcion/voz/huellas.py` (con `RAIZ` para `modelos/` y `voces/`); el Word de
  `informe.py` (hoja, párrafos, formato, `escribir_docx`) → `transcripcion/informe/word.py`; `texto_marcas` y
  `mensaje_amigable` → `transcripcion/base/formatos.py`; `SUFIJOS_CASO` → `casos/repositorio.py`.
- Los módulos de la raíz que todavía usan algunos servicios (`remoto`, `mantenimiento`, `aprender`, `estadisticas`)
  se les pasan en el constructor: el paquete sigue sin importar nada de la raíz. Pasaron al paquete en la etapa 6b.
- Pruebas: parchean métodos de los objetos (`S.TRAB`, `S.VISTA`, `S.VOCES`, `S.IA`, `S.BORRADO`, `S.GUARDADO`) o, si
  el objeto lo crea `main()`, el método en la clase (`patch.object(Trabajador, "reanudar_cola")`). Un «reinicio» en una
  prueba es `S.configurar(aj)` otra vez (objetos nuevos con las mismas carpetas).
- Además de la suite, se probó un servidor real en modo simulado: subir, pausar a mitad de la transcripción,
  panel de administración, reanudar, informe listo y mensaje a las PC, sin errores en la consola.

### Etapa 5: qué quedó

| Antes (globales de `servidor.py`) | Ahora |
|---|---|
| `titulo_de`, `origen_de`, `medico_de`, `usuario_de`, `estilo_de`, `estudios_de`, `ruta_audio`, `duracion_de`, `visible`, `datos_csv`, `sumar_revision`, `revision_de`, `revisado_en`, `fecha_caso`, `formato_de`, `voz_de`, `guardar_voz`, `anotar_voz`, `resumen_avisos`, `poner_usuario_caso` y las cachés `_ESTUDIOS`, `DURACION`, `VOZ_CACHE`, `INDICE_CASOS` con sus candados | `CASOS`: instancia de `transcripcion.casos.repositorio.Casos(datos, nuevos)` |
| `ESTADO`, `LOCK`, `COLA`, `COLA_DURADERA`, `ENCOLADO`, `BORRADOS`, `PAUSAS`, `PAUSA_CV`, `PAUSADO_S`, `TIEMPOS`, `TRABAJO`, `ENCOLAR_LOCK` y `poner_estado`, `empezar`, `en_proceso`, `cola_pendiente`, `esperas`, `encolar`, `pausar`, `reanudar`, `punto_de_pausa`, `avance`, `sincronizar_terminal`, `cargar_tiempos`, `anotar_tiempo`, `_en` | `PROC`: instancia de `transcripcion.procesamiento.estado.Procesamiento(casos)` (`PROC.estado`, `PROC.cola`, `PROC.duradera`…; `_en` → `en_estado`) |
| `mmss`, `pct_voz`, `duracion_wav` | `transcripcion/base/formatos.py` |
| `LOCAL`, `EXT_AUDIO` | `transcripcion/casos/repositorio.py` (también los usa `informe.py`) |

- `configurar(ajustes)` crea `CASOS` y `PROC` nuevos; `configurar(None)` los quita. Una prueba que necesita otra
  carpeta lo dice en los ajustes (`ajustes.para_pruebas(base, carpeta_informes=…, carpeta_audios_nuevos=…)`) en
  lugar de reemplazar `DATOS`, `ESTADO`, `COLA`… uno por uno; para cambiar un comportamiento parchea el método del
  objeto (`patch.object(S.CASOS, "ruta_audio", …)`, `patch.object(S.PROC, "encolar")`).
  `pruebas/test_casos_procesamiento.py` prueba los dos objetos sin importar el servidor.
- Se extrajo con `extraer_clase.py` (en la sesión, no en el repo): cada función pasó tal cual a método y los
  usos de sus globales a `self.…`; en `servidor.py` los usos que quedaron (posiciones de ruff F821) pasaron a
  `CASOS.…` / `PROC.…`.
- Quedan en `servidor.py`, ya usando los objetos: el trabajador, `listar_casos`, `borrar_caso`, `reanudar_cola`, la
  voz, el reinicio y los mensajes, el túnel y el estado de la IA, y todo el HTTP. Salen en la etapa 6
  (6a servicios, 6c HTTP): el trabajador depende de la voz, las marcas y la espera de la IA, que todavía están
  en `servidor.py`, y moverlo antes obligaba a pasarle el módulo entero.

### Etapa 4: qué quedó

| Antes | Ahora |
|---|---|
| `fase1_transcribir.py`: `sin_acentos`, `palabras_a_numeros`, `normalizar`, `datos_criticos` | `transcripcion/texto/normalizacion.py` |
| `fase1_transcribir.py`: CUDA, `cargar_modelo`, `cargar_audio`, `leer_vocabulario`, `transcribir`, `duracion`, `VOCAB_DEF` | `transcripcion/asr/whisper.py` |
| `huecos.py` | `transcripcion/asr/huecos.py` |
| `fase1_transcribir.py` (evaluación de la fase 1 y `--verificar`) | Sigue en la raíz, solo con el reporte y `main()`: lo llaman `instalar.bat` e `instalar.sh` |

- Ningún módulo del sistema depende ya de `fase1_transcribir.py`: el paquete no importa nada de la raíz.
- El servidor usa `W.transcribir`, `W.cargar_modelo`, `H.reparar`… como atributos del módulo (con import diferido,
  igual que antes), así las pruebas los reemplazan en `transcripcion.asr.whisper` / `huecos`.
- La caché de transcripción se firma con el hash del código que transcribe: ahora `transcripcion/asr/whisper.py`,
  `transcripcion/asr/huecos.py` y el vocabulario (antes `fase1_transcribir.py` y `huecos.py`). Consecuencia
  esperada: después de actualizar, «Regenerar» un caso existente vuelve a pasar una vez por Whisper. La firma ya no
  depende de `S.AQUI`: `test_lotes_ia` dejó de copiar esos archivos a su carpeta temporal.

## Red de seguridad (etapa 0)

**Contrato HTTP** (`pruebas/test_contrato_http.py`): copia el código versionado a una carpeta temporal dentro de
`respaldo/`, arranca `servidor.py` en un subproceso con `SIMULAR_IA=1` y un puerto libre (sin internet: no baja
el modelo de voz), y recorre por HTTP: página, lista, estado para la app, subir audio, procesamiento simulado,
abrir el caso, onda, borrador con control de revisión (409/400), guardar Word, descargarlo, validar nombres,
borrar; además formato y vista previa, plantillas y médicos, permisos del panel y 404. Falla si el servidor
escribe un `Traceback` en su consola. No importa ningún módulo: no cambia cuando el código se mueve.

**Contrato del núcleo** (`pruebas/test_contrato_nucleo.py`): ejecuta `pruebas/contratos/calcular_nucleo.py`
en una copia del sistema con el conocimiento de ejemplo, sobre los casos ficticios de
`pruebas/contratos/casos_nucleo.json` (números distintos, Bi-Rads, lado, números juntados por Whisper, baja
confianza, orden de estudios, `[COMPLETAR]`, `[[?…]]`, «protocolo normal» literal, niveles y horas), y compara
con `nucleo_esperado.json`: texto normalizado, marcas con sus motivos, HTML, omisiones, categorías, estudios sin
plantilla, orden, párrafos del Word y los mensajes completos que se mandan a la IA.

Para un cambio funcional **deliberado** (no un refactor), regenerar y revisar el diff en el PR:

```bash
ACTUALIZAR_CONTRATOS=1 python -m unittest pruebas.test_contrato_nucleo
```

Para sumar un caso: agregarlo a `casos_nucleo.json` y regenerar (el diff del PR solo debe mostrar el caso nuevo).

## Calidad del código

Desde la etapa 9 el CI corre, además de las pruebas:

| Qué | Dónde se configura | Comando |
|---|---|---|
| ruff, errores reales en todo el repositorio (`E9`, `F`) | `pyproject.toml` → `[tool.ruff]` | `python -m ruff check .` |
| ruff estricto (`E`, `W`, `I`, `B`, `UP`) en el paquete | `transcripcion/ruff.toml` (extiende `pyproject.toml`) | (el mismo `ruff check .`) |
| Formato del paquete | `transcripcion/ruff.toml` | `python -m ruff format --check transcripcion` |
| Tipos (mypy) en el paquete; `transcripcion.http` también revisa funciones sin anotar | `pyproject.toml` → `[tool.mypy]` | `python -m mypy` |
| Cobertura de las pruebas sobre el paquete, con piso | `pyproject.toml` → `[tool.coverage]` (`fail_under`) | `python -m coverage run -m unittest discover -s pruebas -p 'test_*.py'` y `python -m coverage report` |

Las versiones de ruff, mypy y coverage están fijas en `requirements-ci.txt`.

- **Qué sigue con reglas mínimas**: `servidor.py`, `informe.py`, `scripts/`, `herramientas/` y `pruebas/`. Para sumar uno,
  formatearlo en un commit aparte (y agregarlo a `.git-blame-ignore-revs`), corregir lo que marque ruff con las reglas
  estrictas y extender la configuración (un `ruff.toml` en su carpeta o `extend-select` por archivo).
- **mypy**: sin anotaciones obligatorias. Siguiente paso: `check_untyped_defs` en más módulos (hoy solo
  `transcripcion.http`), empezando por los que tienen menos avisos.
- **Cobertura**: 53,4 % del paquete (piso del CI: 50 %). Es un piso: no cuenta lo que corre en otro proceso (el servidor
  del contrato HTTP corre sobre una copia en `respaldo/`). Lo menos cubierto: `asr/` (Whisper, solo con GPU), `voz/`,
  `aprendizaje/correcciones.py`, `conocimiento/importar.py`, `http/panel_acciones.py`, `operacion/reinicio.py`.
  Subir `fail_under` cuando se agreguen pruebas.
- `B023` (funciones definidas en un bucle que usan la variable del bucle): los casos de `casos/vista.py` y
  `controles/clinicos.py` están marcados con `# noqa: B023` y un comentario: la función se usa en la misma vuelta del
  bucle (se pasa a `partir()` o a `IndiceCasos.obtener()`, que la llaman enseguida).
