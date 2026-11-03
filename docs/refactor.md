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
│   ├── texto/                  normalización de números, horas y niveles; datos críticos
│   ├── ia/                     cliente de Ollama, plantillas, ejemplos y referencias, prompt
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
   contratos que puede cambiar es `pruebas/contratos/calcular_nucleo.py`, y solo en sus imports.
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
| 1 | **Ajustes y arranque sin efectos** | `transcripcion/ajustes.py`; `servidor.py` deja de leer config y crear carpetas al importarse (todo pasa a `main()`); la descarga del modelo de voz se vuelve configurable; prueba «importar no escribe nada» | Medio | Servidor |
| 2 | **Paquete y carpetas** | Crear `transcripcion/` y mover los módulos que ya son independientes (plataforma, persistencia, registro, borradores, paciente, índice, cola, lotes, caché, almacén de aprendizaje, usuarios). Scripts a `scripts/` y `herramientas/` dejando lanzadores en la raíz. Adaptar `mantenimiento.py` (detección de código cambiado), `crear_entorno_pruebas.py`, el CI y `verificar_paquete.py` | Medio (muchos imports) | Servidor |
| 3 | **Núcleo** | `nucleo.py` → `ia/` (ollama, plantillas, ejemplos, prompt) y `controles/` (marcas, clínicos, omisiones, orden). Guardia: contrato del núcleo | Bajo | Servidor |
| 4 | **Transcripción** | `fase1_transcribir.py` → `asr/whisper.py` y `texto/normalizacion.py`; los reportes de evaluación a `herramientas/` | Bajo | Servidor |
| 5 | **Dominio del servidor** | De `servidor.py`: `casos/` (archivos de un caso, listado, borrado) y `procesamiento/` (trabajador, pausas, tiempos) como objetos con su estado, sin globales | **Alto** | Servidor |
| 6 | **HTTP** | Tabla de rutas y handlers por área (casos, conocimiento, cliente, usuario, admin, páginas); páginas HTML fuera de las cadenas; `servidor.py` queda como entrada de pocas líneas | **Alto** | Servidor |
| 7 | **Página principal** | `web/index.html` → `css/` y módulos `js/` (api, lista, editor, audio y onda, marcas, atajos, usuario) | Medio | Servidor + App |
| 8 | **App de escritorio** | `VentanaPrincipal.cs` en clases por responsabilidad (bandeja, compacto, puente con la página, actualizaciones) | Medio | App |
| 9 | **Calidad continua** | Reglas de ruff y formato por módulo terminado, tipos y mypy en el paquete, cobertura en el CI | Nulo | — |

Orden recomendado: 0 → 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8, con la 9 en paralelo. Las etapas 3 y 4 son buenas
para tomar ritmo (riesgo bajo, contrato del núcleo como guardia) antes de las 5 y 6, que son el corazón.

## Estado

| Etapa | Rama / PR | Estado |
|---|---|---|
| 0 | `test/red-de-seguridad-refactor` | En revisión |
| 1–9 | — | Pendiente |

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
- A revisar en la etapa 5: ruff marca 21 casos de `B023` (funciones definidas en un bucle que usan la variable del
  bucle). La mayoría se llaman en la misma vuelta y son correctas, pero conviene confirmarlo una por una.
