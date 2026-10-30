# Cuarta etapa: Word y aprendizaje en segundo plano

29/10/2026. Se agrupa en el candidato aún no distribuido **App 1.22 / Servidor 2026.10.46**.
No se ejecutó aprendizaje sobre informes reales ni se reinició el proceso en uso.

## Camino de guardado

El pedido valida/lee el caso, calcula el porcentaje de palabras corregidas de ese informe y
genera el DOCX completo en memoria. `persistencia.escribir_atomico` escribe un temporal del
mismo directorio, hace flush/fsync y reemplaza el archivo de destino. Si el Word anterior está
abierto y Windows impide reemplazarlo, se conserva y el pedido devuelve error.

Se publican la clave estable de ejemplo y el texto final, luego se conserva la tarea de
aprendizaje en `Informes/revision/datos/_aprendizaje/NOMBRE.json`. La respuesta exitosa exige
que esa tarea haya quedado publicada en disco. El contrato anterior conserva `docx` y `pct`;
se agrega `aprendizaje: "pendiente"`. La interfaz informa que el aprendizaje sigue en segundo
plano; los clientes anteriores siguen pudiendo leer la respuesta.

Se mantiene `FIN_LOCK` para las publicaciones de guardado y su coordinación con reinicios.
No se ejecutan bajo ese bloqueo el recorrido del corpus, la reescritura del historial ni el
registro de voz. No hay garantía de latencia constante: generación del DOCX, fsync, cálculo de
porcentaje y almacenamiento de la tarea siguen en el pedido. El bloqueo global breve todavía
serializa dos guardados Word; no se sustituyó por bloqueos por caso en esta etapa.

## Aprendizaje recuperable

Al iniciar el servidor nuevo se inicia un único consumidor. La tarea conserva dictado, salida
de IA, texto final, médico, clave, fecha de guardado y versión del Word. Es información clínica:
permanece en el directorio de datos, no en Git, logs, artefactos de CI ni servicios externos.

El consumidor aplica ejemplos/historial y el registro de Word procesado. La actualización de
voz solo se intenta si la versión final y el médico siguen correspondiendo; un fallo opcional
de voz se registra sin impedir el aprendizaje textual. Si el DOCX se guardó nuevamente, la
versión anterior no se marca como el Word nuevo procesado.

Cada caso conserva como pendiente su última versión. Si se vuelve a guardar mientras se está
aprendiendo una anterior, la confirmación de esa tarea anterior no elimina la nueva. Puede
existir un intervalo en que los ejemplos reflejen la versión previa; el consumidor aplica luego
la pendiente. El historial usa clave y fecha originales para que los reintentos no dupliquen
la fila del mismo caso/día, incluso si el procesamiento cruza medianoche.

Antes de retirar una tarea completada se publica `_recalcular`. El análisis global se agrupa
una vez por pasada; si falla o el servidor se detiene, el marcador conserva la necesidad de
recalcular. Las tareas fallidas se mantienen y se reintentan cada 30 s o al llegar trabajo nuevo.
La cola conserva datos en disco y no requiere terminar todos los trabajos para apagar el proceso.

Ejemplos, historial, registro de procesados y correcciones se publican individualmente por
reemplazo atómico. Se mantienen los formatos existentes; el modo consola conserva el análisis
síncrono por defecto. No ejecutar procesos de aprendizaje por consola concurrentes sobre los
mismos datos: no se incorporó un bloqueo entre procesos.

## Límites y recuperación

El conjunto DOCX + texto final + tarea **no es una transacción única**: un fallo posterior a
publicar Word puede dejar el documento nuevo aunque la API devuelva error. En ese caso conservar
el estudio y reintentar; no interpretar el error como ausencia del archivo. Un cierre abrupto
antes de publicar la tarea puede requerir reintentar ese guardado no confirmado. Toda respuesta
exitosa sí tiene tarea duradera; una pérdida de respuesta puede causar repetición idempotente.

Las tareas son instantáneas de versiones guardadas: borrar luego el caso no borra su aprendizaje
pendiente, de la misma forma que borrar casos ya revisados conserva los ejemplos aprendidos.
No limpiar `_aprendizaje` ni `_recalcular` automáticamente. Una tarea corrupta o de versión
desconocida se conserva y se registra para revisión; no se descarta silenciosamente.

La etapa siguiente sustituye el recálculo global habitual y las reescrituras CSV por
[correcciones e historial indexados](aprendizaje-incremental.md). Solo la migración inicial
y la reconciliación explícita recorren el corpus. Las lecturas completas del panel aún tienen
un costo proporcional a los datos solicitados.
La UI no muestra todavía un indicador por caso de aprendizaje completado o fallido: los errores
se registran en el servidor. No equivale a entrenamiento de pesos del modelo.

Para volver a un servidor anterior, primero resolver las tareas con este consumidor en una
ventana coordinada o conservarlas para procesar más adelante; el servidor anterior no las lee.
No restaurar datos viejos sobre Word o correcciones recientes. Respaldar el directorio completo
de datos y los ejemplos antes de cualquier recuperación.

## Verificación y entrega

Pruebas ficticias de recuperación al recrear consumidor, fallo/reintento, versiones simultáneas,
historial idempotente, DOCX exportable y fallo de publicación que conserva el Word anterior.
También se prueba guardar una nueva versión mientras el consumidor está detenido dentro de
una tarea lenta: el guardado retorna sin esperar que se libere ese trabajador. No se usa un
umbral de tiempos dependiente del equipo para afirmar esa separación.

Respaldo previo: `respaldo/respaldo_20261029_210238_antes_de_word_aprendizaje/`.
Ensayo: `respaldo/word_aprendizaje_pruebas/sistema/`. La entrega se compila como candidato
con `-SoloCompilar`; no se ofrece todavía a los actualizadores en uso. Las páginas abiertas
conservan su código cargado. Las garantías nuevas del servidor requieren el reinicio coordinado
pendiente. No se afirma que los procesos ni las PC remotas estén actualizados.

Resultado: 29 pruebas Python y cuatro pruebas de navegador aprobadas. Candidato:
`respaldo/compilacion_20261029_210622_502/Transcripcion.exe`, autoprueba de 390 métodos OK.
La verificación completa de fuentes, ejecutable y manifiesto pasa en staging. En la instalación
en uso detecta la diferencia intencional entre fuentes 1.22 y ejecutable distribuido 1.21;
no se ha promovido la nueva distribución. Se conservan dos advertencias CS4014 previas.
