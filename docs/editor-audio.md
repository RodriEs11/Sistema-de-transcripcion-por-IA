# Tercera etapa: fluidez del editor A4 y audio

29/10/2026. Integrada en el candidato aún no distribuido **App 1.22 / Servidor 2026.10.46**,
junto con las dos etapas anteriores. No cambia formatos de archivo, API ni preferencias locales.

## Editor

`ponerModelo` encuentra el primer párrafo que cambió. `paginar` conserva las hojas anteriores
y reconstruye desde la hoja previa a la afectada. Retroceder permite que los borrados atraigan
texto de la siguiente hoja. Si el punto de reinicio cae dentro de un párrafo sin modificar,
se conserva su offset; los párrafos largos siguen pudiendo cruzar varias hojas.

Las llamadas de carga inicial y refresco de marcas conservan la reconstrucción completa.
Se mantienen tamaño A4, encabezado, márgenes, zoom, selección, marcas y exportación Word.
Los identificadores de marcas del prefijo se conservan en una reconstrucción parcial.
La búsqueda de párrafos para sincronizar texto y marcas usa índices por texto y mantiene
el orden de ocurrencias repetidas.

No se implementó virtualización ni detención al estabilizarse una página posterior: se reconstruye
todo el sufijo afectado. Una edición al comienzo o de un párrafo largo que empieza en la primera
hoja puede seguir requiriendo todas las hojas. El historial continúa guardando hasta 100 estados
completos y las mediciones de altura siguen siendo síncronas en el sufijo.

## Audio

La onda prepara dos fondos fuera de pantalla (pendiente y reproducido), incluidas marcas,
huecos y selección. Durante reproducción los frames componen esas imágenes y dibujan el
cabezal. Cambios del editor invalidan el fondo; selección, tema, tamaño y carga de onda lo
recalculan por los caminos de actualización existentes. La animación se suspende al ocultar
la pestaña y vuelve al retornar, sin pausar la reproducción.

El audio para arrastre se descarga al interactuar, no al pasar el mouse. Se prepara el buffer
mono y la copia invertida se crea solamente al arrastrar hacia atrás. Al vaciar/cambiar la fuente
de audio se cancela la descarga, se liberan buffers y se detienen los granos programados.
Un contador de generación descarta respuestas y decodificaciones tardías, incluso si se vuelve
a abrir el mismo caso. Las fuentes y ganancias se desconectan al terminar.

La primera interacción puede esperar la descarga y decodificación. El arrastre todavía decodifica
el audio completo y crear su reversa tiene costo proporcional a su longitud; no hay streaming
de granos ni límite de memoria por duración en esta etapa. El AudioContext se reutiliza para
evitar crear dispositivos/contextos en cada caso.

## Pruebas y medición

Los scripts existentes de CI `editor_word.cjs` y `revision_word.cjs` incluyen las nuevas pruebas:

- Documento de 180 párrafos: edición al final conserva la primera hoja por identidad DOM.
- Comparación de contenido y offsets de fragmentos contra reconstrucción completa, con adiciones
  y borrados cerca del principio, medio y final.
- Regresiones de 11 hojas con párrafo largo, formato, pegado, selección, deshacer, guardado y reapertura.
- 60 frames de onda sin cambios reutilizan el fondo: dos pinturas iniciales; una mutación provoca
  otras dos. No se impone un umbral de milisegundos en runners compartidos.
- Descarga de arrastre cancelada sin repoblar buffers; decodificación WAV ficticio, reversa diferida y liberación.
- Atajos, reproducción, saltos, velocidad, borradores y médicos mediante las pruebas de regresión.

En este equipo, la prueba sintética de una edición al final registró **4,3 ms** frente a
**15,8 ms** de reconstrucción completa. Es una muestra orientativa dentro de la misma ejecución,
no un p95 ni garantía en las PC del trabajo. La comparación incluye sincronización del modelo
en el camino incremental; ambas salidas se verifican iguales. La reducción de pinturas de onda
mide trabajo evitado, no porcentaje de CPU ni calidad audible del dispositivo real.

## Respaldo y despliegue

Respaldo previo: `respaldo/respaldo_20261029_205612_antes_de_editor_audio/`.
Ensayo aislado: `respaldo/editor_audio_pruebas/sistema/`. Se usan únicamente documentos y WAV ficticios.
Las cuatro pruebas de navegador y las 24 pruebas Python pasaron. Se revisó la captura del editor.
El candidato compilado está en `respaldo/compilacion_20261029_210006_983/Transcripcion.exe`;
su autoprueba de 390 métodos y la verificación de versiones/manifiesto en staging pasaron.
Se mantienen las dos advertencias previas CS4014 de notificaciones en segundo plano.
No se reinició el servidor ni se cerraron sesiones de usuarios; las páginas ya abiertas conservan
su JavaScript cargado. Las aperturas nuevas reciben la interfaz nueva. La distribución del
ejecutable permanece pendiente para no disparar el actualizador anterior durante trabajo activo.
Ver [persistencia](persistencia.md) y [CI/CD](ci-cd.md) para la promoción coordinada.
