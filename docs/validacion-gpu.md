# Validación de lotes en la GPU real

29/10/2026, Buenos Aires. **Recomendación para el uso diario: máximo de 2 audios y
180 segundos por lote, sin espera para completarlo.** En la RTX 3080 medida, 4 audios
por lote ofrecen más capacidad para colas sostenidas de dictados cortos, a cambio
de demorar el primer informe. No se modificó la configuración local.

## Resultado medido

Se procesó una cola inicial de cuatro audios ficticios por ensayo. Cada tamaño se
repitió tres veces, en orden `1, 2, 4, 4, 2, 1, 2, 4, 1`: **9 ensayos completos y
36 informes**. Las columnas siguientes son medianas independientes de tres ensayos;
la espera se cuenta desde el inicio de la cola, no desde el comienzo de cada audio.

| Máximo de audios por lote | Primer informe | Espera media de los cuatro | Cola completa | Informes/minuto | Rango de cola completa |
|---|---:|---:|---:|---:|---:|
| 1 | 9,40 s | 23,15 s | 36,99 s | 6,49 | 36,38–55,40 s |
| 2 | 11,48 s | 18,62 s | 25,83 s | 9,29 | 24,43–26,10 s |
| 4 | 16,94 s | 18,62 s | 20,44 s | 11,74 | 18,82–20,65 s |

Con 2 frente a 1, la cola se completa un **30,18 % antes** y la tasa aumenta un
**43,23 %**, con 2,08 s adicionales hasta el primer informe. Con 4 frente a 2,
la tasa mejora un **26,35 %**, pero el primer informe demora 5,46 s adicionales.
La espera media resulta prácticamente igual entre 2 y 4 en este corpus: esa
diferencia mínima no fundamenta una preferencia estadística.

El ahorro procede principalmente de alternar menos veces Whisper y Gemma:

| Componente por cola de cuatro, mediana | Lote 1 | Lote 2 | Lote 4 |
|---|---:|---:|---:|
| Cargas de Whisper acumuladas | 7,99 s | 4,11 s | 2,05 s |
| Cargas de IA informadas por Ollama, acumuladas | 13,22 s | 6,64 s | 3,31 s |
| Transcripción y reparación acumuladas | 10,06 s | 9,65 s | 10,27 s |

Estas medianas de componentes no deben sumarse como si fueran una misma muestra.
La tasa de generación agregada, calculada como tokens de salida / tiempo de
evaluación de Ollama, fue 138,38 / 145,11 / 152,16 tokens/s para lotes 1/2/4.
No equivale a informes/minuto ni demuestra un cambio de velocidad intrínseca del modelo.

## Elección de configuración

- **Uso interactivo habitual:** `lote_max_audios: 2`, `lote_max_segundos: 180`.
  Mantiene un equilibrio entre disponibilidad temprana y capacidad. Si hay un único
  audio disponible, el trabajador lo toma inmediatamente: no espera otro para formar pareja.
- **Vaciado de cola de audios cortos:** considerar `lote_max_audios: 4`, conservando
  el presupuesto de 180 s. Los cuatro audios medidos suman 157,89 s; audios más largos
  pueden hacer que el presupuesto reduzca el lote efectivo. Confirmar que el retraso
  adicional del primer informe sea aceptable para la revisión.
- **Prioridad absoluta al primer informe con cola ya formada:** 1 fue el más rápido
  en esta métrica, con menor capacidad total. No es la recomendación general.

No se activó una política adaptativa ni se cambió el modelo, la cuantización, el
contexto, la temperatura o los controles. La recomendación de 2 confirma el valor
predeterminado del candidato App 1.22 / Servidor 2026.10.46; no constituye su despliegue.

## Equipo, entradas y procedimiento

- GPU NVIDIA GeForce RTX 3080, 10.240 MiB; driver 621.01. CPU AMD Ryzen 9 9900X.
- Windows, Python 3.12.10, Ollama 0.40.13; faster-whisper 1.2.1 y CTranslate2 4.8.3.
- Whisper large-v3 local, CUDA/float16, idioma español, beam 5, VAD y reparación de
  huecos del código de la aplicación. Sin reutilizar caché ASR entre ensayos.
- Gemma `gemma4:12b`, 11,9B, Q4_K_M; contexto 12.288, temperatura 0,1, tres ejemplos
  ficticios fijos y los controles de marcado/omisiones de `transcripcion/controles/`.
- Cuatro dictados inventados: tiroides, mamografía, tórax y abdomen. Voz local
  Microsoft Sabina Desktop, velocidad -1, WAV mono PCM16 a 16 kHz. Duraciones:
  40,39 / 40,21 / 36,26 / 41,03 s. No se leyeron casos, audios, ejemplos aprendidos,
  reglas particulares, configuración privada o informes de pacientes.

Se copiaron solo los módulos necesarios, el vocabulario y `conocimiento.ejemplo/`
a una carpeta de ensayo. Se reutilizaron pesos ya instalados, sin descargas. Por
lote se transcriben/reparan sus audios, se libera Whisper y se generan sus informes
secuencialmente con Gemma. No hay inferencia GPU paralela. Las esperas incluyen
cargas, transcripción, reparación, IA y controles; el tiempo total incluye además
las consultas/instrumentación y escrituras de ensayo. No incluyen síntesis previa,
Word, reconocimiento de médico por voz, túnel ni interfaz de revisión.

Los registros del daemon de ensayo confirman CUDA y **49/49 capas del modelo principal
y 5/5 del asistente en GPU**. `/api/ps` informó una memoria cercana a 1,15 GB que no
representa todos los buffers: el propio log registra 7.024,41 MiB para el buffer del
modelo principal en CUDA. Las muestras de `nvidia-smi` se toman al terminar informes;
no son una medición continua ni un máximo de VRAM. No se usa ese dato parcial para
afirmar cuánto margen de memoria queda en producción.

## Protección del trabajo y trazabilidad

Antes de comenzar, el servidor 8765 no estaba escuchando, no había otros procesos
Python de aplicación y Ollama 11434 no tenía modelos cargados. No se detuvo ningún
servicio para crear esa ventana. La prueba levantó su propio daemon en 11435, sin
descargar modelos de la instancia habitual. El controlador vigila producción
aproximadamente cada segundo y cancela su propio árbol si comienza a escuchar el
servidor, se carga un modelo habitual, aparece Python ajeno o falla la consulta de
estado. Es una precaución conservadora; no es una reserva exclusiva de recursos del SO.

Una consulta de progreso lanzada inicialmente desde otro Python activó esa vigilancia.
Se canceló el ensayo parcial 2, se conservó el ensayo 1 completo y se repitieron los
pendientes tras verificar las huellas de los WAV. El controlador pasó a mostrar su
propio progreso. La comparación contiene solo los nueve ensayos terminados; no
mezcla tiempos del intento parcial. Las preparaciones que fallaron antes de cargar
modelos tampoco se incluyen. La versión final además detecta `pythonw.exe` y valida
corpus, ubicación y secuencia antes de reanudar.

Al finalizar, 8765 y 11435 quedaron sin escucha y la instancia habitual de Ollama
conservó PID 23944 y cero modelos cargados. No se reinició el servidor ni se publicó
otro ejecutable. Solo se finalizaron procesos propios del ensayo.

Artefactos locales ignorados por Git:

- `respaldo/gpu_real_20261029_213721/`: WAV y textos ficticios, SHA-256, resultados
  individuales, `resumen.json`, `procedencia.json`, `paquetes.json`, copia de módulos,
  `controlador_ensayo.py` y log del daemon. El controlador capturado permite distinguir
  el ejecutado de las mejoras posteriores en validación de reanudación/inventario.
- `respaldo/respaldo_20261029_213413_antes_de_validacion_gpu/`: documentos anteriores.

El primer ensayo de lote 1 tardó 55,40 s y su primer informe 24,56 s: incluye el mayor
costo inicial de la campaña. Los dos restantes tardaron 36,38 y 36,99 s. No se elimina
ese dato del rango; las medianas reducen su influencia. Se descargan modelos entre
lotes, pero no se vacían la caché de disco de Windows ni las bibliotecas del proceso:
no es una comparación de nueve arranques completamente fríos. Hay solo tres muestras
por tamaño, mismo orden de audios y un escritorio compartido. No permite estimar p95,
garantizar SLA o extrapolar a colas de 20, dictados largos o llegada continua.

Todos los informes tuvieron contenido (97–111 tokens de salida), sin huecos ni
omisiones automáticas detectadas. Eso no sustituye una evaluación de precisión
clínica o de voces humanas. PyAV observado: 19.0.2, distinto de `av<16` declarado
en requirements; estos WAV usan el lector propio. No se reinstalaron dependencias
y la campaña no valida formatos comprimidos ni resuelve esa diferencia del entorno.

## Reproducir y comprobar

Ejecutar desde `sistema/`, solamente cuando ya exista una ventana libre. Si el
controlador rechaza el estado, no detener producción para forzarlo. No abrir otros
procesos Python para consultar el progreso mientras corre; usar su propia salida.

```powershell
.venv/Scripts/python.exe herramientas/validar_gpu_real.py --ejecutar
# Solo si se interrumpió una carpeta sintética y la ventana vuelve a estar libre:
.venv/Scripts/python.exe herramientas/validar_gpu_real.py --ejecutar --reanudar respaldo/gpu_real_FECHA_HORA
# Después de terminar:
.venv/Scripts/python.exe herramientas/resumir_gpu_real.py respaldo/gpu_real_FECHA_HORA/resultados.json --salida respaldo/gpu_real_FECHA_HORA/resumen.json
.venv/Scripts/python.exe -m unittest discover -s pruebas -p test_validacion_gpu.py -v
```

Sin `--ejecutar`, la herramienta solo muestra ayuda. El resumidor rechaza campañas
incompletas, orden incorrecto, agregados inconsistentes y tiempos no finitos. Ocho
pruebas CPU verifican estas condiciones y la vigilancia, incluyendo cancelación
por servidor/LLM ocupados, API inaccesible, Python ajeno, redirectores de Windows,
inventario fallido y corpus alterado. CI descubre esas pruebas automáticamente;
**el benchmark GPU es manual**, fuera de las tareas de integración habituales.

Son herramientas y documentación: no requieren una nueva versión de la aplicación
ni compilación. La distribución local sigue en App 1.21, con la promoción del candidato
1.22 / 2026.10.46 pendiente de coordinación, igual que antes de esta validación.
Sintaxis Python/JS, enlaces locales y `git diff --check` correctos. El verificador completo
del candidato pasa en `respaldo/validacion_gpu_revision/sistema/`, con el ejecutable ya
compilado de la entrega. En la instalación en uso sigue informando la diferencia
intencional entre fuentes 1.22 y ejecutable/manifiesto 1.21; no se corrigió publicando
una actualización durante este ensayo.
