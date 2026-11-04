# Instrucciones persistentes del proyecto

## Antes de modificar

- Leer `docs/desarrollo.md` y, para escritorio, `docs/compilacion.md`.
- Revisar `git status` y conservar los cambios existentes del usuario.
- Esta carpeta es una instalación en uso: respaldar los archivos que se van a cambiar
  en `respaldo/respaldo_AAAAMMDD_HHMMSS_antes_de_<cambio>/` antes de editarlos.
- No usar datos de pacientes en pruebas. No versionar secretos, configuración local,
  informes, audios, registros ni binarios. No sobrescribir la configuración local con la de ejemplo.
- Hay un refactor por etapas en curso: antes de mover o reorganizar código, leer `docs/refactor.md`
  (reglas de cada PR, estructura destino y estado). Las decisiones de arquitectura van en `docs/adr/`.

## Ramas y orden de trabajo

El usuario exige una rama nueva para cada nueva tarea de cambios o mejoras, antes de editar.

- No desarrollar ni hacer commits directamente en `main`.
- Para una tarea nueva, consultar el remoto y partir de `main` actualizado mediante avance
  rápido, sin sobrescribir trabajo local. Si no hay acceso al remoto, explicitar esa limitación.
- Usar nombres breves en minúsculas con guiones y prefijo según el propósito:
  `feat/`, `fix/`, `refactor/`, `docs/`, `test/` o `chore/`. Ejemplo: `feat/atajos-editor`.
  Los experimentos usan `exp/` y parten de `experimental` (ver «Experimentos»).
- Una rama por objetivo coherente. Los ajustes y correcciones de la misma tarea continúan
  en su rama; una tarea distinta comienza en otra. No reutilizar una rama ya integrada.
- Revisar el estado antes de cambiar de rama; no arrastrar cambios ajenos, descartarlos,
  usar `reset --hard` ni reescribir historial compartido. Conservar siempre el trabajo existente.
- Mantener commits pequeños y coherentes con Conventional Commits en español; incluir
  versiones, documentación y pruebas correspondientes a la entrega.
- Al pedir el usuario subir cambios, publicar la rama con seguimiento remoto y preparar
  un pull request hacia `main`. Integrar mediante PR tras las comprobaciones, sin push
  directo a `main`, salvo instrucción explícita del usuario que autorice esa excepción.
- No interpretar «subir a GitHub» como autorización para fusionar el PR. No eliminar ramas
  con trabajo pendiente. Al terminar, indicar rama, commit y PR si se publicó.

## Experimentos

Guía completa: `docs/experimentos.md`.

- Los cambios de prueba, que quizá no lleguen a la versión final, van en `exp/<tema>` creada
  desde `experimental`, con PR hacia `experimental` (nunca hacia `main`). `test/` no es para esto.
- `experimental` es permanente y nunca se fusiona entera en `main`. Para incluir un experimento,
  crear `feat/<tema>` desde `main`, traer los commits (`cherry-pick` o rehacerlos) y completar
  versiones, CHANGELOG, documentación y pruebas como en cualquier entrega.
- En `exp/` y `experimental` no subir `Programa.VERSION` ni `VERSION` del servidor: la versión
  se asigna al promover. No distribuir a las PC del trabajo binarios compilados desde esas ramas.
- No cambiar de rama en la instalación en uso para probar. Usar una copia creada con
  `python crear_entorno_pruebas.py` (otra carpeta, otro puerto, sin túnel, IA simulada por defecto).
  La IA real de esa copia comparte GPU y Ollama con producción: solo sin trabajo en curso.

## Versiones: parte obligatoria del trabajo

El usuario pidió que estos pasos se hagan sin tener que recordarlos en cada cambio.
No dar por terminado un cambio funcional hasta completar su versión, documentación y validación.

- App de escritorio: incrementar `Programa.VERSION`, `AssemblyVersion` y `AssemblyFileVersion`
  en `cliente_codigo/Programa.cs`, juntos. Mantener el esquema existente (1.15 → 1.16).
  Revisar si el cambio rompe compatibilidad y requiere otra versión mayor.
- Los cambios de la página principal (`web/index.html`, `web/js/principal/`, `web/css/principal/`)
  que se usan en la app también requieren nueva versión
  de escritorio, aunque no cambie C#. No alcanza con cambiar la versión del servidor.
- Servidor: al cambiar su comportamiento, APIs, procesamiento o páginas servidas, incrementar
  `VERSION` en `servidor.py` con el esquema existente `AAAA.MM.N`, usando la fecha de
  Buenos Aires y un correlativo creciente dentro del mes. Una interfaz compartida requiere
  subir ambas versiones. No modificar versiones históricas ni reutilizar una versión publicada.
- Agrupar los cambios de una misma entrega en una versión; no incrementar por cada archivo
  ni por una corrección previa a publicar. Solo documentación, pruebas o herramientas de
  desarrollo sin cambios funcionales no requieren subir la versión de la aplicación.
- Actualizar la versión actual y la fecha en `cliente/LEEME.txt`; agregar entradas fechadas
  de App y/o Servidor al `CHANGELOG.md`, describiendo el resultado real de los cambios.
  Pasar a la entrada publicada las notas correspondientes de «Sin publicar» al cerrar
  esa entrega; conservar allí solo trabajo que realmente siga pendiente.
- Actualizar README y documentación afectada: atajos, ayuda, instalación, configuración,
  dependencias y compatibilidad según corresponda. Revisar pantallas que comparten estilos.
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
- Ejecutar `python verificar_versiones.py` en esta instalación. Verifica código, documentación,
  ejecutable y manifiesto. En un checkout sin binarios usar explícitamente `--sin-binario`;
  esa modalidad no confirma una distribución lista.
- Revisar `git diff --check`, el diff y `git status`. Los binarios son distribución local,
  no archivos para Git. No incluir datos clínicos o secretos en commits ni salidas.
- El manifiesto lo calcula `transcripcion/operacion/app_cliente.py`: no escribir huellas manualmente. Comprobar
  que anuncia la nueva versión y que los archivos `.viejo`, `.nuevo` y `.fallida` quedan excluidos.
- No cerrar la app ni reiniciar el servidor a ciegas: considerar trabajos en curso, audios
  pendientes y cambios sin guardar. El servidor recalcula el manifiesto sin reinicio;
  las PC instalan cuando están libres. Si cambió código Python, distinguir archivo actualizado
  de proceso reiniciado; coordinar cualquier reinicio que interrumpa trabajo.
- Al finalizar informar versión(es), pruebas ejecutadas y resultado, ubicación del ejecutable,
  y cualquier paso pendiente de reinicio o distribución. No afirmar que las PC ya se actualizaron
  sin comprobarlo. Si falta compilador o falla una prueba, dejarlo explícito y no publicar el binario.
