# Activación coordinada: App 1.22 / Servidor 2026.10.46

Piloto elegido: **pc-test**. La preparación original conserva sus artefactos y respaldos.

## Estado de activación — 2026-10-30

Con autorización del usuario se comprobó que el proceso real ya ejecutaba Servidor
2026.10.46, con cola vacía, sin pausas ni estudios abiertos. No se reinició ni se cambiaron
dependencias o configuración. Se publicó App 1.22 en `cliente/Transcripcion.exe` mediante
reemplazo atómico del ejecutable congelado, después de verificar el paquete y repetir la
autoprueba Windows (392 métodos). El verificador completo de versiones pasó.

Respaldo privado fresco: `respaldo/respaldo_20261030_014047_antes_de_activar_122/`.
Incluye datos persistidos, perfil local y distribución anterior; las bases SQLite se
copiaron mediante su API de respaldo. Se excluyó únicamente el mutex
`cola_procesamiento.sqlite3.lock`: pertenece al proceso activo y no contiene tareas.
La primera copia se detuvo al encontrar ese archivo bloqueado; se repitió con esa
exclusión explícita, sin detener producción. El inventario final registra la copia terminada.

El ejecutable anterior también queda en `cliente/Transcripcion.exe.viejo-1.21-20261030`,
excluido del manifiesto. Las PC estaban desconectadas y no tenían estudios registrados
abiertos. No se comprobó su cola cifrada remota ni su instalación: **pc-test sigue pendiente
de reconexión y ensayo funcional**, y las demás PC de confirmación de versión. No se
forzó el arranque, cierre ni actualización de una PC remota. El perfil local no tenía
audios cifrados, temporales ni recuperación pendientes y los borradores eran legibles.
La publicación global autorizada se realizó sin ensayo interactivo previo en pc-test;
registrar este límite y mantener el rollback disponible hasta confirmar ese ensayo.

Los pasos siguientes conservan el procedimiento para futuras ventanas y recuperación.

## Comprobación posterior — 2026-10-30

Evidencias: `respaldo/verificacion_post_122_20261030_014452/` (estado inicial/final,
registros y copia aislada). El servidor real anuncia 2026.10.46; el manifiesto ofrece
1.22 y coincide con la huella del ejecutable publicado. Cola SQLite con `quick_check`
correcto, cero pendientes, pausas, errores y estudios abiertos; IA disponible.
Los 144 borradores en disco son legibles y el perfil local no tiene audios cifrados,
temporales ni recuperación pendiente. Esto no verifica el perfil de una PC remota.

Todas las PC siguen desconectadas: pc-test conserva como último reporte 1.11,
pc-rodri 1.21 y pc-rodriweb no registra versión. **No hay instalación 1.22 confirmada.**
No confundir ese reporte histórico con una inspección actual del disco remoto.

Ensayo con configuración/conocimiento de ejemplo y datos ficticios: 51 pruebas Python
(borradores, recepción, cola persistente, Word/aprendizaje), tres regresiones de navegador
(borradores, editor, reproducción WAV) y cola nativa con DPAPI real: todas aprobadas.
La primera tanda Python se detuvo por bloqueos/fallos en el entorno restringido;
la repetición con permisos locales terminó completa. Se detuvo únicamente ese proceso
de ensayo. No se reiniciaron servicios, cerraron aplicaciones ni enviaron casos ficticios
a producción. La copia de esta documentación anterior queda en `previos/` de las evidencias.

Queda pendiente la reconexión de cada PC y el ensayo interactivo de pc-test; las pruebas
aisladas no comprueban su micrófono, altavoz, conectividad ni cola cifrada remota.

## Paquete concreto

Preparación local: `respaldo/activacion_20261029_230255/`.

| Contenido | Uso |
|---|---|
| `entrega/candidato/sistema/` | Fuentes congeladas 2026.10.46 y conjunto cliente 1.22 probado, sin credenciales/datos |
| `entrega/rollback/sistema/` | Fuentes de Git HEAD 48afe404, Servidor 2026.10.45 y binario distribuido App 1.21 |
| `manifiesto_entrega.json` | SHA-256 de todos los archivos del candidato y rollback; integridad, no firma del editor |
| `privado/` | Respaldo de audios, informes, conocimiento, ejemplos, historial, voces, registros, configuración y estado local de la app |
| `estado_previo.json`, `estado_final.json` | Auditoría con cantidades, sin contenido clínico; bloqueos explícitos |
| `resumen_respaldo.json` | Cantidad y tamaño copiados, SQLite verificados y límites de consistencia |
| `INFORME.md` | Resultado final de esta preparación y condiciones pendientes |

El paquete completo tiene ACL privada para el usuario actual, SYSTEM y administradores.
**No distribuir `privado/`, sus inventarios, configuración, acceso remoto o perfil de la app.**
La carpeta `entrega/` no incluye `conexion.json`; se conserva el de cada instalación y nunca
se copia el perfil/llave DPAPI del servidor a pc-test. Mantener todo el paquete fuera de Git.

La copia del cliente anterior usa su manual 1.21 de HEAD, no el manual 1.22 que ya estaba en
el workspace. Se respalda aparte la carpeta distribuida tal como estaba para trazabilidad.
Las fuentes actuales tienen cambios sin commit: el commit base solo no reproduce la entrega;
la lista de archivos y sus hashes identifican los bytes preparados.

## Qué puede confirmar la inspección

El estado del servidor se consulta solo con GET local. Si no está escuchando, las colas, pausas,
casos abiertos y cambios en memoria quedan **desconocidos**, no se presentan como cero.
Los borradores en disco se validan sin reescribirlos. El recuento de cola cifrada corresponde
únicamente al perfil local inspeccionado; no demuestra que pc-test u otra PC estén libres.
La preparación siempre deja `activacion_autorizada:false`: no equivale a una ventana aprobada.

El respaldo coteja tamaño/fecha y SHA-256 del origen y copia; reintenta hasta tres veces si
un archivo cambia. SQLite se copia con su API y se comprueba integridad, sin migrar el origen.
No es una instantánea transaccional de todas las carpetas ni cubre texto sin guardar en RAM.
Repetir el respaldo al cerrar la ventana si hubo trabajo posterior. Las voces y nombres de
tareas son datos sensibles aunque no sean el cuerpo de un informe.

## Preparación y comprobación sin activar

La herramienta `preparar_activacion.py` exige una carpeta nueva, vacía y con ACL protegida
bajo `respaldo/`. Por defecto muestra ayuda. Con `--preparar` solo copia, audita y empaqueta;
no tiene una opción para aplicar la actualización. No importa el servidor sobre datos reales.

```powershell
.venv/Scripts/python.exe -B verificar_paquete.py respaldo/activacion_20261029_230255
.venv/Scripts/python.exe -B respaldo/activacion_20261029_230255/entrega/candidato/sistema/verificar_versiones.py
.venv/Scripts/python.exe -B respaldo/activacion_20261029_230255/entrega/rollback/sistema/verificar_versiones.py
```

Usar `-B` para no agregar `__pycache__` a los artefactos congelados. Probar en una copia de
ensayo con configuración de ejemplo, nunca iniciar esos servidores contra las carpetas reales
para un ensayo. El manifiesto de actualización de las PC lo calcula `app_cliente.py`; el
manifiesto del paquete es un control independiente y no lo reemplaza.

## Ventana de activación: condiciones obligatorias

1. Confirmar con las dos PC registradas y pc-test cuál participa, nombre y versión instalados,
   si hay captura activa, cola cifrada, temporales o recuperación pendiente y estudio abierto.
   Cerrar el estudio desde la aplicación y esperar confirmación del borrador/Word. Ocultar la
   ventana no prueba que se hayan guardado los cambios. No enviar avisos a otras personas desde
   esta preparación; esa coordinación queda para el operador.
2. Tomar un estado fresco del panel: cero tareas activas, cero pausas, cero estudios abiertos
   y cero aprendizaje pendiente. Una pausa es trabajo pendiente. No reanudarla ni cancelarla
   para obtener un contador en cero sin decisión de quien trabaja con ese audio.
3. Si el servidor está apagado o no responde, no arrancarlo a ciegas solo para comprobar.
   Conciliar los archivos, pausas anotadas y capturas de cada PC. La primera migración no puede
   reconstruir pausas antiguas que nunca se guardaron en disco.
4. Detener nuevas capturas/ediciones **solo durante la ventana acordada**, terminar el trabajo
   actual y repetir respaldo y auditoría. Verificar espacio libre e integridad de la entrega.
   Si cambia cualquier condición entre comprobación y despliegue, posponer y comprobar otra vez.
5. No instalar/actualizar dependencias junto con este cambio. Conservar `.venv`, pesos y rutas.
   Registrar las versiones del runtime que pasó GPU y pruebas. La instalación observada usa
   PyAV 19.0.2 frente a `av<16` declarado; la validación GPU fue con WAV/lector propio. No convertir
   este despliegue en una reinstalación de dependencias ni afirmar validación de otros formatos.

## Aplicación en orden durante esa ventana

1. Con el servidor cerrado de forma coordinada y los clientes libres, verificar hashes y copiar
   las fuentes del candidato a `sistema/` conservando las rutas relativas. No copiar configuración
   local, conocimiento real, audios, resultados, bases ni carpetas de ensayo desde el paquete.
   Esos datos se conservan en su lugar. Las fuentes de esta instalación ya contienen el candidato;
   comparar hashes antes de copiar y no sobrescribir cambios nuevos que aparezcan después.
2. Mantener todavía la carpeta publicada `sistema/cliente/` en App 1.21. Ejecutar el lanzador
   habitual del servidor en una ventana controlada. La cola SQLite se abre/importa antes de
   atender HTTP. Si falla recuperación o integridad, no borrar la base para forzar el arranque:
   conservar evidencias y aplicar el plan de recuperación.
3. Comprobar versión **cargada** 2026.10.46 en el panel, salud de IA y ausencia de migraciones
   fallidas. Comprobar que las pausas/revisiones conservadas coinciden con la conciliación.
   Un número de versión leído del archivo no demuestra que ese proceso ya lo cargó.
4. Copiar solo el conjunto `candidato/sistema/cliente/` a una carpeta de ensayo en **pc-test**,
   con su App anterior cerrada normalmente y cola segura. Conservar su perfil, llave y usuario
   Windows. Si pc-test no está vinculada, vincularla por el flujo normal cuando el servidor
   esté disponible; no reutilizar el perfil cifrado de otra PC ni registrar una PC durante esta preparación.
5. En pc-test usar un dictado ficticio: capturar, esperar recepción, abrir, reproducir, editar,
   guardar/cerrar, reabrir, generar Word y comprobar aprendizaje/recuperación. Probar un corte
   de conectividad únicamente en ese ensayo. Confirmar App 1.22 ejecutándose y cierre seguro.
6. Solo después del piloto, publicar el conjunto cliente probado en una ventana sin estudios
   ni audios pendientes en todas las PC. No recompilar para promover. Conservar el conjunto
   distribuido anterior completo y sustituir cada archivo mediante temporal/renombrado en su
   misma carpeta, reteniendo el anterior. La carpeta `cliente/` no tiene canales de piloto:
   ofrecer ahí 1.22 la ofrece a **todas** las PC. La App 1.21 podía actualizar una ventana oculta
   con estudio abierto; por eso este control no puede delegarse al actualizador viejo.
7. Ejecutar el verificador completo en la instalación, comprobar el manifiesto generado por
   `app_cliente.py`, y registrar por separado servidor reiniciado, versión publicada y versión
   confirmada por cada PC. Observar errores, guardados y tiempos antes de cerrar la ventana.

No se proporciona un script que publique automáticamente por tener hashes válidos: faltan
las condiciones humanas y de cada PC, y no hay un bloqueo global de admisión de nuevos trabajos.

## Rollback según el momento

**Antes de aceptar trabajo nuevo:** con la misma ventana controlada, conservar la situación
fallida, detener el servidor nuevo y restaurar únicamente las fuentes y conjunto cliente de
`entrega/rollback/sistema/`. Mantener configuración, llaves y datos; no volcar indiscriminadamente
un respaldo antiguo sobre ellos. El código nuevo adicional puede quedar apartado según la lista
de archivos, sin borrados recursivos ni tocar carpetas de pacientes. Verificar 1.21/2026.10.45.

**Después de guardar trabajo con el nuevo servidor:** no restaurar una imagen vieja de datos.
Si solo falla el escritorio, preferir volver el binario de pc-test conservando el servidor nuevo
y sus formatos. Si es necesario degradar también el servidor, cerrar la ventana de escrituras,
conservar una copia reciente, resolver/drenar tareas, pausas, errores y aprendizaje con el nuevo
código y preparar una copia compatible:

```powershell
.venv/Scripts/python.exe rollback_datos.py --origen RUTA_COPIA_RECIENTE --salida RUTA_COPIA_COMPATIBLE_NUEVA
```

`RUTA_COPIA_RECIENTE` tiene el formato de `privado/`: `informes/revision/datos`, `resultados`,
`ejemplos`. La herramienta rechaza destinos existentes, enlaces, solapamientos, JSON inválidos,
trabajo/pausas/errores/borrados en la cola o aprendizaje pendiente. Convierte borradores JSON a
HTML/omisiones antiguos, exporta historial y Word procesados desde SQLite, y aparta los formatos
nuevos conservándolos. Todo ocurre en una copia nueva; no activa ni restaura producción.
Revisar y validar esa copia antes de promoverla durante la ventana, conservando los originales.
No mezclar después procesos antiguos y nuevos sobre un mismo historial sin reconciliación.

El ensayo de rollback usa exclusivamente datos ficticios e incluye una corrección posterior a
la activación para demostrar que no desaparece al volver al formato anterior. No se ejecutó
esa conversión sobre pacientes. La compatibilidad de archivos no sustituye la conciliación
de colas cifradas de cada PC ni recupera borradores que nunca salieron de la memoria del navegador.
