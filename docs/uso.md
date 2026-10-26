# Uso diario

## Flujo de trabajo

1. Abrir **Ollama** y luego **`interfaz.bat`** (o `iniciar_servidor.bat` si se usa desde otras PC).
2. El **médico** se reconoce solo por la voz ([voz.md](voz.md)): dejá «Automático (por la voz)» y confirmalo en
   cada caso al revisar. Solo hace falta elegirlo antes si todos los audios que vas a subir son del mismo médico.
3. **Cargar el audio**: arrastrarlo a la lista o hacer clic en *Cargar audio*. En las PC del trabajo la app los toma sola.
   Estados: *en cola → transcribiendo → generando → para revisar*.
4. **Abrir el caso**: informe editable a la izquierda; dictado a la derecha (se resalta mientras suena) y debajo
   la forma de onda con las marcas.
5. Atender los **avisos** de arriba: datos dictados que no están en el informe, posibles partes no transcritas
   (▶ escuchar, ✕ descartar) y estudios sin plantilla.
6. Recorrer las marcas con **F2**. Si algo está mal, se escribe encima y la marca desaparece; si está bien, **F8**.
7. **Leer el informe completo**: puede haber errores sin marcar. Revisar el **médico** (junto al título): si no es o
   está sin reconocer, elegirlo; al guardar, su voz queda registrada.
8. **Guardar Word y aprender**: crea `Informes\NOMBRE.docx`, registra el ejemplo, el historial y el tiempo de revisión.
   Alternativa: **Copiar para Word** (con formato) para pegar en un documento con encabezado.

Los cambios se autoguardan como borrador. **Regenerar** vuelve a pedir el informe a la IA (se pierden los cambios).

## Atajos de teclado

| Tecla | Acción |
|---|---|
| **F2** | Ir a la siguiente marca: la selecciona, reproduce ese momento y muestra la explicación |
| **F8** | Aceptar la marca actual (estaba bien) |
| **F4** | Reproducir / pausar |
| **F3** | Volver 3 segundos |
| **F9** | Vista previa como Word (con editor de formato) |
| **Alt + clic** en una línea | Escuchar el tramo del dictado de esa línea |
| Clic en una palabra del dictado | Escucharla |
| **Esc** | Cerrar explicación, vista previa o ventana |
| Ctrl + B / I / U | Negrita / cursiva / subrayado (en la vista previa) |
| Ctrl + L / E / R / J | Alinear izquierda / centrar / derecha / justificar (en la vista previa) |
| Ctrl + Z / Y | Deshacer / rehacer |

La velocidad de reproducción va de 0,25× a 2,5×; al reanudar retrocede 1 segundo.

## Marcas de revisión

| Marca | Significado |
|---|---|
| 🔴 Rojo | Número, hora (H12), nivel vertebral (L5-S1), Bi-Rads o ACR que no coincide con el dictado; `[COMPLETAR]` |
| 🟡 Amarillo | La IA no entendió (`[[?…]]`) o Whisper oyó el número con poca confianza |
| 🔵 Turquesa | Línea no encontrada en el dictado, o término clave (sólida/quística, lado, márgenes…) no dictado junto a ese hallazgo |
| ⚪ Gris | Frase de protocolo normal que el médico no dictó explícitamente |

Al pasar el mouse sobre una marca (o al saltar con F2) aparece su explicación, por ejemplo
*"Dictado: Bi-Rads 3 / Informe: Bi-Rads 2"* o *"Dictado: 984951 (Whisper juntó los números) / Informe: 98"*,
junto con el tramo del dictado correspondiente.

## Otras funciones

- **Modo oscuro/claro**: botón luna/sol arriba a la izquierda.
- **Modo compacto**: solo la lista de casos con sus avisos, en una columna siempre visible.
- **Paneles ajustables**: arrastrar los divisores; doble clic vuelve al tamaño original.
- **Autocorrección de Word** (solo en la app del trabajo): los activadores del Normal.dotm (por ejemplo `ECOABD`)
  se expanden con su formato al escribir espacio, Enter o un signo. Ctrl+Z enseguida lo deshace.
- **Pausar una transcripción** (solo en la PC del servidor): botón **Pausar** debajo del audio que se está
  transcribiendo. Se detiene en unos segundos y conserva lo transcrito; **Reanudar** sigue desde ahí. Los audios
  que siguen en la cola esperan hasta que se reanude.
- **Borrar informes**: tacho en cada caso o "Borrar revisados". Cada PC del trabajo solo borra lo que envió.
- **Nombre del paciente**: se detecta del inicio del dictado y se puede corregir con el lápiz del título.
  Solo se muestra en la lista; nunca va al informe ni a la IA.

## Formato del informe

- Tahoma 12, interlineado sencillo, sin espacio entre párrafos, hoja A4.
- Renglones vacíos arriba para el encabezado del paciente (se completa a mano).
- Título del estudio (centrado y en negrita), línea en blanco y viñetas que empiezan con `-`.
- Línea en blanco entre estudios y cierre "Lo saluda atte.".

Todo es configurable en `configuracion.json` ([configuracion.md](configuracion.md)).
