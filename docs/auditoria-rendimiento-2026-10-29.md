# Auditoría de rendimiento y fiabilidad — 29/10/2026

Base revisada: commit `48afe40`, servidor **2026.10.45**, app **1.21**. Árbol Git inicialmente limpio.

Seguimiento: se preparó el candidato App 1.22 / Servidor 2026.10.46 para la primera etapa de
borradores y cola de audios. Ver [implementación, pruebas y promoción pendiente](persistencia.md).
Los hallazgos siguientes describen la base auditada, no el estado del candidato posterior.
Esta entrega agrega documentación y un microbenchmark; las mejoras de producción descritas abajo
son propuestas, no cambios ya implementados. El plan de entrega está en [ci-cd.md](ci-cd.md).

## Conclusión

Las primeras inversiones deben ser la persistencia confiable, el listado incremental y la edición
incremental. Hay trabajo repetido comprobable en disco, HTTP y DOM. La GPU es un recurso limitado,
pero no explica por sí sola una interfaz lenta: consultar casos, escribir y guardar tienen caminos
independientes que se pueden mejorar sin cambiar modelos ni reducir controles del informe.

No se justifica todavía una reescritura completa, microservicios o una migración de framework.
Conviene conservar la aplicación y sustituir los caminos costosos con pruebas de regresión.

## Alcance y límites

Se inspeccionaron las rutas HTTP, trabajador, persistencia, aprendizaje, selección de ejemplos,
estadísticas, voz, interfaz y editor A4, cola/actualizador C#, compilación, dependencias y pruebas.
Las referencias usan archivo y función para que sigan siendo útiles si cambian las líneas.
No es una auditoría exhaustiva de seguridad ni una certificación de ausencia de defectos.

No se leyeron contenidos de informes, audios, configuración ni registros clínicos reales.
No se reinició el servidor ni se reemplazó el ejecutable. No se ejercitó Whisper/Ollama ni se midió
la red del trabajo, la GPU o el rendimiento real de WebView2 en las PC remotas. Los resultados
de disco son de este equipo con datos sintéticos; no son percentiles de producción.

## Medición reproducible

Desde `sistema/`, usando su entorno:

```powershell
.venv/Scripts/python.exe pruebas/medir_listado.py --casos 100 1000 --repeticiones 5
```

El script copia fuentes y conocimiento de ejemplo a un directorio temporal bajo `respaldo/`,
crea una configuración aislada y casos ficticios, importa el servidor allí y llama a
`listar_casos`. No inicia un servidor HTTP ni modelos. Borra solamente su propio temporal.
Cada caso tiene informe, borrador y metadatos mínimos; no tiene WAV ni huella de voz.
La primera llamada calienta cachés de aplicación; no equivale a un arranque con caché del SO vacía.
Los casos con muchos avisos, audio real o más metadatos pueden tener otro costo.

| Casos | Primera llamada | Mediana de 5 posteriores | Máximo posterior | JSON de la lista |
|---:|---:|---:|---:|---:|
| 100 | 850,9 ms | 108,9 ms | 116,3 ms | 49.376 bytes |
| 1.000 | 7.222,6 ms | 1.151,1 ms | 1.419,8 ms | 493.698 bytes |

El crecimiento observado es aproximadamente proporcional al número de casos. El benchmark no
incluye serialización en el tiempo medido, HTTP, TLS, túnel, DOM ni usuarios simultáneos.
El tamaño JSON se calcula por separado. Cinco muestras no permiten afirmar un p95 estable.

`/api/cliente/estado` ejecuta `listar_casos` **dos veces**, aunque solo devuelve hasta 40 casos
de esa PC. Una extrapolación orientativa del resultado caliente de 1.000 casos sería unos 2,3 s
solo en esos recorridos; no es una medición de ese endpoint. La web consulta cada 2 s y la app
aproximadamente cada 10 s. Con C PC abiertas son aproximadamente `0,7 × C` recorridos completos
por segundo: 0,5 de la web más 0,2 del escritorio. No implica uso de CPU equivalente, porque hay I/O.

## Hallazgos priorizados

P1: siguiente entrega; P2: después de establecer la línea base y resolver P1.
«Comprobado» significa observado en código o medición, no necesariamente un incidente ocurrido.

| ID | Prioridad | Evidencia y efecto | Cambio propuesto y aceptación |
|---|---|---|---|
| R01 | P1 | `servidor.py:listar_casos` recorre directorios, consulta múltiples archivos por caso, lee marcas y borradores; el filtrado ocurre después. Escalado medido arriba. | Índice de resúmenes actualizado al mutar casos; separar estado volátil de metadatos; filtros y paginación en servidor. Verificar invalidación al guardar, borrar, regenerar, cambiar médico y editar paciente. Conservar compatibilidad con clientes anteriores. |
| R02 | P1 | `H.do_GET`, `/api/cliente/estado`: dos listados completos para resumen y conteo. | Obtener una instantánea por pedido como primera mejora pequeña. Luego endpoint de estado económico con contador y revisión de cambios; probar igualdad de permisos y resultados. |
| R03 | P1 | `web/index.html:cargarLista`, `setInterval(..., 2000)`: sin exclusión de solicitudes ni cancelación explícita; vacía `#casos` y recrea filas. | Un pedido activo, próxima consulta al terminar, timeout y descarte de respuestas obsoletas; pausa/adaptación por visibilidad, con renovación de bloqueo independiente. Actualizar filas por nombre y campos cambiados; preservar foco, scroll y selección. |
| R04 | P1 | `web/editor_word.js:cambiarFormato`, `ponerModelo`, `paginar`: copia/serializa documento y repagina todo al editar; alterna inserciones con lecturas `scrollHeight/clientHeight`. `sincronizarInforme` busca cada párrafo en toda la lista anterior. | Invalidar desde el párrafo modificado y detener repaginación cuando se estabiliza; índice de párrafos e historial de operaciones. Probar pegado Word, selección entre hojas, marcas, undo y exportación antes/después. Perfil de 1, 10 y 30 páginas. |
| R05 | P1 | `index.html:guardarBorrador` usa `.catch(()=>{})`; `cerrarCaso` puede continuar y anunciar guardado si ese envío falló y no había formato pendiente que bloqueara el cierre. | Estado explícito guardando/guardado/error, reintento y retención de cambios. Guardado versionado por caso para evitar que un pedido viejo pise uno nuevo. `guardarFormato` ya serializa y reporta errores: conservar esa protección. Probar pérdida de conexión, navegación rápida y respuestas fuera de orden. |
| R06 | P1 | `Audios.cs:Revisar` persiste huella antes de `AudioListo`; el receptor captura errores de `cola.Agregar` y aun muestra aviso de audio tomado. | Confirmar la huella después de persistir cola; comunicar error y reintentar si falla. Simular disco lleno y denegación de escritura. No declarar entregado un audio que no tiene copia recuperable. |
| R07 | P1 | `ColaEnvio.Agregar` escribe `.audio` directamente y luego `.nombre`; el lector puede encontrar un parcial y `Bucle` elimina pendientes ilegibles. | Escribir temporal, cerrar y publicar por renombrado; metadatos coherentes, cuarentena de archivos dañados y recuperación al iniciar. Probar escritura concurrente y terminación entre pasos; ningún pendiente debe desaparecer silenciosamente. |
| R08 | P1 | `_finalizar` bajo `FIN_LOCK` hace Word, ejemplo, historial y análisis global de correcciones. `registrar_ejemplo` reescribe historial y `analizar_correcciones` recorre ejemplos con `SequenceMatcher`. | Confirmar primero guardado duradero de documento y evento de aprendizaje; recalcular aprendizaje incrementalmente en trabajador posterior, con reintentos idempotentes. No sacar el lock sin sustituir sus garantías. Medir guardado con 100/1.000/10.000 ejemplos y dos PC. |
| R09 | P1 | `trabajador` espera 0,5 s y drena la cola completa: transcribe todo el lote antes de generar informes. El bloque de excepciones exterior puede marcar varios pendientes como error por un fallo de un caso. | Lotes con límite por cantidad/duración/antigüedad; aislamiento de errores por caso y recuperación por etapa. Comparar latencia del primer resultado y rendimiento total; no pasar automáticamente a un cambio de modelos por audio. |
| R10 | P1 | `COLA` es `queue.Queue()` sin límite ni persistencia transaccional. `cola_al_reiniciar.json` conserva pendientes en reinicio coordinado, no es un diario duradero de cada recepción. | Persistir trabajo y estado antes de confirmar recepción; reconstruir pendientes tras caída; límites de admisión y respuesta reintentable. Reinicio forzado con audios ficticios: sin pérdidas ni duplicados y sin repetir etapas ya confirmadas. |
| R11 | P2 | `H._body` admite hasta 100 MiB y conserva cuerpos completos; en chunked acumula bloques y luego los une. Servidor por hilo, sin límite explícito de conexiones/lectura en esa clase. | Límites por endpoint y tiempo, número acotado de subidas, escritura por bloques a temporal con hash incremental. Validar longitudes negativas/incompletas y liberar recursos ante corte. Medir memoria con subidas simultáneas. |
| R12 | P2 | `_enviar_archivo` ya envía bloques de 64 KiB y admite Range, pero no rechaza correctamente todos los rangos fuera de archivo. | Probar y responder 416 en rangos no satisfacibles, archivos vacíos y rangos malformados. Conservar streaming; no reemplazarlo por lectura completa en memoria. |
| R13 | P2 | `dibujarOnda` redibuja onda y busca marcadores DOM en cada frame mientras reproduce. `bufferScrub` descarga y decodifica audio completo. | Separar capa estática de onda/marcas y cabezal; invalidar por cambio, cachear colores y coordenadas; límites para scrub de audios largos y liberar buffers. Medir CPU/memoria y frames perdidos. |
| R14 | P2 | `N.cargar_banco` lee ejemplos por lote; `elegir_referencias` recorre referencias por informe; se releen plantillas/reglas. | Caché por revisión de contenido e invalidación en edición/importación/guardado; índice de términos para selección. Medir costo antes de adoptar embeddings o una base vectorial. |
| R15 | P2 | `_guardar_audio_nuevo` consulta duplicado, escribe y registra en pasos separados; `remoto.guardar_huella` bloquea la escritura JSON, pero la operación total no es atómica. | Restricción única por hash y transacción de recepción; provisionalmente lock acotado para reserva de hash y nombres más publicación atómica. Dos envíos simultáneos del mismo WAV deben producir un único caso. |
| R16 | P2 | Estadísticas cacheadas, pero reconstruyen desde CSV ante invalidación/cambio; historial y registro de ejemplos crecen. Varias escrituras de casos son `write_text` directas. | Primero medición e índices/resúmenes; luego SQLite local para metadatos y trabajos si se confirma necesidad. WAL/transacciones, esquema versionado y migración reversible; audio/Word permanecen en archivos. No ubicar una base WAL sobre recurso de red. |
| R17 | P2 | `Vigilante.Iniciar` barre `%TEMP%` recursivamente y se llama desde `HandleCreated`; captura/subidas usan arrays completos. | Mover barrido inicial fuera del hilo UI, mantener recuperación del watcher, acotar raíces si se conoce el origen. Medir memoria con WAV largos; DPAPI requiere planificación específica, no quitar cifrado para acelerar. |
| R18 | P2 | Manifiesto usa caché de 5 s y solo rehash si cambia firma; un cambio rehasha todo el conjunto bajo lock. Distribución de varios archivos no es una transacción única. | Mantener caché existente; hash incremental solo si se mide costo significativo. Publicar candidato completo y validado antes de exponer nueva revisión; descargar/verificar un conjunto consistente y conservar rollback. |
| R19 | P1 | No hay workflows CI versionados, lock de Python ni manifiesto de dependencias de pruebas JS; `requirements.txt` permite múltiples versiones. | Incorporar las puertas del plan CI/CD, locks por plataforma y entorno de pruebas reproducible. Verificar configuración remota de ramas por separado: esta auditoría solo confirma lo presente en el checkout. |

## IA: cómo optimizar sin empeorar informes

El trabajador ya agrupa audios para amortizar la carga de Whisper y Gemma. La documentación
anterior describía «un audio por vez», pero la implementación es un trabajador por **lote de dos
etapas**. No iniciar varios workers GPU con el esquema actual: podrían descargar el modelo que
otro necesita o agotar VRAM. Conservar un propietario de GPU y colas diferenciadas por etapa.

`nucleo.llamar_ia` usa contexto 12.288, `stream:false`, `keep_alive:15m`, y devuelve tiempo total
y cantidades de tokens. Faltan métricas separadas de carga, evaluación del prompt y generación.
Ollama expone `load_duration`, `prompt_eval_duration` y `eval_duration` en nanosegundos:
[documentación oficial](https://docs.ollama.com/api/usage). Registrar su disponibilidad por versión.
La medición actual de Whisper reinicia el reloj después de cargar el modelo, por lo que no es
una medida completa de espera del usuario. La duración de IA incluye además trabajo posterior.

Instrumentar: recepción → espera de cola → carga Whisper → ASR → reparación → voz → cambio
de modelo → selección/prompt → carga LLM → tokens → controles → listo. Usar reloj monotónico
para duraciones y mantener fecha civil por separado. Identificar ejecuciones con ID opaco;
no agregar nombres, dictados, prompts ni respuestas a métricas o artefactos de CI.

Ensayar contexto ajustado al presupuesto real, menos ejemplos redundantes, cuantización,
Whisper alternativo o CPU solo con corpus de evaluación separado de ejemplos aprendidos.
Comparar números, lateralidad, omisiones, correcciones y tiempo total de revisión. Una mejora
de tokens/s que aumenta errores o minutos de corrección no es una mejora del sistema.
El streaming puede mostrar progreso, pero un informe parcial no debe parecer validado.

## Lo que conviene conservar

- Separación entre HTTP y trabajador GPU; procesamiento de IA local.
- Detección de duplicados por hash, cola local cifrada y reintentos.
- Cachés existentes de duración, estudios, voz, estadísticas y manifiesto: extender, no ignorar.
- Búsqueda binaria de la palabra del audio en `timeupdate` y agrupación de `selectionchange` con RAF.
- Debounce del borrador/formato, bloqueo de casos, serialización de formato y finalización.
- Streaming de descargas, autoprueba .NET y reemplazo del ejecutable con recuperación.
- Pruebas de Word y UI ficticias ya existentes: son una base aprovechable.

## Objetivos propuestos y experimentos pendientes

Estos presupuestos son criterios iniciales a acordar con el equipo, no capacidades ya alcanzadas.

| Área | Objetivo inicial | Cómo comprobar |
|---|---|---|
| Resumen de casos | p95 < 200 ms en servidor con 1.000 casos y 10 clientes, tras calentamiento | HTTP aislado, al menos 100 muestras por escenario; separar serialización/red |
| Lista remota | Cambio visible < 3 s con conexión saludable | Medir evento servidor → fila actualizada; conservar alertas de desconexión |
| Escritura | Respuesta habitual < 50 ms y ninguna tarea de edición > 100 ms en PC objetivo | Perfil navegador con audio y documentos de 1/10/30 páginas |
| Word | p95 < 1 s sin aprendizaje global en el camino crítico | Documento ficticio representativo, dos guardados simultáneos |
| Persistencia | Cero pérdidas silenciosas ante fallos ensayados | Corte de red, disco lleno, proceso terminado y respuestas reordenadas |
| IA | Mejorar tiempo hasta primer informe y p95 por duración sin degradar calidad | GPU real, carga fría/caliente, 1/5/20 pendientes, evaluación separada |
| Memoria | Sin crecimiento sostenido al abrir/cerrar 100 casos | Medir heap WebView2, proceso C#, RAM Python y VRAM por separado |

Añadir escenarios de 100/1.000/10.000 casos y 1/5/10 clientes, internet interrumpido y RTT
simulada de 50/150/300 ms. Primero correr fuera de producción. No usar un umbral absoluto
estricto en runners compartidos; comparar línea base en hardware estable y tendencias.

## Orden de implementación

1. Corregir confirmación duradera de cola y borradores (R05–R07); pruebas de fallos antes del cambio.
2. Instalar CI reproducible y métricas; eliminar doble listado y solapamiento HTTP (R01–R03, R19).
3. Reducir repaginación y refresco de audio (R04, R13); verificar en WebView2 del trabajo.
4. Guardado rápido, cola persistente y lotes acotados (R08–R10, R15).
5. Ajustar IA con evidencia; evolucionar HTTP/almacenamiento y cachés según el perfil (R11–R18).

Para HTTP remoto, planificar una capa de servidor de producción con límites, apagado ordenado
y observabilidad. Python advierte que `http.server` no está recomendado para producción:
[referencia oficial](https://docs.python.org/3.13/library/http.server.html).
Migrar requiere adaptar handlers y probar autorización, cookies, Range y clientes antiguos;
no se resuelve simplemente envolviendo esta clase en un servidor WSGI/ASGI.

## Comprobaciones de esta entrega

- 11 pruebas `unittest`: aprobadas en copia de archivos versionados, sin datos reales.
- Tres scripts Playwright aprobados con Edge: editor Word (11 hojas), revisión/audio y médicos.
- Primera ejecución HTTP/navegador bloqueada por sandbox; repetición autorizada fuera de él aprobada.
- La prueba de médicos necesitó `PYTHON` apuntando al entorno existente; no se copió `.venv`.
- `verificar_versiones.py`: app 1.21, servidor 2026.10.45, ejecutable y manifiesto coherentes.
- Microbenchmark: resultados de la tabla; no demuestra rendimiento de GPU ni de producción.
- No se compiló ni distribuyó una app nueva: no se cambió comportamiento de producción.

El estado del ejecutable local no demuestra qué versión está ejecutando cada PC remota.
Las optimizaciones quedan pendientes de implementación; la configuración real de GitHub,
el despliegue automático y los benchmarks GPU no fueron activados por esta auditoría.
