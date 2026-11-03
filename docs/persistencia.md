# Borradores y cola de audios — primera etapa de la auditoría

Candidato: **App 1.22 / Servidor 2026.10.46**, 29/10/2026.
Este documento cubre R05–R07, el cierre del actualizador y la revisión posterior de
confirmaciones. Las otras etapas de rendimiento se documentan por separado.

## Qué cambia para las personas

La revisión muestra «Cambios sin guardar», «Guardando…», confirmación o error con un botón de
reintento. Los errores transitorios se reintentan a los 10 s cuando el pedido devuelve un fallo.
Un pedido aún sin respuesta continúa pendiente; no se presenta como guardado.
Cerrar estudio o cambiar a otro caso requiere confirmación del guardado. Si llega otra edición
mientras se espera, se conserva el caso abierto. Un conflicto con otra sesión exige conservar
el texto local y resolverlo antes de volver a abrir: no se fuerza el sobrescrito automáticamente.

Si el panel libera un caso con cambios pendientes, se mantiene su contenido en pantalla para
recuperarlo. El servidor sigue rechazando escrituras de quien perdió el permiso.
Antes de cerrar/recargar la página se solicita confirmación si hay cambios sin guardar; se quitó
el beacon de borrador porque no garantizaba orden ni confirmación. El aviso del navegador no
garantiza recuperación frente a un cierre forzado del proceso, apagado o fallo del equipo.
No se guardan informes clínicos en localStorage para resolver ese problema.

La app 1.22 requiere cerrar el estudio antes de **Salir** o instalar una actualización. Cerrar
la ventana normalmente sigue ocultándola, conservando la sesión. Una ventana minimizada con
un estudio abierto ya no se considera segura para actualizar. Si no puede comprobar el estado
de WebView2, pospone la actualización. No utiliza una espera fija como prueba de guardado.

## Formato y compatibilidad de borradores

`transcripcion/casos/borradores.py` guarda un archivo `NOMBRE.borrador.json` con:

```json
{"v": 1, "html": "<div>Texto ficticio</div>", "omisiones_ok": [], "revision": 1}
```

Se escribe un temporal en el mismo directorio, se hace flush + fsync y se publica por
`os.replace`. HTML y omisiones corresponden a una misma escritura. Un fallo previo al replace
conserva el borrador anterior. La durabilidad última ante pérdida de energía depende también
del sistema de archivos y hardware; no sustituye un respaldo.

Si todavía no existe el JSON, se leen `.borrador.html` y `.omisiones_ok.json` anteriores. No hay
migración masiva al iniciar: el primer guardado produce el JSON y conserva los archivos antiguos.
Una vez creado, el JSON es la fuente autoritativa. Borrar/regenerar un caso incluye este nuevo
archivo. Un JSON corrupto o de versión desconocida genera error; no se reemplaza silenciosamente.
También se validan HTML, omisiones y revisión aunque el archivo sea JSON sintácticamente
válido. Un archivo inválido produce 503 al leer el caso o guardar; se conserva intacto.
Un borrador vacío (`html: ""`) es válido y no se sustituye por el informe original al reabrirlo.

La API mantiene `nombre`, `html` y `omisiones_ok`. Acepta además `revision` y devuelve
`{ok:true, revision:N}`; GET del caso agrega `borrador_revision`. Una revisión antigua con contenido
distinto produce 409. Un reintento idéntico después de perder la respuesta confirma la misma revisión.
La revisión se comprueba y actualiza bajo el mismo lock que la escritura. Los clientes anteriores
sin ese campo siguen funcionando, aunque no obtienen protección contra escrituras obsoletas.
La interfaz exige una revisión válida cuando el servidor anunció soporte de revisiones;
un HTTP 200 incompleto o sin confirmación no habilita el cierre. La interfaz nueva también
funciona contra el servidor anterior; las garantías atómicas y de
revisión solo están activas después de iniciar el servidor nuevo.

Autoguardado y guardado de formato usan la misma cola de envíos de borrador. Se captura cada
contenido antes de esperar; se usa la revisión confirmada más reciente al enviar. El guardado
de formato conserva su propio indicador y errores: esta etapa no convierte formato, borrador
y Word en una sola transacción de almacenamiento. El formato se publica también con temporal,
fsync y reemplazo; su respuesta debe confirmar `ok:true`. Una edición nueva durante un envío
mantiene el estado pendiente en vez de anunciar que todo quedó guardado.

### Recuperación o vuelta a un servidor anterior

No volver al servidor anterior ignorando los `.borrador.json`: no los sabe leer. Antes de un
rollback, coordinar el cierre de casos y detener escrituras, respaldar todos los datos y convertir
cada JSON v1 validado a `.borrador.html` (campo `html`) y `.omisiones_ok.json` (campo `omisiones_ok`)
en una copia de recuperación. Verificar contenido y permisos antes de promover esa copia.
No borrar el JSON original ni restaurar un respaldo antiguo sobre trabajo reciente. La conversión
y la promoción a producción no se ejecutaron durante esta entrega.

## Cola cifrada de Windows

Se conserva el cifrado DPAPI CurrentUser con entropía `Transcripcion-audio-v1`. La app puede leer
los `.audio` anteriores con su `.nombre`. No cambiar de usuario Windows para recuperar esos datos.

`Agregar` escribe primero el nombre y después el audio cifrado a `.audio.pendiente`, cierra ambos
con `Flush(true)` y publica el audio por renombrado a `.audio`. Los identificadores incluyen GUID.
El lector solo toma `*.audio`; la recuperación inicial y publicación se serializan para no
confundir una escritura activa con una interrumpida. La huella de captura se confirma únicamente
después de que la cola indique éxito. Si falla, el vigilante conserva el candidato y reintenta
cada 10 s mientras siga existiendo el original. Un fallo de notificación no invalida un audio
que ya se guardó.

Al iniciar la cola se recuperan `.audio.pendiente` descifrables con nombre presente. Los temporales
incompletos, `.audio` ilegibles y audios rechazados permanentemente por el servidor se trasladan a:

```text
%LOCALAPPDATA%\Transcripcion\pendientes\recuperacion\
```

Se conserva el contenido cifrado y se avisa; errores transitorios de lectura/permisos no borran
archivos. La cuarentena no se reenvía automáticamente ni se cuenta como pendiente enviable.
Un administrador debe revisar con el mismo usuario Windows, recuperar desde el origen cuando
sea necesario y volver a cargar por la app. No borrar ni limpiar esa carpeta automáticamente.
Los nombres huérfanos o temporales preservados por fallos no son audios confirmados.

El registro local de huellas se escribe como instantánea temporal, con `Flush(true)` y
renombrado/reemplazo. Su fallo posterior no invalida el audio cifrado ya publicado. Un WAV
cuyo tamaño RIFF conocido supera los bytes disponibles no se captura al vencer una espera:
se conserva el candidato y se reintenta cuando el archivo se completa. Se verifica de nuevo
la cabecera y longitud de los bytes efectivamente leídos. Los tamaños RIFF 0/0xFFFFFFFF
siguen usando la estabilidad del archivo, por compatibilidad con grabadores existentes.
Los errores de lectura/bloqueo o permisos conservan el candidato para reintento cada 10 s;
no se lo descarta por superar un minuto. Si desaparece el original antes de que se pueda
leer y cifrar, no existe una copia recuperable en la cola: conservarlo en el grabador sigue
siendo necesario hasta la confirmación de captura.

La cola elimina un audio solo ante HTTP 200 con JSON `ok:true`, `nombre` no vacío y sin
campo `error`. Respuestas vacías, negativas o ambiguas conservan el cifrado y reintentan.
Un error al mostrar el aviso visual tras persistir tampoco convierte la captura en fallida.

En el servidor, la recepción remota escribe atómicamente sus metadatos antes de publicar el
audio completo; después registra la huella y encola. El índice de huellas también usa escritura
atómica. Un lock de recepción serializa la deduplicación/nombre/publicación entre solicitudes
del proceso; el procesamiento de GPU no toma ese lock. Un reintento tras registrar la huella
pero antes de encolar retoma el caso si no tiene estado. No regenera un caso cuyo estado ya existe.

Una caída entre archivos aún puede dejar metadatos huérfanos o un audio duradero sin índice.
Se privilegia conservar bytes: puede haber reenvíos/duplicados y la app no obtiene confirmación
antes de completar recepción/encolado. No es una transacción única entre todos los archivos ni
una garantía de entrega exactamente una vez. La etapa posterior agrega la [cola transaccional
del servidor](cola-servidor.md) para recuperar tareas tras caídas (R10). El lock de recepción
no coordina dos servidores independientes; la cola nueva usa propietario exclusivo local.

## Validación inicial y estado de despliegue

- 21 pruebas Python: compatibilidad, atomicidad, fsync/replace fallidos, revisión, concurrencia,
  contratos HTTP, permisos, Word, médicos y versiones, en copia de ensayo.
- Prueba nativa de `Audios.cs` con stubs: DPAPI real, publicaciones concurrentes, captura fallida,
  recuperación de escritura interrumpida, cuarentena y rechazo de API ficticia.
- Playwright: borradores con errores/demoras, cierre/navegación, orden de escrituras y formato;
  regresión de editor Word, revisión/audio y médicos.
- Compilación con .NET Framework y `--autoprueba`; no se cerraron aplicaciones de usuarios.

La copia de ensayo está en `respaldo/persistencia_20261029_pruebas/sistema`.
El respaldo previo está en `respaldo/respaldo_20261029_163445_antes_de_persistencia_segura`.
La fuente nueva de Python necesita un reinicio coordinado; no se reinició el proceso en uso.
Las páginas ya abiertas mantienen su código cargado; una apertura nueva obtiene los archivos web nuevos.

**Promoción pendiente:** el binario se compila como candidato con `-SoloCompilar`. El actualizador
anterior podía cerrar una ventana oculta con estudio abierto, por lo que ofrecerle el candidato
sin comprobar las sesiones podría interrumpir trabajo. Se conserva el ejecutable distribuido
anterior hasta coordinar una ventana sin estudios abiertos. El verificador de la instalación
detectará esa diferencia intencional entre fuentes y distribución; no declararla una release
ya desplegada. La copia de staging se verifica por separado con su ejecutable candidato.

## Repetir pruebas

Usar siempre checkout aislado con configuración ficticia, como indica [desarrollo.md](desarrollo.md).
`pruebas/borradores.cjs` utiliza las mismas variables de Playwright que las pruebas existentes.
Para la prueba nativa, compilar `pruebas/cola_audios.cs` junto con `cliente_codigo/Audios.cs`
usando `csc.exe` de .NET Framework y referencia `System.Security.dll`. Pasar rutas absolutas de
fuentes al compilador. Ejecutar el resultado con una carpeta nueva y vacía bajo `respaldo/` como
único argumento. Esa carpeta conserva exclusivamente resultados ficticios para inspección.

## Revisión de confirmaciones del 29/10/2026

Se integra en la misma entrega aún no publicada App 1.22 / Servidor 2026.10.46; no se
incrementa una versión por cada revisión de ese candidato. Se conserva la distribución 1.21.

Respaldo anterior: `respaldo/respaldo_20261029_215533_antes_de_confirmaciones_persistencia/`.
Ensayo nuevo: `respaldo/persistencia_cierre_pruebas/sistema/`, con configuración de ejemplo,
sin copiar audios, datos, reglas particulares ni configuración de la instalación.

Resultado: **70 pruebas Python**, las cuatro regresiones de navegador y prueba nativa de cola
con **DPAPI real** aprobadas. Se agregaron casos de borrador vacío, esquema/omisiones corruptos,
HTTP 200 ambiguo para borrador/formato/audio, WAV incompleto durante más de 20 s, publicación
fallida, recepciones concurrentes y recuperación entre recepción y encolado. La cola nativa
se probó con seis respuestas inválidas antes de confirmar la eliminación con un recibo válido.

`test_recepcion_audio.py` entra automáticamente en CI por descubrimiento; las nuevas aserciones
de navegador y C# usan las tareas existentes. No se necesitan modelos, GPU ni datos reales.
Las pruebas simulan fallos y recuperaciones; no se cortó la energía del equipo en uso.

Para recuperar un borrador inválido, conservar primero una copia completa de los archivos del
caso y sus permisos. Revisar el JSON autoritativo sin eliminarlo para forzar un fallback antiguo;
comparar con respaldos y con el texto aún abierto. Reparar/promover solo una copia validada en
una ventana sin escrituras sobre ese caso. Si solo queda el navegador, mantenerlo abierto y
conservar el contenido antes de recargar. No se ejecutó ninguna reparación sobre casos reales.

Candidato recompilado con `cliente_codigo/compilar.ps1 -SoloCompilar`:
`respaldo/compilacion_20261029_220859_948/Transcripcion.exe`. Autoprueba de **392 métodos OK**;
se conservan las dos advertencias CS4014 previas, fuera del guardado. No se sustituyó
`cliente/Transcripcion.exe` (App 1.21), ni se detuvo/reinició el servidor o las PC.
El verificador de fuentes, ejecutable y manifiesto se ejecuta por separado en la copia de
ensayo; la instalación en uso mantiene la diferencia intencional de distribución pendiente.
