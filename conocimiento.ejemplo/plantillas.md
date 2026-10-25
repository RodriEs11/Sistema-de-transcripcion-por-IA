# PLANTILLAS DE INFORMES (EJEMPLO)
# Este archivo lo lee la IA. Cada estudio empieza con "## NOMBRE" y tiene:
#   TITULO:            el título del estudio (alternativas separadas por "|")
#   TEXTO FIJO:        líneas que van siempre debajo del título (no se controlan contra el dictado)
#   PROTOCOLO NORMAL:  lo que se escribe cuando el médico dicta "protocolo normal"
#   FRASES HABITUALES: frases que la IA puede usar si se dictan
# Los huecos se marcan con <...>. Una plantilla propia de un médico se nombra "## ESTUDIO (estilo Apellido)".
# Este contenido es ilustrativo: reemplazalo por las plantillas de tu servicio.

## RX DE TÓRAX
TITULO: RX de Tórax (frente)  |  RX de Tórax (frente y perfil)   (según lo dictado)
PROTOCOLO NORMAL:
-Campos pulmonares sin imágenes focales.
-Senos costofrénicos libres.
-Silueta cardíaca de tamaño conservado.

## ECOGRAFÍA RENAL
TITULO: Ecografía Renal Bilateral
PROTOCOLO NORMAL:
-Riñones de forma, tamaño y ecoestructura conservados.
-No se observa dilatación de las vías excretoras.
FRASES HABITUALES:
-Riñón <derecho|izquierdo> de <L>mm de diámetro longitudinal.

## TOMOGRAFÍA (TC) - TEXTO COMÚN
TITULO: TC de <Región>
TEXTO FIJO:
Se efectuaron cortes sobre <región>.
Se efectuó el estudio en Tomógrafo <marca y modelo del equipo>.
El examen de los diferentes cortes realizados muestra:
