# Sexta etapa: procesamiento de IA y lotes

29/10/2026. Se agrupa en el candidato aún no distribuido **App 1.22 / Servidor 2026.10.46**.
En la implementación inicial no se reinició el servidor, no se cargaron modelos reales
y no se cambiaron preferencias locales. La [validación posterior en GPU real](validacion-gpu.md)
usó únicamente voz sintética y confirma el valor 2/180 para el uso diario.

## Reducir la espera del primer informe

El trabajador anterior esperaba 0,5 s y drenaba toda la cola: primero transcribía cada audio
y recién después generaba informes. Ahora toma los audios disponibles en orden FIFO sin esperar
a que lleguen más, con un máximo predeterminado de **dos audios y 180 s** de duración conocida.
Los demás permanecen en la cola; no se extraen y reinsertan al final. El primer audio siempre se
admite aunque exceda el presupuesto, para evitar que un dictado largo quede sin procesar.
Una duración desconocida consume conservadoramente todo el presupuesto.

Se mantienen dos etapas dentro de cada lote: transcripción/reparación, liberación de Whisper,
generación y controles. No se ejecutan dos modelos o trabajadores GPU en paralelo. Los pedidos
repetidos de un caso ya en proceso no agregan trabajo duplicado; la recuperación de un borrado
fallido conserva su reencolado explícito.

Un error de un audio o informe ya no marca como erróneos todos los compañeros del lote. Se
registra el fallo de ese caso y se continúa con los demás. Un error de infraestructura compartida
todavía puede afectar el lote. Whisper se libera también al salir por un error de lote.

Los límites se configuran con `lote_max_audios` (1–20) y `lote_max_segundos` (1–3600); ausentes
en configuraciones guardadas usan 2 y 180. Valores no numéricos/no finitos usan esos defaults;
otros se acotan al rango y la cantidad se convierte a entero. No se sobrescribe configuracion.json.

Un lote pequeño reduce cuánto ASR debe esperar el primer informe, pero aumenta la frecuencia
de cambios de modelo con cola grande. **No se garantiza mayor throughput**: el equilibrio debe
medirse en la GPU real. Una pausa manual sigue deteniendo al único trabajador; si Ollama no
está disponible, espera su recuperación antes de pasar al lote siguiente. La cola de procesamiento
general se registra ahora en [SQLite con recuperación tras caídas](cola-servidor.md), conservando
FIFO, pausas y la verificación de resultados completos antes de repetir inferencia.

## Evitar trabajo repetido

Por caso se puede conservar `NOMBRE.transcripcion_cache.json` (formato v1), con texto, palabras,
huecos y firma de entrada. La firma incluye SHA-256 de los bytes del audio, modelo/dispositivo,
versiones de faster-whisper/CTranslate2 y hashes de `transcripcion/asr/whisper.py`, `transcripcion/asr/huecos.py` y el vocabulario (hasta el Servidor
2026.11.5, de `fase1_transcribir.py` y `huecos.py`: al actualizar, cada caso vuelve a pasar una vez por Whisper si se regenera).
Un archivo corrupto, formato distinto o firma diferente provoca transcripción nueva. La firma
no incluye parámetros del LLM porque la salida de IA **no se reutiliza**: plantillas, médico,
ejemplos y reglas se vuelven a aplicar al regenerar el informe.

Si todo el lote tiene transcripción válida, no se carga Whisper ni se descarga el modelo de
Ollama para hacer ASR. La caché se publica atómicamente; no poder escribirla no impide generar
el informe. Leer/hashar audio tiene costo de I/O. La caché contiene datos clínicos, permanece
en el directorio del caso y se incluye en su borrado. `reusar_transcripcion: false` evita leerla
o actualizarla; al volver a habilitarla una caché previa válida puede reutilizarse. Para invalidar
manualmente, retirar su archivo en una ventana segura, sin borrar la transcripción de revisión.

La firma no detecta la sustitución manual de los pesos de un modelo bajo el mismo nombre/versiones
ni todos los cambios externos de driver/runtime. En ese caso invalidar/desactivar la caché.
Las versiones iniciales sin caché siguen funcionando y crean la suya al transcribir de nuevo.
El modo simulado no reutiliza ASR para que los fixtures sigan ejercitando ambas etapas.

El banco de ejemplos se reutiliza por firma de directorios/rutas, nombres, tamaños y mtime de
sus archivos relevantes. Cambiar ejemplos o médico invalida la lectura; se devuelve una copia
de cada entrada para que el consumidor no modifique la caché. La detección aún recorre metadatos
y no reconoce cambios externos que preserven exactamente tamaño y fecha. Los perfiles de
categorías/términos de ejemplos se cachean con LRU de hasta 4096 entradas y claves de plantillas
como parte de la identidad. La selección mantiene puntuaciones, exclusiones, orden y cantidad.

## Medir antes de ajustar modelos

`NOMBRE.rendimiento.json` (v1) registra tamaño del lote, tiempo desde el inicio del lote/caso,
tiempo aproximado desde encolado, uso de caché, carga Whisper y etapas ASR/IA. Duraciones del
trabajador y de `llamar_ia` usan reloj monotónico; el tiempo desde encolado usa el registro civil
existente y es aproximado. Incluye las pausas/esperas en los tiempos hasta listo.

Si Ollama los devuelve, se conservan `total_duration`, `load_duration`, `prompt_eval_duration`
y `eval_duration` convertidos de nanosegundos a segundos, más tokens de entrada/salida. No se
registran prompts ni respuestas en estas métricas. El contrato de cuatro valores de `llamar_ia`
permanece compatible; el diccionario de métricas es opcional.

La métrica histórica Whisper conserva su definición anterior: no incluye la primera carga del
modelo y puede incluir procesamiento de metadatos/voz; la carga se informa aparte. La reutilización
de caché no alimenta el factor de velocidad de ASR, ni en vivo ni al releer actividad.csv.
Las métricas nuevas no deben sumarse sin revisar solapamientos entre etapas.

No se reducen ejemplos, contexto (12.288), controles, reparación de huecos ni temperatura (0,1),
ni se cambia Whisper large-v3/Gemma o su cuantización. El ajuste de esos parámetros requiere
un corpus separado de los ejemplos de entrenamiento/selección y comparar números, lateralidad,
omisiones y tiempo humano de revisión además de latencia.

## Pruebas y despliegue

`test_lotes_ia.py` comprueba FIFO, presupuesto, dictados largos/desconocidos, ausencia de espera
por productores, encolado duplicado, invalidación ASR, caché de banco y perfiles de plantillas,
contrato/métricas Ollama, fallos aislados y ejecución del trabajador completo sin modelos reales.
Se verifica que el primer informe está listo antes de transcribir el tercer audio. Una ejecución
fría con ASR simulado crea caché real y el reintento no vuelve a invocar ASR/carga/descarga de modelos.

Estas pruebas demuestran orden y trabajo evitado, no una mejora medida de segundos/tokens por
segundo en producción. La [campaña real posterior](validacion-gpu.md) comparó lotes 1/2/4
con cuatro audios sintéticos, tres repeticiones por tamaño y los modelos locales en RTX 3080.
Quedan pendientes colas de 1/5/20, arranques completamente fríos, duraciones variadas y
llegada continua, siempre fuera del trabajo activo. No se extrapolan esos escenarios.

Respaldo: `respaldo/respaldo_20261029_211903_antes_de_ia_lotes/`.
Ensayo aislado: `respaldo/ia_lotes_pruebas/sistema/`. El nuevo comportamiento Python requiere el
reinicio coordinado pendiente; no se cerraron sesiones ni se ofreció un nuevo ejecutable a las PC.

Validación final: 53 pruebas Python y cuatro pruebas de navegador aprobadas. Sintaxis Python/JS,
JSON de ejemplo, enlaces y `git diff --check` correctos. La verificación completa del candidato
y manifiesto pasa en staging con el ejecutable ya compilado de la entrega agrupada
(`respaldo/compilacion_20261029_210622_502/Transcripcion.exe`). Esta etapa no cambia C# ni JS;
no se recompiló ni distribuyó otra app. En la instalación en uso el verificador sigue señalando
la diferencia intencional entre fuentes 1.22 y distribución 1.21. No equivale a una release activada.
