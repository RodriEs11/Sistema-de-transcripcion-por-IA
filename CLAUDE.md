# CLAUDE.md

Reglas del proyecto (ramas, versiones, entregas, pruebas): @AGENTS.md

## Ahorrar contexto
- Leer solo los archivos de la tarea. Usar este mapa y `grep` en lugar de recorrer carpetas.
- No leer enteros `CHANGELOG.md` ni `docs/refactor.md` (buscar la sección con `grep`). `docs/historial/` es historia: no hace falta.
- No abrir `package-lock.json`, binarios, `cliente/` ni `respaldo/`.
- Correr solo las pruebas del área tocada; la suite completa, antes de publicar.
- Respuestas cortas: qué cambió, pruebas corridas, qué falta. Sin repetir el plan.
- No abrir PR hasta que el usuario lo pida.

## Mapa
- Entradas en la raíz: `servidor.py` (configurar + main), `informe.py`, lanzadores `aprender.py` e `importar_informes.py`, `.bat`/`.sh`.
- `transcripcion/` (no importa nada de la raíz; `transcripcion.RAIZ` = carpeta del sistema):
  - `http/` rutas: `tabla.py` (todas), una función por ruta en `casos`, `edicion`, `audios`, `panel*`, `acceso`, `cliente`, `conocimiento`, `voces`, `usuario`, `paginas`.
  - `casos/` (repositorio `Casos`, vista, borrado, borradores, paciente, índice) · `procesamiento/` (estado, cola SQLite, lotes, caché, trabajador).
  - `asr/` (whisper, huecos) · `texto/` (normalización) · `ia/` (prompt, ejemplos, ollama) · `controles/` (marcas, clínicos, avisos, orden).
  - `conocimiento/` (plantillas, médicos, importar) · `informe/` (formato, word, guardado) · `aprendizaje/` · `voz/` · `acceso/` (usuarios, remoto, admin) · `operacion/` (ia, reinicio, mantenimiento, estadísticas, app_cliente, gpu) · `base/` (plataforma, persistencia, registro, formatos).
- Página principal: `web/index.html` + `web/js/principal/NNN-area.js` y `web/css/principal/` (el servidor los une; funciones globales, sin nombres repetidos). Panel: `web/admin.html`, `estadisticas.html`, `medicos.html`, `correcciones.html`.
- App de escritorio: `cliente_codigo/` (C# .NET 4.8 + WebView2, `VentanaPrincipal.<Parte>.cs`).
- `scripts/` operación · `herramientas/` desarrollo y versiones · `pruebas/` · `docs/` (índice `docs/README.md`).

## Comandos
```
python -m unittest pruebas.test_<area>                      # pruebas de un área
python -m unittest discover -s pruebas -p 'test_*.py'      # todas
python -m ruff check . && python -m ruff format transcripcion && python -m mypy
node pruebas/verificar_fuentes.cjs                          # página principal
python herramientas/verificar_versiones.py --sin-binario
```
