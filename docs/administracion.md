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
