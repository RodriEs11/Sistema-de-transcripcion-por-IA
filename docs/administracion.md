# Administración

## Ventana del servidor

La consola muestra un cartel de inicio (interfaz, modo de prueba, acceso remoto y PC vinculadas, estado de Ollama
y del modelo, Whisper, placa de video, casos pendientes) y después **una línea por evento**:

```
22:14:05   OK     AUDIO     Audio recibido de info-01: «caso.wav» · 0:23 · 412 KB
```

- **Niveles**: OK, INFO, AVISO, ERROR (DEBUG solo va al archivo).
- **Áreas**: AUDIO, WHISPER, IA, INFORME, CASO, ACCESO, TÚNEL, CONFIG, SERVIDOR, APP.
- El **título de la ventana** resume: IA lista o no, audios en proceso, túnel, informes del día y errores.
- Los errores muestran un mensaje breve en pantalla y el *traceback* completo en el archivo.
- **Ctrl+C** apaga el servidor y muestra el resumen del día.

## Registros (`registros/`, no versionado)

| Archivo | Contenido |
|---|---|
| `servidor_AAAA-MM-DD.log` | Todo lo del día, incluidos *tracebacks* y la salida de `cloudflared`. Se puede abrir mientras el servidor corre |
| `actividad.csv` | Una fila por informe generado, guardado o con error: PC, médico, estudios, duración, tiempos de Whisper e IA, marcas por color, datos faltantes, huecos, % corregido, tiempo de revisión. Separador `;` y coma decimal (abre directo en Excel) |

Si `actividad.csv` está abierto en Excel, el servidor guarda las filas pendientes y las escribe después.

## Panel de administración

**http://127.0.0.1:8765/admin** (engranaje al pie de la lista, en la PC del servidor).

Muestra:
- Servidor (activo desde, versión, modo prueba), IA, placa de video, contadores del día.
- Túnel: estado, dirección (con botón Copiar), centro de Cloudflare, publicación en ntfy, reinicios.
- PC del trabajo: conectada ahora o última vez, versión de la app (al día / por actualizar), médico, sesiones, caso abierto.
- Últimos errores y avisos de hoy y ayer, con filtro y detalle técnico.

Acciones: reiniciar el túnel, volver a publicar la dirección, anular una PC, cambiar la contraseña de acceso remoto,
configurar la contraseña del panel remoto, abrir el registro o las carpetas (solo en la PC del servidor).

### Mantenimiento (desde la versión 2026.10.27)

- **Cambios sin tomar**: el servidor anota la versión de cada archivo de Python que carga (también los que se
  importan tarde, como `aprender.py` o `huecos.py`) y de `configuracion.json`. Si alguno cambia en la carpeta,
  el panel lo muestra y sugiere reiniciar. Las páginas (`web/`), las plantillas y las reglas no necesitan
  reiniciar: se leen en cada pedido.
- **Versión del código**: commit con el que arrancó el servidor, commit actual de la carpeta y archivos sin
  commitear. Usa `git` si está instalado; si no, lee `.git` directamente (commit y archivos modificados).
- **Reiniciar servidor**: en cuanto termine lo que se está procesando, en 1 minuto o en 5 minutos, con o sin
  cartel en las PC. Antes se prueba el código nuevo en otro proceso (compila todos los `.py` e importa
  `servidor`): si falla, no se reinicia y se muestra el error. Mientras espera, no empieza audios nuevos; si la
  IA está cerrada, no espera. «Reiniciar ya, sin esperar» corta lo que se esté procesando. Los audios de la cola
  se anotan en `Informes/revision/cola_al_reiniciar.json` y se retoman al volver.
  - Funciona si el servidor se abrió con `iniciar_servidor.bat` o `interfaz.bat`: el servidor termina con el
    código 75 y el `.bat` lo vuelve a abrir en la misma ventana (sin abrir otra pestaña del navegador). Las
    líneas del `.bat` anteriores a `python servidor.py` no se tocan, porque Windows lee el archivo mientras corre.
  - Al reiniciar se pierden las sesiones en memoria: las apps vuelven a entrar solas con su llave; el panel desde
    el trabajo pide de nuevo su contraseña. Con túnel, la dirección cambia y se publica sola.
- **Mensaje a las PC del trabajo**: un cartel arriba a la derecha de la página de informes (también en modo
  compacto), por un tiempo o hasta quitarlo. Cada PC lo cierra con «Entendido». Vive en memoria: se borra al
  reiniciar. El aviso del reinicio usa el mismo cartel, con la cuenta regresiva.
- **Cola de procesamiento**: qué se transcribe o genera, cuánto lleva cada etapa, el orden y cuánto falta
  (estimado con los tiempos de los últimos informes). **Pausar / Reanudar** (solo en la PC del servidor): detiene
  la transcripción en curso al terminar el tramo actual, conservando lo transcrito; lo que sigue en la cola espera.
  La parte de la IA (unos segundos) no se puede pausar. Si se reinicia el servidor con una transcripción en pausa,
  ese audio queda «sin procesar» (botón Procesar en la lista).
- **Casos abiertos ahora**: qué PC tiene cada caso, desde cuándo y si sigue dando señal. **Liberar** se lo saca:
  la página de esa PC se cierra con un aviso en la próxima renovación (15 s) y sus guardados se rechazan hasta
  que lo vuelva a abrir desde la lista.

### Desde las PC del trabajo

Se habilita en el panel local con una contraseña propia (mínimo 10 caracteres, distinta de la de acceso remoto).
Desde el trabajo no se pueden abrir carpetas, cambiar la contraseña del panel ni cerrar sus sesiones.

## Estadísticas

**http://127.0.0.1:8765/admin/estadisticas**

- Período: 7 días, 30 días, 3 meses o todo.
- Resumen: informes revisados, % corregido (promedio y mediana, con variación contra el período anterior),
  tiempo de revisión, palabras corregidas, marcas por informe.
- Por semana, por médico y por estudio, con la **parte del trabajo** de cada uno (tiempo de revisión si está
  medido en al menos el 80 % de los informes; si no, palabras corregidas).
- Lista de informes del período con colores por % corregido (verde < 5 %, amarillo 5–15 %, rojo ≥ 15 %).

El **tiempo de revisión** cuenta solo segundos activos: caso abierto, ventana visible y teclado/mouse en el último
minuto o audio sonando.

Desde la versión 2026.10.27 también muestra **tiempos de procesamiento** (de las filas «generado» y «error»
de `actividad.csv`): IA por informe (mediana, promedio y percentil 90), Whisper por minuto de audio, total por
audio, comparados con el período anterior, por semana, los 10 más lentos (en rojo los que tardaron más del doble
de lo normal) y los errores al procesar.

## Correcciones

**http://127.0.0.1:8765/admin/correcciones** (`correcciones.py`)

Compara la salida de la IA (`ejemplos/*.ia.txt`) con el informe final (`ejemplos/*.informe.txt`) palabra por
palabra (los cambios de renglón separan los cambios) y junta los reemplazos, agregados y borrados que más se
repiten, contando en cuántos informes aparece cada uno. Filtros: período, médico y si se incluyen los cambios solo
de puntuación o mayúsculas. No cuenta cambios con números ni reescrituras de más de 12 palabras. Marca los que ya
menciona `reglas_dictado.md` y los que ya están en `correcciones_aprendidas.md`.

**Convertir en regla** (solo en la PC del servidor) agrega un renglón editable al final de
`conocimiento/reglas_dictado.md`, en la sección «REGLAS AGREGADAS DESDE EL PANEL», con copia de la versión anterior
en `conocimiento/copias/`. La IA lo usa desde el próximo informe.

## Borrar informes

- Desde la lista (tacho) o "Borrar revisados". Las PC del trabajo solo pueden borrar lo que enviaron.
- Se borran: el audio de `Audios_nuevos`, los archivos del caso, el Word y su huella (si se reenvía el mismo audio,
  se procesa de nuevo).
- **No** se borran los ejemplos aprendidos, el historial ni las estadísticas.
- No se puede borrar un caso que se está transcribiendo, que tiene abierto otra PC o cuyo Word está abierto.

## Mantenimiento recomendado

- Revisar `conocimiento/correcciones_aprendidas.md` cada tanto (un error al corregir se propaga como regla).
- Hacer copia de seguridad de `conocimiento/`, `ejemplos/`, `resultados/` y `acceso_remoto.json`: son lo único
  que no se puede regenerar.
- Comparar versiones del sistema con la evaluación de [pipeline.md](pipeline.md#evaluación).
