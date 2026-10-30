# Quinta etapa: correcciones incrementales e historial indexado

29/10/2026. Agrupada en el candidato todavía no distribuido **App 1.22 / Servidor 2026.10.46**.
No se migraron datos reales ni se reiniciaron servicios en esta entrega.

## Camino habitual

`registrar_ejemplo` conserva los archivos de ejemplo y calcula las correcciones solo del informe
recibido. SQLite mantiene una firma SHA-256 de IA/texto final, sus aportes distintos y el conteo
de informes que aportan cada corrección. Si el contenido no cambió, no se repite ese análisis.
Si se vuelve a corregir el informe, se restan sus aportes anteriores y se incorporan los nuevos
en una transacción, junto con la actualización de historial.

Se conservan las reglas anteriores: no generalizar cambios con números, diferencias de más de
12 palabras ni cambios que solo difieren en puntuación/mayúsculas. Un ejemplo cuenta una sola
vez para cada corrección. Una edición que deja de justificar una regla reduce su frecuencia.

El índice ordena por frecuencia y desempates de operación/textos, y obtiene hasta 40 reglas
sin ordenar todas las contribuciones en Python. `analizar_correcciones()` publica esas reglas
y ahora devuelve esa misma lista acotada. El Markdown solo se reemplaza si cambió su contenido.
El trabajador duradero de la etapa anterior continúa agrupando esta publicación por pasada.

El historial tiene clave `(día, informe)` y el registro de Word procesados tiene clave de ruta.
Guardar/reintentar actualiza sus filas indexadas sin leer ni reescribir todos los registros.
El CSV y JSON anteriores no se mantienen como espejos en cada guardado. El panel de estadísticas
y el resumen de consola leen la base nueva cuando existe y usan CSV cuando todavía no existe.

No se promete costo constante absoluto: índices B-tree, escrituras duraderas, longitud del
informe, cantidad de correcciones y contención de disco influyen. Se elimina el trabajo habitual
proporcional al número total de informes. Calcular el porcentaje corregido sigue dependiendo
del tamaño de ese informe. Las lecturas completas para estadísticas/exportación siguen siendo
proporcionales a los registros solicitados y el panel todavía lee actividad.csv.

## Esquema y migración

`resultados/historial.sqlite3`, esquema `PRAGMA user_version=1`, es la fuente nueva de historial,
Word procesados y frecuencias. Usa SQLite de la biblioteca estándar, transacciones con rollback,
índices y espera de locks de hasta 15 s. Se conserva el journal tradicional de SQLite; no se
activa WAL. La base debe permanecer en disco local, fuera de Git y de artefactos de CI: contiene
identificadores clínicos y fragmentos de correcciones.

Al abrir por primera vez para escritura se crea el esquema y se importa `historial.csv` en una
transacción; si falla, no se confirma esa migración. `_procesados.json` se importa una sola vez
cuando se utiliza su registro. Los archivos originales quedan intactos como base de recuperación.
El primer análisis importa el corpus de ejemplos y registra que terminó; ese recorrido inicial
puede ser costoso, pero ocurre en el trabajador, fuera de la confirmación del Word.

Las llamadas siguientes no recorren el corpus. Las modificaciones desde la aplicación pasan
por el índice. Para ediciones o borrados manuales de archivos de ejemplo hay una reconciliación
explícita que relee sus firmas, reanaliza los cambios y retira los aportes de ejemplos eliminados.
Los cambios posteriores hechos por programas antiguos directamente al CSV/JSON no se importan
automáticamente. No mezclar procesos antiguos y nuevos sobre el mismo directorio de datos.

Una versión de esquema desconocida genera error en lugar de reinicializar la base. Una falla
de SQLite deja pendiente la tarea de aprendizaje para reintento; no convierte un Word confirmado
en un documento fallido. Los archivos de ejemplo y SQLite son publicaciones separadas: no son
una transacción conjunta; un fallo entre ellas se resuelve al reintentar la tarea conservada.

## Operación explícita y recuperación

Desde `sistema/`, con destinos nuevos bajo `respaldo/`:

```powershell
.venv/Scripts/python.exe mantenimiento_aprendizaje.py --exportar respaldo/historial_exportado.csv
.venv/Scripts/python.exe mantenimiento_aprendizaje.py --respaldar respaldo/historial_copia.sqlite3
.venv/Scripts/python.exe mantenimiento_aprendizaje.py --reconciliar
```

Los dos primeros comandos rechazan destinos existentes. La exportación conserva columnas,
delimitador `;` y UTF-8 con BOM; no implica mantener el CSV original actualizado. El respaldo
usa la API SQLite backup para obtener una copia consistente. No copiar únicamente el archivo
principal durante una transacción activa ni borrar un journal de recuperación.

La reconciliación modifica el índice y el Markdown; programarla en una ventana coordinada si
hay muchos ejemplos. No se ejecutó sobre datos reales en esta entrega. Para rollback a código
anterior, coordinar el cierre de escrituras, respaldar base/datos/ejemplos, exportar el historial
actual y revisar la convivencia de tareas pendientes. El JSON de Word procesados antiguo puede
estar desactualizado: evitar la reimportación masiva de Word que ya fueron aprendidos. No borrar
la base para forzar una reconstrucción: el CSV original no contiene los guardados posteriores.

## Pruebas y medición

Se prueban importación única, archivo anterior intacto, exportación CSV, copia SQLite consistente,
reintentos sin duplicados, reemplazo y retirada de aportes, rollback, reconciliación tras editar
y borrar ejemplos, exclusión de números/puntuación, índice de selección y lectura del panel.
Una prueba prohíbe recorrer directorios o repetir el diff al reintentar un ejemplo idéntico.

`python pruebas/medir_aprendizaje.py` crea bases ficticias aisladas y mide siete transacciones
de actualización de un informe y sus aportes, incluida la consulta top 40:

| Informes | Mediana | Máximo |
|---:|---:|---:|
| 100 | 28,89 ms | 33,64 ms |
| 1.000 | 23,44 ms | 223,44 ms |
| 10.000 | 22,17 ms | 34,55 ms |

Las medianas no muestran crecimiento lineal en ese ensayo. Hay variabilidad de disco y una
muestra de 223 ms; no es un p95 ni una garantía de producción. No incluye migración, exportación,
recorrido de actividad.csv ni cálculo de diferencias de texto: mide el almacenamiento indexado.

Respaldo previo: `respaldo/respaldo_20261029_210913_antes_de_aprendizaje_incremental/`.
Ensayo: `respaldo/incremental_pruebas/sistema/`. La distribución sigue pendiente y el proceso
en uso conserva su versión cargada. La migración real requiere activar el nuevo servidor en
la ventana coordinada pendiente; no se reinició ni se cerró ninguna app para esta etapa.

Resultado de validación: 39 pruebas Python y cuatro pruebas de navegador aprobadas; sintaxis,
enlaces y `git diff --check` correctos. La verificación completa de fuentes, ejecutable y
manifiesto pasa en staging con el candidato ya compilado de la etapa anterior
(`respaldo/compilacion_20261029_210622_502/Transcripcion.exe`). Esta etapa solo cambia Python,
pruebas y documentación: no se recompiló C# ni se sustituyó el ejecutable distribuido 1.21.
El verificador en la instalación en uso sigue detectando esa diferencia intencional respecto
de las fuentes 1.22; no se considera una distribución nueva ya publicada.
