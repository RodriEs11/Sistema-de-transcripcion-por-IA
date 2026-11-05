# Instrucciones persistentes del proyecto

## Antes de modificar

- Leer `docs/desarrollo.md` y, para escritorio, `docs/compilacion.md`. Para versiones y entregas, `docs/versiones.md`.
- Revisar `git status` y conservar los cambios existentes del usuario.
- Esta carpeta es una instalación en uso: respaldar los archivos que se van a cambiar
  en `respaldo/respaldo_AAAAMMDD_HHMMSS_antes_de_<cambio>/` antes de editarlos.
- No usar datos de pacientes en pruebas. No versionar secretos, configuración local,
  informes, audios, registros ni binarios. No sobrescribir la configuración local con la de ejemplo.
- Hay un refactor por etapas en curso: antes de mover o reorganizar código, leer `docs/refactor.md`
  (reglas de cada PR, estructura destino y estado). Las decisiones de arquitectura van en `docs/adr/`.

## Qué significa cada pedido

| El usuario dice | Hacer | No hacer |
|---|---|---|
| «subí a GitHub», «subí los cambios» | Publicar la rama y abrir un PR hacia `main` | Fusionar, crear etiquetas ni preparar una entrega |
| «sacá versión», «publicá», «distribuí», «hacé la entrega» | Preparar una entrega (sección «Versiones y entregas») | Subir versiones en una rama de trabajo |
| «fusioná», «mergeá» | Fusionar el PR indicado | Crear etiquetas si no lo pidió |

Si no está claro cuál de estos pedidos es, preguntar antes de actuar.

## Ramas y orden de trabajo

El usuario exige una rama nueva para cada nueva tarea de cambios o mejoras, antes de editar.

- No desarrollar ni hacer commits directamente en `main`.
- Para una tarea nueva, consultar el remoto y partir de `main` actualizado mediante avance
  rápido, sin sobrescribir trabajo local. Si no hay acceso al remoto, explicitar esa limitación.
- Usar nombres breves en minúsculas con guiones y prefijo según el propósito:
  `feat/`, `fix/`, `refactor/`, `docs/`, `test/` o `chore/`. Ejemplo: `feat/atajos-editor`.
  Las entregas usan `release/` (ej. `release/app-1.29-servidor-2026.11.16`).
  Los experimentos usan `exp/` y parten de `experimental` (ver «Experimentos»).
- Una rama por objetivo coherente. Los ajustes y correcciones de la misma tarea continúan
  en su rama; una tarea distinta comienza en otra. No reutilizar una rama ya integrada.
- Revisar el estado antes de cambiar de rama; no arrastrar cambios ajenos, descartarlos,
  usar `reset --hard` ni reescribir historial compartido. Conservar siempre el trabajo existente.
- Mantener commits pequeños y coherentes con Conventional Commits en español; incluir
  las notas del CHANGELOG, la documentación y las pruebas del cambio.
- Al pedir el usuario subir cambios, publicar la rama con seguimiento remoto y preparar
  un pull request hacia `main`. Integrar mediante PR tras las comprobaciones, sin push
  directo a `main`, salvo instrucción explícita del usuario que autorice esa excepción.
- No eliminar ramas con trabajo pendiente. Al terminar, indicar rama, commit y PR si se publicó.

## Experimentos

Guía completa: `docs/experimentos.md`.

- Los cambios de prueba, que quizá no lleguen a la versión final, van en `exp/<tema>` creada
  desde `experimental`, con PR hacia `experimental` (nunca hacia `main`). `test/` no es para esto.
- `experimental` es permanente y nunca se fusiona entera en `main`. Para incluir un experimento,
  crear `feat/<tema>` desde `main`, traer los commits (`cherry-pick` o rehacerlos) y completar
  notas del CHANGELOG, documentación y pruebas como en cualquier PR.
- En `exp/` y `experimental` no tocar versiones ni notas de «Sin publicar»: el número se asigna en la entrega.
  No distribuir a las PC del trabajo binarios compilados desde esas ramas.
- No cambiar de rama en la instalación en uso para probar. Usar una copia creada con
  `python scripts/crear_entorno_pruebas.py` (otra carpeta, otro puerto, sin túnel, IA simulada por defecto).
  La IA real de esa copia comparte GPU y Ollama con producción: solo sin trabajo en curso.

## Versiones y entregas

Guía completa con comandos: `docs/versiones.md` (decisión en `docs/adr/0002-versiones-por-entrega.md`).
El usuario pidió que esto se haga sin tener que recordarlo en cada cambio.

**Un número por entrega, no por PR.** Una entrega es lo que se activa junto en el servidor y/o se distribuye a
las PC, y la decide el usuario. Un PR fusionado no es una entrega. Así se evitan versiones de más (el 03/11 hubo
11 del servidor) y dos ramas que se disputan el mismo número.

### En cada PR de trabajo (`feat/`, `fix/`, `refactor/`, `perf/`, promoción de experimentos)

- No tocar `Programa.VERSION`, `AssemblyVersion`, `AssemblyFileVersion` ni `VERSION` de `servidor.py`.
- Un cambio funcional no está terminado sin su nota en `CHANGELOG.md` → «Sin publicar», bajo `### App` y/o
  `### Servidor`, con categoría `####` (Agregado, Cambiado, Corregido, Quitado, Interno) y el issue (`#NN`).
  Describir el resultado para quien usa el sistema, no la lista de archivos.
- La página principal (`web/index.html`, `web/js/principal/`, `web/css/principal/`) lleva nota en App y en Servidor.
- Un refactor con contratos en verde va como «Interno», sin versión propia.
- Solo documentación, pruebas, CI o herramientas de desarrollo: sin nota obligatoria.
- En el PR, decir qué componente afecta y si rompe compatibilidad. Si exige una versión mínima del otro
  componente, escribirlo en la nota («Requiere Servidor ≥ …» / «Requiere App ≥ …»).

### Al preparar una entrega (rama `release/…`, solo cuando el usuario lo pide)

1. Elegir los números:

   | Cambio incluido | App (`MAYOR.MENOR[.PARCHE]`) | Servidor (`AAAA.M.N`, fecha de Buenos Aires) |
   |---|---|---|
   | Corrección en la app | PARCHE: 1.28 → 1.28.1 | — |
   | Función nueva o cambio visible en la app | MENOR: 1.28 → 1.29 | — |
   | La app deja de funcionar con servidores anteriores | MAYOR: 1.x → 2.0 | sube |
   | Página principal | MENOR | sube |
   | Comportamiento, API, procesamiento o páginas del servidor | — | 2026.11.15 → 2026.11.16; mes nuevo → 2026.12.1 |

   Si hay varios cambios, gana el más grande. Todo lo que tenga notas en «Sin publicar» entra en la entrega.
2. `python herramientas/subir_version.py --app parche|menor|mayor --servidor --leeme "línea para las PC"`
   (`--sin-escribir` para ver los números antes). Cambia `Programa.cs` (los tres valores), `servidor.py`,
   CHANGELOG y `cliente/LEEME.txt`. No editar esos números a mano.
3. Revisar las entradas generadas y actualizar la documentación que nombra versiones.
4. `python herramientas/verificar_versiones.py --sin-binario --entrega`; commit `chore(release): App X y Servidor Y`; PR hacia `main`.
5. Después de fusionar, y solo con autorización del usuario para publicar: etiquetas anotadas `app-vX` /
   `servidor-vY` en el commit de la fusión y `git push origin <etiquetas>`. Nunca mover ni reutilizar una etiqueta
   ni un número publicado.
6. La instalación se actualiza a la etiqueta (`git merge --ff-only <etiqueta>`), no a la punta de `main`.

### Documentación de cada cambio

- Actualizar README y documentación afectada: atajos, ayuda, instalación, configuración,
  dependencias y compatibilidad según corresponda. Revisar pantallas que comparten estilos.
- No escribir el número de versión actual en la documentación: queda viejo. Para eso están el CHANGELOG y el
  panel. «Desde la versión X» sí se puede, y se completa al preparar la entrega.
- Si cambian opciones, actualizar `configuracion.ejemplo.json` y los valores predeterminados,
  manteniendo compatibilidad con configuraciones guardadas; no cambiar preferencias locales
  sin que la tarea lo requiera. Si cambia un formato persistido o protocolo, revisar consumidores,
  migración, versiones de formato y convivencia con clientes anteriores.

## Compilar, verificar y entregar

- Ejecutar pruebas pertinentes a lo modificado: Python, JavaScript, exportación a Word,
  interfaz en modo simulado y/o Windows según el alcance. No sustituir una prueba funcional
  por comprobar números de versión. No duplicar pruebas sin motivo.
- Los contratos `pruebas/test_contrato_http.py` y `pruebas/test_contrato_nucleo.py` fijan el comportamiento.
  Un refactor nunca los regenera; un cambio funcional deliberado regenera el del núcleo
  (`ACTUALIZAR_CONTRATOS=1`) y explica el diff en el PR. `python -m ruff check .` sin errores.
- Para Windows ejecutar `powershell -NoProfile -ExecutionPolicy Bypass -File cliente_codigo/compilar.ps1`
  (la opción de ejecución aplica solo a ese proceso; no cambia la política de Windows).
  Compila a una carpeta temporal, verifica versión y ejecuta `--autoprueba` antes de sustituir
  `cliente/Transcripcion.exe`. Conserva el ejecutable anterior para recuperación.
  Para Linux usar el flujo Mono de `docs/compilacion.md` y su autoprueba.
- `python herramientas/verificar_versiones.py` comprueba código, CHANGELOG, LEEME, ejecutable y manifiesto, y que
  ninguna versión sea anterior a la última etiqueta. En un checkout sin binarios usar `--sin-binario`
  (no confirma una distribución lista); en una rama `release/`, agregar `--entrega`.
- Revisar `git diff --check`, el diff y `git status`. Los binarios son distribución local,
  no archivos para Git. No incluir datos clínicos o secretos en commits ni salidas.
- El manifiesto lo calcula `transcripcion/operacion/app_cliente.py`: no escribir huellas manualmente. Comprobar
  que anuncia la nueva versión y que los archivos `.viejo`, `.nuevo` y `.fallida` quedan excluidos.
- No cerrar la app ni reiniciar el servidor a ciegas: considerar trabajos en curso, audios
  pendientes y cambios sin guardar. El servidor recalcula el manifiesto sin reinicio;
  las PC instalan cuando están libres. Si cambió código Python, distinguir archivo actualizado
  de proceso reiniciado; coordinar cualquier reinicio que interrumpa trabajo.
- Al terminar un PR de trabajo, informar rama, commit, PR, pruebas ejecutadas y las notas agregadas.
- Al terminar una entrega, informar versiones, etiquetas, pruebas y resultado, ubicación del ejecutable y
  cualquier paso pendiente de reinicio o distribución. No afirmar que las PC ya se actualizaron sin
  comprobarlo. Si falta compilador o falla una prueba, dejarlo explícito y no publicar el binario.
