# Base de conocimiento de ejemplo

Esta carpeta es un **punto de partida ficticio**. La primera vez que se ejecuta el sistema,
`nucleo.py` copia estos archivos a `conocimiento/` (solo los que falten; nunca pisa los existentes).

La carpeta `conocimiento/` real **no se versiona**: contiene las plantillas propias del servicio,
nombres de profesionales y reglas aprendidas de dictados reales.

| Archivo | Qué es |
|---|---|
| `plantillas.md` | Plantillas por estudio, separadas por `## NOMBRE`. Se editan desde la interfaz (botón *Plantillas*). |
| `reglas_dictado.md` | Convenciones de dictado que la IA debe interpretar. |
| `medicos/<Nombre>.md` | Notas de cómo dicta cada profesional (se crean desde la interfaz). |
| `correcciones_aprendidas.md` | Se genera solo al guardar informes. No se edita a mano. |

El formato completo está documentado en [`docs/configuracion.md`](../docs/configuracion.md).
