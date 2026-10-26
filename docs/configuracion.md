# Configuración

## `configuracion.json`

Se crea en el primer arranque copiando `configuracion.ejemplo.json`. No se versiona.

| Clave | Ejemplo | Descripción |
|---|---|---|
| `modelo_ia` | `"gemma4:12b"` | Modelo de Ollama que arma el informe |
| `modelo_whisper` | `"large-v3"` | Modelo de faster-whisper |
| `dispositivo_whisper` | `"cuda"` | Opcional. `"cpu"` para usar el procesador si no hay placa NVIDIA (mucho más lento) |
| `fuente`, `tamano_fuente` | `"Tahoma"`, `12` | Fuente del Word, de la vista previa y de "Copiar para Word" |
| `lineas_vacias_para_encabezado` | `6` | Renglones vacíos al principio para el encabezado del paciente |
| `linea_vacia_entre_titulo_y_texto` | `true` | Línea en blanco después de cada título |
| `carpeta_audios_nuevos` | `"..\\Audios_nuevos"` | Carpeta de audios recibidos (relativa a `sistema\`; en Linux la barra invertida vale como `/`) |
| `carpeta_informes` | `"..\\Informes"` | Carpeta de los Word y de los datos de revisión |
| `abrir_word_al_terminar` | `true` | Modo consola: abrir el Word generado |
| `ejemplos_por_informe` | `3` | Ejemplos *few-shot* por informe |
| `negrita_titulos` | `true` | Títulos de estudio en negrita |
| `centrar_titulos` | `true` | Títulos de estudio centrados |
| `negrita_si_empieza_con` | `["Categorización conjunta", …]` | Líneas que van en negrita si empiezan así |
| `negrita_lineas_exactas` | `["Tórax", "Abdomen", "Pelvis"]` | Líneas que van en negrita si son exactamente así |
| `pagina` | `{"nombre": "A4", "ancho_cm": 21.0, …}` | Tamaño de hoja y márgenes (superior, inferior, izquierdo, derecho) en cm |

## Variables de entorno

| Variable | Uso |
|---|---|
| `PUERTO_INTERFAZ` | Puerto del servidor (por defecto `8765`) |
| `NO_COLOR` / `FORZAR_COLOR` | Desactivar / forzar colores en la consola |
| `TRANSCRIPCION_REINICIO` | Linux: la ponen los .sh y el servicio; habilita «Reiniciar servidor» en el panel |
| `SIMULAR_IA`, `SIMULAR_SIN_IA`, `SIMULAR_HUECOS`, `SIMULAR_DEMORA` | Modo de prueba sin GPU ni Ollama ([desarrollo.md](desarrollo.md)) |

## Base de conocimiento (`conocimiento/`)

No se versiona: contiene el material propio del servicio. En el primer arranque se crea desde
`conocimiento.ejemplo/`.

### `plantillas.md`

Un estudio por sección, separadas por `## NOMBRE`. Se edita desde la interfaz (**Plantillas**); antes de cada
guardado se hace una copia en `conocimiento/copias/`.

```text
## ECOGRAFÍA RENAL
TITULO: Ecografía Renal Bilateral
PROTOCOLO NORMAL:
-Riñones de forma, tamaño y ecoestructura conservados.
-No se observa dilatación de las vías excretoras.
FRASES HABITUALES:
-Riñón <derecho|izquierdo> de <L>mm de diámetro longitudinal.
```

| Elemento | Significado |
|---|---|
| `## NOMBRE` | Inicio de un estudio. Las palabras del nombre ayudan a detectar el estudio en el dictado |
| `## NOMBRE (estilo Apellido)` | Variante propia de un médico; reemplaza a la general cuando se elige ese médico |
| `TITULO:` | Título del informe. Alternativas separadas por `\|`; aclaraciones entre paréntesis |
| `TEXTO FIJO:` | Líneas que van siempre debajo del título. No se controlan contra el dictado |
| `PROTOCOLO NORMAL:` | Lo que se escribe cuando el médico dicta "protocolo normal" |
| `FRASES HABITUALES:` | Frases que la IA puede usar si se dictan |
| `NOTAS:` | Instrucciones para la IA sobre ese estudio |
| `<...>` | Hueco a completar con lo dictado |

Una plantilla también se puede crear desde un Word (`.docx`) con **Plantillas → "Desde un Word…"**.
Cuando un informe trae un estudio sin plantilla, aparece el botón **"Crear plantilla de…"**.

### `reglas_dictado.md`

Convenciones de dictado en texto libre: "punto y aparte" = nueva viñeta, "barra" = `/`, "le ponemos un 2" = Bi-Rads 2,
deformaciones habituales de Whisper ("para el horario" = periareolar), etc. Si una corrección se repite y la IA no
la aprende sola, conviene convertirla en regla acá.

### `medicos/<Nombre>.md`

Notas de cómo dicta cada médico (estilo, frases preferidas, plantillas propias). Se crean y editan desde
**Médicos** en la interfaz.

### `correcciones_aprendidas.md`

Generado por `aprender.py` en cada guardado. **No editar a mano.**

## `vocabulario.txt`

Términos que se sugieren a Whisper, uno por línea (las líneas con `#` se ignoran). Conviene agregar los términos
que aparezcan mal escritos con frecuencia.

## Informes de referencia (`referencias/`)

Informes Word terminados (sin audio) convertidos a texto. Se envían a la IA solo como guía de formato cuando no hay
ejemplos suficientes del estudio (por ejemplo TC o PET). Se importan con **Plantillas → "Importar informes Word"**
desde `..\Dataset\Informes word\`.
