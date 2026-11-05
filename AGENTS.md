# Instrucciones persistentes del proyecto

Detalle en `docs/` (índice `docs/README.md`): consultar solo la guía del área que se toca —
`desarrollo.md` (pruebas, convenciones), `compilacion.md` (app de Windows), `versiones.md` (entregas),
`arquitectura.md` (estructura). El refactor por etapas terminó; `docs/refactor.md` y `docs/historial/` son historia.

## Antes de modificar

- Revisar `git status` y conservar los cambios existentes del usuario.
- Esta carpeta es una instalación en uso: respaldar los archivos que se van a cambiar
  en `respaldo/respaldo_AAAAMMDD_HHMMSS_antes_de_<cambio>/` antes de editarlos.
- No usar datos de pacientes en pruebas. No versionar secretos, configuración local, informes, audios,
  registros ni binarios. No sobrescribir la configuración local con la de ejemplo.
- Decisiones de arquitectura nuevas: un ADR en `docs/adr/`.

## Qué significa cada pedido

| El usuario dice | Hacer | No hacer |
|---|---|---|
| «subí a GitHub», «subí los cambios» | Publicar la rama y abrir un PR hacia `main` | Fusionar, crear etiquetas ni preparar una entrega |
| «sacá versión», «publicá», «distribuí», «hacé la entrega» | Preparar una entrega (`docs/versiones.md`) | Subir versiones en una rama de trabajo |
| «fusioná», «mergeá» | Fusionar el PR indicado | Crear etiquetas si no lo pidió |

Sin uno de estos pedidos no se abre PR. Si no está claro cuál es, preguntar antes de actuar.

## Ramas

- Una rama nueva por tarea, antes de editar, desde `main` actualizado por avance rápido (si no hay acceso al
  remoto, decirlo). Nunca commits en `main` ni push directo a `main` sin autorización explícita.
- Prefijos: `feat/`, `fix/`, `refactor/`, `perf/`, `docs/`, `test/`, `chore/`; entregas `release/`;
  experimentos `exp/` desde `experimental`. Nombres breves en minúsculas con guiones.
- Ajustes de la misma tarea siguen en su rama; no reutilizar una rama ya integrada ni borrar ramas con trabajo.
- No arrastrar cambios ajenos, descartarlos, usar `reset --hard` ni reescribir historial compartido.
- Commits pequeños, Conventional Commits en español, con CHANGELOG, documentación y pruebas del cambio.

## Experimentos (`docs/experimentos.md`)

- `exp/<tema>` desde `experimental`, PR hacia `experimental`, nunca hacia `main`. `experimental` nunca se fusiona
  entera en `main`: se promueve con `feat/<tema>` desde `main` + cherry-pick y notas completas.
- En `exp/` y `experimental`: sin versiones ni notas de «Sin publicar», y sin distribuir binarios a las PC.
- No cambiar de rama en la instalación en uso: probar en la copia de `python scripts/crear_entorno_pruebas.py`
  (su IA real comparte GPU y Ollama con producción: solo sin trabajo en curso).

## Versiones (`docs/versiones.md`, ADR 0002)

Un número por entrega, no por PR. Se hace sin que el usuario tenga que recordarlo.
- En un PR de trabajo no tocar `Programa.VERSION`, `AssemblyVersion`, `AssemblyFileVersion` ni `VERSION` de
  `servidor.py`. Todo cambio funcional deja su nota en `CHANGELOG.md` → «Sin publicar», bajo `### App` y/o
  `### Servidor`, categoría `####` (Agregado, Cambiado, Corregido, Quitado, Interno) e issue (`#NN`), escrita
  para quien usa el sistema. La página principal (`web/index.html`, `web/js/principal/`, `web/css/principal/`)
  lleva nota en App y en Servidor. Refactor con contratos en verde: «Interno». Solo docs, pruebas, CI o
  herramientas: sin nota.
- En el PR, decir qué componente afecta y si exige versión mínima del otro («Requiere Servidor ≥ …»).
- Entregas: solo cuando el usuario lo pide, con `herramientas/subir_version.py` (nunca números a mano) y las
  etiquetas anotadas `app-vX` / `servidor-vY` solo con autorización (nunca mover ni reutilizar una etiqueta
  ni un número publicado). Pasos y tabla de qué número subir en `docs/versiones.md`.

## Documentación

- Actualizar README y docs afectados (atajos, ayuda, instalación, configuración, compatibilidad).
- No escribir la versión actual en la documentación («desde la versión X» sí).
- Opciones nuevas: `configuracion.ejemplo.json` y valores predeterminados compatibles con lo guardado. Si cambia un
  formato persistido o protocolo: consumidores, migración y convivencia con clientes anteriores.

## Verificar

- Pruebas pertinentes al cambio (Python, JS, Word, interfaz simulada, Windows); no reemplazarlas por chequear versiones.
- Los contratos `pruebas/test_contrato_http.py` y `test_contrato_nucleo.py` fijan el comportamiento: un refactor
  nunca los regenera; un cambio funcional deliberado regenera el del núcleo (`ACTUALIZAR_CONTRATOS=1`) y explica el diff.
- `python -m ruff check .`, `python herramientas/verificar_versiones.py --sin-binario`, `git diff --check`, revisar diff y
  `git status` (sin datos clínicos, secretos ni binarios).
- App de Windows: `cliente_codigo/compilar.ps1` (autoprueba antes de reemplazar el exe) o Mono según
  `docs/compilacion.md`. El manifiesto lo calcula `transcripcion/operacion/app_cliente.py`: no escribir huellas.
- No cerrar la app ni reiniciar el servidor a ciegas (trabajos en curso, audios pendientes, cambios sin guardar).
  Distinguir archivo actualizado de proceso reiniciado y de PC efectivamente actualizada.

## Al terminar

- PR de trabajo: rama, commit, PR si se publicó, pruebas corridas y notas agregadas.
- Entrega: versiones, etiquetas, pruebas, ubicación del ejecutable y pasos pendientes de reinicio o distribución.
  Si falta compilador o falla una prueba, decirlo y no publicar el binario.
