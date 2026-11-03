# Plan de refactor: código modular, legible y mantenible

*Iniciado el 03/11/2026. Decisión y alternativas en [ADR 0001](adr/0001-modularizar-por-etapas.md).
Este documento es la guía de trabajo: se actualiza al cerrar cada etapa (tabla «Estado»).*

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
│   └── http/                   servidor, tabla de rutas, handlers por área, páginas HTML
├── web/                        index.html + css/ + js/ (módulos), admin, estadísticas…
├── scripts/                    configurar_acceso, configurar_tunel, mantenimiento_*, activación, rollback…
├── herramientas/               evaluación (fase 1/2/5), verificación de versiones y paquete, mediciones
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
5. **Versión**: un refactor que cambia código que corre en el servidor sube la versión del servidor
   (`AAAA.MM.N`) para que el panel muestre qué código está corriendo. En el CHANGELOG va bajo
   «Cambiado» como *reorganización interna, sin cambios visibles*. Si toca `web/index.html`, sube también la app.
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
| 2b | **Scripts y herramientas** | Scripts de mantenimiento y activación a `scripts/`, herramientas de desarrollo y evaluación a `herramientas/`, dejando lanzadores en la raíz para lo que se usa desde un `.bat` o desde la documentación | Bajo | — |
| 3 | **Núcleo** | `nucleo.py` → `conocimiento/` (archivos, plantillas, médicos), `ia/` (ollama, ejemplos, prompt) y `controles/` (marcas, clínicos, avisos, orden). Guardia: contrato del núcleo | Bajo | Servidor |
| 4 | **Transcripción** | `fase1_transcribir.py` → `asr/whisper.py` y `texto/normalizacion.py`; `huecos.py` → `asr/huecos.py`. `fase1_transcribir.py` queda como herramienta de evaluación (pasa a `herramientas/` en la 2b) | Bajo | Servidor |
| 5 | **Estado del servidor en objetos** | De `servidor.py`: `Casos` (`casos/repositorio.py`: archivos de cada caso, cachés, índice del listado) y `Procesamiento` (`procesamiento/estado.py`: etapas, cola, pausas, tiempos) como objetos creados en `configurar()`, sin las globales sueltas | **Alto** | Servidor |
| 6a | **Servicios fuera de `servidor.py`** | Trabajador → `procesamiento/trabajador.py`; listado y borrado → `casos/`; voz → `voz/`; reinicio, mensajes y estado del túnel/IA → `operacion/`. Cada uno recibe los objetos que usa | **Alto** | Servidor |
| 6b | **HTTP** | Tabla de rutas y handlers por área (casos, conocimiento, cliente, usuario, admin, páginas); páginas HTML fuera de las cadenas; `servidor.py` queda como entrada de pocas líneas | **Alto** | Servidor |
| 7 | **Página principal** | `web/index.html` → `css/` y módulos `js/` (api, lista, editor, audio y onda, marcas, atajos, usuario) | Medio | Servidor + App |
| 8 | **App de escritorio** | `VentanaPrincipal.cs` en clases por responsabilidad (bandeja, compacto, puente con la página, actualizaciones) | Medio | App |
| 9 | **Calidad continua** | Reglas de ruff y formato por módulo terminado, tipos y mypy en el paquete, cobertura en el CI | Nulo | — |

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
| 5 | `refactor/5-casos-procesamiento` · Servidor 2026.11.7 | En revisión |
| 2b, 6–9 | — | Pendiente |

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
  (6a servicios, 6b HTTP): el trabajador depende de la voz, las marcas y la espera de la IA, que todavía están
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

- `pyproject.toml` → `[tool.ruff]`. Hoy: solo errores reales (`E9`, `F`: sintaxis, nombres sin definir,
  imports y variables sin usar). Corre en el CI (`python -m ruff check .`, versión fijada en `requirements-ci.txt`).
- No se reformatea todo de una vez (serían miles de líneas cambiadas sin valor y conflictos con todo lo abierto).
  Cada módulo que se crea o termina de refactorizar en el paquete entra a reglas más estrictas
  (`E`, `W`, `I`, `B`, `UP`) y a `ruff format`, agregándolo a una lista en `pyproject.toml`.
- `B023` (funciones definidas en un bucle que usan la variable del bucle): revisados los 21 casos en la etapa 5
  (`listar_casos`, `controles/clinicos.py`, `pruebas/resumir_gpu_real.py`). En todos la función se usa en la misma
  vuelta del bucle (se pasa a `partir()` o a `IndiceCasos.obtener()`, que la llaman enseguida), así que no hay error.
  La regla queda desactivada; si se activa, marcar esos casos con `# noqa: B023` y el motivo.