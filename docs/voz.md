# Médico reconocido por la voz

El servidor reconoce qué médico dictó cada audio comparando su **huella de voz** con las de los informes ya
revisados. No hace falta elegir el médico antes de mandar los audios: alcanza con confirmarlo al revisar.

## Cómo funciona

1. Después de Whisper, `transcripcion/voz/huellas.py` calcula la huella del audio: un vector de 256 números que describe la voz
   (modelo **WeSpeaker ResNet34**, entrenado con VoxCeleb, en formato ONNX). Usa solo los tramos con voz (los tiempos
   de las palabras de Whisper), hasta 120 s, en partes de 20 s que se promedian. Corre en el procesador con
   `onnxruntime` (ya viene con faster-whisper) y tarda 1 o 2 segundos; no usa la placa de video.
2. La huella se compara con las **muestras** de cada médico: el parecido es el promedio de sus 3 muestras más
   parecidas (entre las últimas 40).
3. Resultado:

| Estado | Condición (valores por defecto) | Qué pasa |
|---|---|---|
| **Seguro** | parecido ≥ 0,62, le saca ≥ 0,10 al segundo médico, el médico tiene ≥ 3 muestras y el parecido no es más de 0,15 menor que el que tienen sus muestras entre sí | Se asigna el médico solo. La IA usa sus plantillas `(estilo X)`, sus notas y sus ejemplos |
| **Dudoso** | parecido ≥ 0,45 | Se sugiere («¿Pérez? 64 %»). La IA arma el informe con la **plantilla general, sin estilos de médico** |
| **Sin reconocer** | menos de 0,45, o no hay muestras | Sin médico; plantilla general |
| **Corto** | menos de 2 s de voz | Sin médico; plantilla general |

4. Al **Guardar Word y aprender** con un médico elegido, la voz del audio queda como muestra de ese médico
   (`voces/huellas.json`). Si se guarda sin médico, no se registra nada. Si después se cambia el médico de un
   informe ya guardado, la muestra se corrige al momento.

Si el audio llegó con un médico elegido (el de la PC o el de «Médico de los audios que subas»), ese médico se
respeta: la voz solo se anota para las estadísticas.

## En la pantalla

- **Lista**: «🎙 Pérez» = reconocido por la voz; «¿Pérez?» = dudoso; «médico sin reconocer».
- **Barra del caso**, junto al médico: un botón que dice *por la voz · 82 %* (verde), *¿Pérez? 64 %* (amarillo,
  un clic lo elige), *voz sin reconocer* o *elegido a mano*. Al pasar el mouse explica el motivo. Si se elige un
  médico distinto del que usó la IA, el aviso ofrece **Regenerar con este médico**.
- **Médicos**: cada médico muestra cuántas muestras de voz tiene; abajo de sus notas está la lista de muestras con
  ▶ para escuchar y **Quitar** para sacar una mal etiquetada.
- **Médicos → Agrupar voces**: los audios sin médico cuya voz todavía no es muestra de nadie, agrupados por
  parecido (≥ 0,65 en promedio). Se elige el médico, se destildan los que no son y **Etiquetar** los registra
  todos de una vez (también les pone ese médico).
- **Estadísticas → Médico reconocido por la voz**: cuántos se reconocieron solos, cuántos de esos estaban bien,
  dudosos, sin reconocer y los equivocados, por médico.
- «Médico de los audios que subas» tiene ahora la opción **Automático (por la voz)**, que es la de siempre (vacío).

## Archivos

| Archivo | Contenido |
|---|---|
| `transcripcion/voz/huellas.py` | Características (fbank como Kaldi, en numpy), huella, muestras, detección y agrupamiento |
| `transcripcion/voz/servicio.py` | `ServicioVoz`: huella de cada caso, médico detectado, muestra al guardar, agrupar voces, hilo de arranque |
| `sistema/modelos/wespeaker_resnet34.onnx` | El modelo (26 MB). Si falta, el servidor lo baja solo al arrancar desde las versiones publicadas de sherpa-onnx en GitHub y verifica su SHA-256 |
| `sistema/voces/huellas.json` | Muestras etiquetadas: `{"muestras": {caso: {medico, h, fecha, fuente, seg, modelo}}}` |
| `Informes/revision/datos/<caso>.voz.json` | Huella del caso, resultado de la detección, `medico_por` (`voz`, `usuaria`, `pc` o vacío) y `medico_ia` |

`voces/` y `modelos/` no se suben al repositorio. Una huella **no permite reconstruir la voz ni lo que se dijo**,
pero es un dato biométrico de los médicos: se trata como el resto de los datos de la PC servidor.

Al arrancar, el servidor calcula la huella de los casos que todavía no la tienen (sin cambiarles el médico) y los
informes ya guardados con médico suman su voz como muestra.

Borrar un informe borra su `.voz.json`, pero su muestra (si la tenía) se conserva, como lo aprendido por la IA.

## Ajustes (`configuracion.json`)

Opcional, todo con valores por defecto:

```json
"voces": {"umbral_seguro": 0.62, "margen": 0.10, "margen_propio": 0.15, "umbral_dudoso": 0.45,
          "min_muestras": 3, "max_muestras": 40, "min_voz_s": 2.0, "max_voz_s": 120, "agrupar": 0.65}
```

- Si se equivoca al reconocerlo solo (Estadísticas → «Reconocidos con el médico equivocado»): subir `umbral_seguro`
  o `margen`, y revisar las muestras de esos médicos en Médicos.
- Si casi todo queda dudoso aunque el médico tenga varias muestras: bajar `umbral_seguro` de a 0,03.
- Como referencia, con este modelo dos audios de la misma persona suelen dar 0,65 a 0,90 y dos personas distintas
  grabadas con el mismo equipo, 0,2 a 0,55.

## API

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/api/voces` | Estado del modelo, parámetros, muestras por médico y cuántos audios hay sin etiquetar |
| GET | `/api/voces/muestras?medico=` | Muestras de un médico (o de todos) |
| GET | `/api/voces/agrupar` | Grupos de audios sin médico ni muestra, con la sugerencia de cada grupo |
| POST | `/api/voces/etiquetar` | `{nombres: [...], medico}`: pone el médico y registra la voz de cada uno |
| POST | `/api/voces/quitar` | `{caso}`: saca una muestra |

`/api/casos` y `/api/caso` traen `voz` (estado, médico sugerido, puntaje, segundo, motivo, `por`, `medico_ia`,
`muestra`). `/api/caso_medico` devuelve `voz` y `regenerar` (si la IA armó el informe con otro médico).
`/api/medicos` trae `voz` (cantidad de muestras) por médico.

## Registro

Área **VOZ** (cian): médico reconocido, voz dudosa con el motivo, voz sin reconocer, voz registrada al guardar
(«tiene 3 muestras: desde ahora se puede reconocer solo»), etiquetado y muestras quitadas. En DEBUG, el tiempo y el
ranking de cada audio. `actividad.csv` tiene las columnas nuevas `medico_voz`, `voz_estado` y `voz_puntaje`.

## Pruebas

- La extracción de características coincide con `kaldi-native-fbank` (diferencia máxima 0,0002 en valores de ~21).
- Con dos personas de una grabación real (pyannote, 30 s): misma persona 0,73 y 0,87; distintas 0,38 a 0,54.
- Flujo completo con el servidor simulado y voces sintéticas: 3 audios guardados con un médico → el cuarto se
  reconoce solo; otras voces quedan dudosas o sin reconocer; agrupar, etiquetar, quitar muestras, cambiar el médico
  de un informe guardado, borrar, arranque con casos anteriores; la página probada con jsdom.
