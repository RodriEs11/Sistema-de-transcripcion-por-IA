# Instrucciones persistentes del proyecto

## Antes de modificar

- Leer `docs/desarrollo.md` y, para escritorio, `docs/compilacion.md`.
- Revisar `git status` y conservar los cambios existentes del usuario.
- Esta carpeta es una instalación en uso: respaldar los archivos que se van a cambiar
  en `respaldo/respaldo_AAAAMMDD_HHMMSS_antes_de_<cambio>/` antes de editarlos.
- No usar datos de pacientes en pruebas. No versionar secretos, configuración local,
  informes, audios, registros ni binarios. No sobrescribir la configuración local con la de ejemplo.

## Versiones: parte obligatoria del trabajo

El usuario pidió que estos pasos se hagan sin tener que recordarlos en cada cambio.
No dar por terminado un cambio funcional hasta completar su versión, documentación y validación.

- App de escritorio: incrementar `Programa.VERSION`, `AssemblyVersion` y `AssemblyFileVersion`
  en `cliente_codigo/Programa.cs`, juntos. Mantener el esquema existente (1.15 → 1.16).
  Revisar si el cambio rompe compatibilidad y requiere otra versión mayor.
- Los cambios de `web/index.html` que se usan en la app también requieren nueva versión
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
- El manifiesto lo calcula `app_cliente.py`: no escribir huellas manualmente. Comprobar
  que anuncia la nueva versión y que los archivos `.viejo`, `.nuevo` y `.fallida` quedan excluidos.
- No cerrar la app ni reiniciar el servidor a ciegas: considerar trabajos en curso, audios
  pendientes y cambios sin guardar. El servidor recalcula el manifiesto sin reinicio;
  las PC instalan cuando están libres. Si cambió código Python, distinguir archivo actualizado
  de proceso reiniciado; coordinar cualquier reinicio que interrumpa trabajo.
- Al finalizar informar versión(es), pruebas ejecutadas y resultado, ubicación del ejecutable,
  y cualquier paso pendiente de reinicio o distribución. No afirmar que las PC ya se actualizaron
  sin comprobarlo. Si falta compilador o falla una prueba, dejarlo explícito y no publicar el binario.
