# Pipeline de IA

Este documento describe cómo un audio se convierte en un informe y cómo se decide qué revisar.

El candidato conserva modelos, prompts y controles. La [etapa de lotes e IA](ia-lotes.md) acota
la espera inicial, reutiliza ASR verificado y ejemplos sin cambios, e incorpora métricas por etapa.

## 1. Transcripción (`transcripcion/asr/whisper.py`, `transcripcion/asr/huecos.py`)

- **Modelo**: Whisper large-v3 con [faster-whisper](https://github.com/SYSTRAN/faster-whisper), CUDA en `float16`.
- **Parámetros**: idioma español, VAD activado, marcas de tiempo por palabra.
- **Prompt de vocabulario**: los términos de `vocabulario.txt` se pasan como *initial prompt* para que Whisper
  escriba bien la terminología (parénquima fibroglandular, anexiales, espondilouncoartrosis…).
- **Lectura de audio**: el WAV se lee con código propio (sin depender de PyAV); otros formatos se decodifican con `av`.

### Segunda pasada sobre tramos perdidos

Whisper a veces "se come" fragmentos (en una prueba tapó 3,3 s con la palabra "aparte" y en otra dejó 9 s sin
transcribir). `transcripcion/asr/huecos.py`:

1. Calcula la energía del audio por ventanas.
2. Busca regiones con voz (`voz_min`) donde no hay palabras durante al menos `gap_min` segundos, o donde una
   sola palabra dura demasiado (`palabra_max`).
3. Vuelve a transcribir **solo esos tramos** (con un pequeño margen) y los inserta en su lugar.
4. Lo que sigue sin texto se informa como **"posible parte no transcrita"** con su inicio y fin.

En la evaluación, la segunda pasada recuperó 218 palabras en 33 audios.

### Normalización

Antes de llegar a la IA, el texto se normaliza: números en palabras a cifras ("veintitrés" → 23),
horas de reloj de mama ("hora 11" → H11), niveles vertebrales ("L5, S1" → L5-S1). También se extraen los
**datos críticos** (números, lados, categorías) que después se usan en los controles.

## 2. Armado del prompt (`transcripcion/ia/prompt.py`)

El mensaje de sistema se compone de:

| Parte | Origen |
|---|---|
| Reglas generales | Código (`SISTEMA` en `transcripcion/ia/prompt.py`) |
| Convenciones de dictado | `conocimiento/reglas_dictado.md` |
| Correcciones frecuentes | `conocimiento/correcciones_aprendidas.md` (generado) |
| Notas del médico | `conocimiento/medicos/<médico>.md` |
| Plantillas | Solo las secciones relevantes de `conocimiento/plantillas.md` |
| Ejemplos | 3 pares dictado → informe final |
| Referencias | 1–2 informes Word del mismo tipo, cuando faltan ejemplos |

### Detección del estudio

El dictado se clasifica en categorías (mama, gine, tiroides, columna, tórax, osteoarticular, TC, PET y los
estudios agregados en `plantillas.md`). Solo se envían las plantillas de esas categorías; TC y PET nunca se
mezclan con radiografías o ecografías. Si no se reconoce el estudio, se envían todas.

### Plantillas por médico

Una sección llamada `## ESTUDIO (estilo Apellido)` reemplaza a la general cuando el médico elegido es *Apellido*.
Sin médico elegido, se envían marcadas como *variante de otro médico*; si el audio tiene huella de voz y el médico no
se reconoció con seguridad (voz dudosa o sin reconocer), no se envían: solo la plantilla general. El médico se
reconoce por la voz antes de llamar a la IA: ver [voz.md](voz.md).

### Selección de ejemplos (*few-shot*)

Se puntúa cada ejemplo disponible por:
- misma categoría de estudio;
- palabras en común con el dictado;
- bonus por mismo médico y por correcciones recientes.

Nunca se usa el mismo audio como su propio ejemplo (evita fuga de datos en las evaluaciones), y una corrección
aprendida reemplaza al ejemplo original de ese audio.

### Llamada al modelo

`POST http://localhost:11434/api/chat` con `gemma4:12b`, `temperature 0.1`, `num_ctx 12288`, sin *streaming*
y sin modo de razonamiento (si el modelo no acepta el parámetro `think`, se reintenta sin él).

## 3. Post-proceso

- **Orden de estudios**: `ordenar_estudios` reordena los bloques de mama, ginecología y tiroides en el orden
  estándar (Mamografía → Ecografía mamaria → Categorización conjunta → Transvaginal → Tiroides), porque el modelo
  a veces sigue el orden del dictado. Las radiografías quedan en el orden dictado.
- Un "Protocolo normal." literal (cuando el estudio no se reconoció) se reemplaza por `[COMPLETAR]` en rojo.

## 4. Controles y marcas

Cada línea del informe se ubica en el dictado (`ventana_dictado`) y se comparan:

| Control | Marca |
|---|---|
| Números, horas, niveles y medidas que no aparecen cerca en el dictado | 🔴 con "Dictado: X / Informe: Y" |
| Números que Whisper juntó ("98, 49, 51" → "984951") | 🔴 con la explicación |
| Bi-Rads y ACR distintos de lo dictado (incluye "un birrastre" = Bi-Rads 3) | 🔴 |
| `[[?…]]` de la IA o número oído con baja confianza | 🟡 con el % de confianza |
| Línea o título sin correspondencia en el dictado | 🔵 |
| Términos clave (lado, sólida/quística, márgenes, ecogenicidad…) no dictados junto al hallazgo (`FAMILIAS`) | 🔵 |
| Frase de protocolo normal no dictada explícitamente | ⚪ |
| Datos críticos dictados que no aparecen en el informe | Aviso superior ("Dictado pero no está en el informe") |

Las líneas de bloques `TEXTO FIJO` de las plantillas no se controlan. Las marcas guardan una versión (`"v": 2`):
si cambian las reglas, los casos viejos se recalculan al abrirlos.

Hay un control adicional de **palabras raras** (palabras deformadas por Whisper que la IA copió tal cual) que se
activa recién con 150 informes revisados, para no generar falsas alarmas con un vocabulario de referencia chico.

## 5. Aprendizaje (`aprender.py`)

Al guardar un informe:

1. Se crea un ejemplo en `ejemplos/`: `FECHA_NOMBRE.dictado.txt`, `.informe.txt` (final), `.ia.txt` (salida original) y `.medico.txt`.
2. Se actualiza una fila por día/caso en `resultados/historial.sqlite3` (importa el CSV anterior una sola vez) con el **% de palabras corregidas** (diferencia entre la salida
   de la IA y el texto final). Volver a guardar el mismo día reemplaza la fila.
3. Se actualiza por ejemplo el índice de correcciones y se publica el top 40 en `conocimiento/correcciones_aprendidas.md`: cambios de palabras repetidos en 2 o más informes
   (por ejemplo *«fibronodulillar» → «fibronodular»*), que la IA lee en cada informe.

> Las correcciones también son ejemplos: un error de tipeo al corregir se propaga. Conviene revisar
> `correcciones_aprendidas.md` de vez en cuando.

## Evaluación

El conjunto de prueba son 33 pares audio → informe final escrito a mano.

| Medida | Fase 2 (Whisper inicial) | Fase 5 (Whisper + vocabulario + segunda pasada + reglas) | Fase 5 + orden automático |
|---|---|---|---|
| Palabras a corregir (promedio) | 13,0 % | 12,2 % | **9,1 %** |
| Palabras a corregir (mediana) | 9,4 % | 7,7 % | **7,7 %** |

Comparación de modelos de lenguaje (fase 2): Gemma 4 12B 13 % de palabras a corregir y 94 % de datos críticos
correctos (≈ 10 s por informe) contra 29 % de Qwen 3.5 9B.

**Limitaciones conocidas**
- Parte de las reglas se escribieron mirando los mismos audios de la evaluación: la medida real de calidad es el
  historial con audios nuevos (página de estadísticas).
- Las autocorrecciones del médico dentro del dictado ("hora 2… hora 12") no siempre se detectan; solo se notan escuchando.

`fase1_transcribir.py` también funciona como herramienta de evaluación de Whisper:

```bat
python fase1_transcribir.py --audios <carpeta> --salida resultados\fase1   :: reporte HTML con y sin vocabulario
python fase1_transcribir.py --verificar                                    :: prueba rápida de la GPU
```

El aprendizaje del servidor candidato se procesa en segundo plano. Ver [migración y mantenimiento](aprendizaje-incremental.md).
