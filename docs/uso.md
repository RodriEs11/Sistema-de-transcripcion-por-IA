# Uso diario

## Flujo de trabajo

Si en el panel hay transcriptores, cada persona entra con su usuario y la IA arma los informes con su estilo
(plantillas, notas, reglas y correcciones propias). Arriba de la lista: **Mi cuenta** y **Cerrar sesión**. Ver
[usuarios.md](usuarios.md).

1. Abrir **Ollama** y luego **`interfaz.bat`** (o `iniciar_servidor.bat` si se usa desde otras PC).
2. El **médico** se reconoce solo por la voz ([voz.md](voz.md)): dejá «Automático (por la voz)» y confirmalo en
   cada caso al revisar. Solo hace falta elegirlo antes si todos los audios que vas a subir son del mismo médico.
3. **Cargar el audio**: arrastrarlo a la lista o hacer clic en *Cargar audio*. En las PC del trabajo la app los toma sola.
   Estados: *en cola → transcribiendo → generando → para revisar*.
4. **Abrir el caso**: editor de Word con hojas A4 y barra de formato a la izquierda; dictado a la derecha
   (se resalta mientras suena) y debajo la forma de onda con las marcas. El reproductor queda arriba.
5. Atender los **avisos** de arriba: datos dictados que no están en el informe, posibles partes no transcritas
   (▶ escuchar, ✕ descartar) y estudios sin plantilla.
6. Recorrer las marcas con **F2**. Si algo está mal, se escribe encima y la marca desaparece; si está bien, **F10**.
7. **Leer el informe completo**: puede haber errores sin marcar. Revisar el **médico** (junto al título): si no es o
   está sin reconocer, abrir la lista y buscar por nombre o apellido (ignora tildes y mayúsculas).
   La lista tiene altura limitada y desplazamiento. El médico asignado queda en azul con una tilde;
   el mouse y las flechas resaltan las otras opciones en gris sin cambiar la asignación.
   Se puede elegir con las flechas y Enter; Escape cierra la lista sin cambiar el médico.
   El botón pequeño **+** al costado permite agregar y asignar uno nuevo. Al guardar, su voz queda registrada.
8. **Guardar Word y aprender**: crea `Informes\NOMBRE.docx` y registra el tiempo de revisión.
   Con el servidor candidato 2026.10.46, ejemplos e historial se actualizan en segundo plano;
   la confirmación indica ese estado. El Word se puede usar mientras continúa el aprendizaje.
   Alternativa: **Copiar para Word** (con formato) para pegar en un documento con encabezado.

Los cambios se autoguardan como borrador. **Regenerar** vuelve a pedir el informe a la IA (se pierden los cambios).

Desde App 1.22 / Servidor 2026.10.46, el estado del borrador distingue cambios pendientes,
guardado en curso, confirmación y error. Si falla, conservá el estudio abierto y usá **Reintentar
guardado**; los fallos transitorios también se reintentan automáticamente. Si otra sesión cambió
el borrador, preservá tu texto antes de volver a abrir: no se sobrescribe automáticamente.
**Cerrar estudio** no abandona cambios que no pudieron confirmarse. Para salir de la app o
actualizarla, cerrá primero el estudio. Ver [persistencia y recuperación](persistencia.md).

## Atajos de teclado

| Tecla | Acción |
|---|---|
| **F2** | Ir a la siguiente marca: la selecciona, reproduce ese momento y muestra la explicación |
| **F10** | Aceptar la marca actual (estaba bien) |
| **F5** | Reproducir / pausar |
| **F6** | Volver 3 segundos |
| **F7** | Adelantar 3 segundos |
| **F3** | Reducir la velocidad en 0,25× |
| **F4** | Aumentar la velocidad en 0,25× |
| **F9** | Ampliar el editor de Word / volver junto al audio |
| **Alt + clic** en una línea | Escuchar el tramo del dictado de esa línea |
| Clic en una palabra del dictado | Escucharla |
| **Esc** | Cerrar explicación, vista previa o ventana |
| Ctrl + B / I / S | Negrita / cursiva / subrayado (en el editor de Word) |
| Ctrl + Q / T / D / J | Alinear izquierda / centrar / derecha / justificar |
| Ctrl + Z / Y | Deshacer / rehacer |

La velocidad de reproducción va de 0,25× a 2,5×; al reanudar retrocede 1 segundo.
El **volumen** está a la derecha de **+3s**: el deslizador va de 0 % a 100 % (de a 5 %, también con la rueda del mouse
o las flechas), y el parlante silencia y vuelve al nivel anterior; en 0 % se ve tachado. Se guarda en cada PC (depende
de sus parlantes o auriculares) y también vale al arrastrar sobre la onda y en las muestras de voz de Médicos. Si la
barra es muy angosta queda solo el parlante.
Los saltos usan 3 segundos por defecto y se ajustan en **Configuración → Audio y revisión**.
En **Configuración → Atajos de teclado** se puede elegir una tecla de F1 a F12 para cada acción,
incluida siguiente marca. No se permiten teclas
duplicadas. Las preferencias se guardan en esta PC y se pueden restablecer a los valores de la tabla
con **Restablecer atajos predeterminados**. Las ayudas y los botones muestran las teclas elegidas.

## Editor de Word junto al audio

El editor se abre automáticamente al entrar a un caso, junto al dictado y la forma de onda, con hojas A4
de tamaño fijo, separadas y numeradas. **Ampliar editor** o **F9** permite verlo en pantalla completa;
**F9** o **Esc** vuelve a la presentación junto al audio, sin detener la reproducción.
Al llegar al final de una hoja, el texto continúa en otra debajo, incluso dentro de un párrafo largo.
El zoom cambia la escala de las hojas sin alterar los cortes de página.

Se puede escribir, pegar texto y corregir directamente en las hojas. La barra permite cambiar fuente,
tamaño (6 a 96 puntos), negrita, cursiva, subrayado, tachado, color, resaltado y alineación, con deshacer
y rehacer. Seleccionar texto y hacer **clic derecho** abre un menú con opciones de formato,
**Copiar selección** y **Pegar** (texto sin formato). El menú permanece abierto y conserva la
selección al encadenar cambios de formato. Se cierra al hacer clic fuera de él.
Sin selección, el formato de caracteres se aplica a lo que se escriba a continuación.

Los cambios se autoguardan y se conservan al generar el Word o usar **Copiar para Word**.
**Guardar Word y aprender** termina el informe. Las marcas pendientes y sus explicaciones se muestran
en las propias hojas: **F2** selecciona la siguiente y la escucha; **F10** la da por revisada.
**F5** reproduce o pausa; **F6** retrocede y **F7** adelanta. El cursor señala el tramo del dictado y **Alt+clic** en una
línea permite escucharlo. También funcionan las autocorrecciones con formato del Normal.dotm de Word.
Dentro del editor, **Ctrl+S** aplica subrayado (también **Ctrl+U**). El guardado sigue siendo automático.
**Ctrl+Q**, **Ctrl+T**, **Ctrl+D** y **Ctrl+J** alinean a la izquierda, centran, alinean a la derecha
y justifican. El menú contextual muestra estas acciones con iconos. La barra y el menú ofrecen los
mismos 12 colores estándar: negro, blanco, rojo oscuro, rojo, naranja, amarillo, verde claro, verde,
celeste, azul, azul oscuro y violeta, además de un selector para cualquier otro color.

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
- Margen superior de 2,5 cm, sin renglones vacíos adicionales reservados para encabezado.
- Título del estudio (centrado y en negrita), línea en blanco y viñetas que empiezan con `-`.
- Línea en blanco entre estudios y cierre "Lo saluda atte.".

Todo es configurable en `configuracion.json` ([configuracion.md](configuracion.md)).
