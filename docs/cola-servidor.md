# Cola persistente de procesamiento del servidor

29/10/2026. Parte de la entrega aún no promovida **App 1.22 / Servidor 2026.10.46**.
Esta etapa cambia Python; no cambia C#, modelos, límites de lote ni preferencias locales.
No se reinició el servidor en uso ni se activó la migración sobre sus datos durante el desarrollo.

## Confirmación y recuperación

El servidor registra una tarea SQLite antes de anunciar «En cola» o confirmar la subida.
La cola en memoria sirve al trabajador único; SQLite conserva la intención de procesar, el
orden, el instante original de encolado, un identificador de ejecución y la pausa solicitada.
Una solicitud repetida de un caso activo no crea otra tarea. Un reintento explícito de un
caso terminado o con error crea una nueva ejecución y vuelve al final de la cola.

La base es `Informes/revision/cola_procesamiento.sqlite3`, relativa a la carpeta de informes
configurada. Usa transacciones SQLite, `synchronous=FULL`, versión de formato 1 e índices
por nombre y estado/orden. No contiene audios, prompts ni textos de informes; los nombres
de tareas también son datos sensibles. Los registros terminales se conservan, incluso al
cancelar/borrar: no representan trabajo que deba volver a ejecutarse. No hay purga automática.
Cada caso tiene una fila; las consultas normales no recorren el historial completo de tareas.
Al arrancar se comprueba la integridad de la base; ese chequeo sí depende de su tamaño.

El archivo `.sqlite3.lock` utiliza un lock del sistema operativo, sin espera, para impedir que
dos procesos de esta implementación recuperen la misma cola. El archivo queda en disco;
el lock se libera al terminar el proceso, incluso abruptamente. No borrarlo por parecer antiguo.
Usar almacenamiento local con garantías de SQLite (NTFS/ext4), no carpetas sincronizadas ni
dos servidores sobre una carpeta compartida. Versiones antiguas no conocen este lock.

El arranque reserva primero el puerto y recupera la cola **antes** de iniciar trabajadores,
vigilancia, voz o atención HTTP. Una base corrupta, incompatible, bloqueada por otro propietario
o inaccesible impide iniciar procesamiento; no se reemplaza por una vacía. Durante el trabajo,
un fallo de confirmación de la cola conserva las tareas, libera Whisper y reintenta después
de 5 s. La API devuelve 503 cuando no puede confirmar una operación duradera.

| Situación tras una caída | Comportamiento al volver |
|---|---|
| En cola, transcribiendo o generando | Recupera el orden original y vuelve a procesar; usa la caché ASR si sigue siendo válida |
| Pausa solicitada o efectiva | Conserva la pausa; **Reanudar** la confirma en disco antes de despertar el trabajador |
| Audio desaparecido | Conserva el registro y muestra error en la lista; restaurar el original y usar **Procesar** |
| Error de procesamiento ya registrado | Permanece con error para reintento manual; no entra en un ciclo de fallos tras cada arranque |
| Resultado completo confirmado por archivos, pero faltó confirmar SQLite | Comprueba el resultado y marca listo sin ejecutar otra vez Whisper/IA |
| Borrador, formato manual, texto final o Word y recuperación dudosa | Conserva la revisión y detiene ese caso con error; requiere revisión/reintento explícito |
| Borrado en curso al caer | Conserva la intención de borrado y no vuelve a procesar el caso automáticamente |
| Terminado o cancelado | No lo vuelve a encolar |

Las pausas se comprueban antes de cargar modelos y entre etapas. Una pausa durante una
transcripción interrumpida conserva la decisión de pausar; no serializa el estado interno de
Whisper ni promete continuar desde el mismo milisegundo. Un audio en cabeza pausado puede
seguir deteniendo los siguientes, igual que en el flujo anterior.

## Comprobante de resultado completo

Transcripción JSON, dictado, informe y marcas se publican por temporal, fsync y reemplazo.
Al terminar se escribe atómicamente `NOMBRE.procesamiento.json` (v1), con el identificador
de la ejecución, firma del audio (ruta, tamaño y mtime_ns) y SHA-256 de esos cuatro archivos.
Después se confirma «listo» en SQLite y se actualiza el estado visible.

Una caída antes de ese comprobante obliga a repetir la tarea incompleta. Una caída después
permite reconocer el resultado completo sin regenerar ni eliminar revisiones posteriores.
Una nueva solicitud de procesamiento cambia el identificador: un comprobante anterior no
puede confirmar el nuevo trabajo. Si se pierde una respuesta de commit local, el trabajador
reconcilia el estado terminal sin repetir la generación.

No hay una transacción única entre SQLite y todos los archivos ni garantía de inferencia
exactamente una vez: una caída puede repetir cómputo incompleto. No se sobrescribe una revisión
humana automáticamente para resolver una inconsistencia. La firma del audio detecta cambios
normales; no identifica una modificación externa que preserve exactamente tamaño y fecha.
No editar ni sustituir manualmente el audio mientras está procesándose.

## Compatibilidad y adopción de audios

`cola_al_reiniciar.json` se importa una sola vez dentro de una transacción y se conserva como
evidencia. Un formato inválido no se borra ni se importa parcialmente. Los registros ya existentes
en SQLite tienen prioridad. Los reinicios nuevos dependen de la cola duradera, no de reescribir
ese archivo antiguo al apagar.

La primera migración no puede reconstruir estados que la versión anterior nunca guardó:
su instantánea no contiene las pausas. Antes de activar, revisar/anotar las pausas existentes
y los informes incompletos de la instalación anterior en una ventana coordinada. Los archivos
con informe previo no se adoptan por mera presencia de audio, aunque ese informe antiguo pueda
haber quedado incompleto. No se promete recuperar retroactivamente una cola que nunca fue persistida.

En cada arranque se buscan audios publicados sin registro, ordenados por fecha del archivo y
nombre. Se adoptan solo si no tienen informe, borrador, formato, final o Word y no existe un
registro previo. Esto cubre la caída entre publicar el audio y registrar la tarea, y la migración
desde instalaciones anteriores. El orden de un audio sin registro solo puede aproximarse por
sus metadatos; el orden de tareas ya registradas se conserva exactamente.

Las subidas locales y remotas publican metadatos antes del audio completo y registran luego la
tarea. Ante un fallo la app conserva/reintenta su copia; puede haber archivos huérfanos sin
confirmación. Un caso cancelado o con error no se reactiva por ese barrido. Las tareas recuperadas
siguen usando el único trabajador y los límites de lote existentes, con fallos aislados por caso.

Un borrado registra su intención antes de apartar archivos. Si falla por permisos, restituye
el estado anterior y su pausa. Si cae a mitad del borrado, conservar los `.borrando`, el resto
del caso y la base: no se restauran ni se eliminan automáticamente esos archivos apartados.
Revisar/completar el borrado en una ventana segura antes de volver a procesar. Se conserva el
registro de cancelación para impedir que restos del caso se interpreten como un audio nuevo.
Si ya no queda ningún archivo, **Borrar** permite cancelar explícitamente el registro residual
o de audio desaparecido. Si quedan archivos `.borrando`, exige revisar esos restos y los conserva.

## Respaldar sin detener el servidor

El respaldo SQLite usa su API de backup, abre el origen solo para lectura, verifica integridad
y publica el destino completo sin sobrescribir otro archivo. No toma el lock de propietario
del trabajador, ni inicia modelos o servidor. Puede compartir brevemente I/O/locks de SQLite
con las escrituras; no es una copia manual del archivo mientras cambia.

Desde `sistema/`, con una carpeta de destino existente y un nombre nuevo:

```powershell
.venv/Scripts/python.exe mantenimiento_cola.py --base Informes/revision/cola_procesamiento.sqlite3 --respaldar respaldo/cola_procesamiento.sqlite3-copia-20261029
```

El temporal y destino deben estar en un volumen que permita enlaces físicos (NTFS/ext4);
si falla su publicación no se anuncia éxito. El origen no se crea si falta. El comando no
muestra nombres de tareas. Proteger el respaldo con los mismos permisos que los datos.

La base sola no recupera los bytes de los audios: respaldar también audios, datos de revisión
y documentos. Una instantánea de SQLite no es una instantánea transaccional de todas esas
carpetas. Para una restauración completa, coordinar una ventana sin escrituras, conservar el
estado actual y verificar una copia conjunta antes de promoverla. No restaurar una base vieja
sobre trabajo reciente. No eliminar el journal de SQLite para forzar el arranque.

Para volver a una versión sin esta cola, detener escrituras en una ventana coordinada,
conservar base y archivos, obtener la lista de pendientes en una copia validada y reencolarlos
con el mecanismo de esa versión. Esa versión no lee SQLite ni conserva automáticamente las
pausas nuevas. No se ejecutó ninguna restauración o rollback sobre la instalación en uso.

## Pruebas y estado de entrega

`pruebas/test_cola_procesamiento.py` cubre FIFO, solicitudes concurrentes, rollback de commit,
confirmación local perdida, migración única, base corrupta/desconocida, propietario exclusivo,
borrados, pausas, audio faltante, conservación de revisión y consultas indexadas con 1.000 tareas
terminadas. Comprueba además respaldo por CLI con propietario activo y bloqueo del arranque
sin iniciar hilos cuando no puede recuperar la cola.

Se terminaron procesos **propios de ensayo** con `os._exit` en cola, transcripción, generación,
transacción sin commit y justo antes de confirmar «listo». Se volvió a abrir SQLite y se ejecutó
el trabajador completo en modo simulado; el informe terminado y su revisión se conservaron.
Son pruebas de caída de proceso, no cortes de energía del equipo ni ensayos con pacientes/GPU.
La durabilidad física depende también del sistema de archivos, controlador y hardware.

Respaldo de fuentes/documentos previo:
`respaldo/respaldo_20261029_221606_antes_de_cola_servidor/`.
Ensayo aislado: `respaldo/cola_servidor_pruebas/sistema/`.
Las pruebas entran en CI por descubrimiento, sin dependencias nuevas.

Validación final: **97 pruebas Python aprobadas**, más regresión del panel de médicos en
navegador contra HTTP ficticio. Sintaxis Python/JS, enlaces y `git diff --check` verificados.
El candidato completo pasa el verificador de fuentes, ejecutable y manifiesto en la copia
de ensayo, usando el binario App 1.22 ya compilado y autoverificado:
`respaldo/compilacion_20261029_220859_948/Transcripcion.exe`. No se recompiló C# en esta etapa.
La instalación mantiene App 1.21: su verificador señala la diferencia intencional respecto de
fuentes 1.22 / Servidor 2026.10.46. No es una distribución promovida.

La nueva base solo se abre al iniciar el servidor actualizado. No se importaron pendientes
reales, no se cargó GPU y no se reinició ningún servicio durante esta implementación.
La activación sigue pendiente de una ventana coordinada; no hay migración en caliente.
