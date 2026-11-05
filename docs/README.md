# Documentación

Versiones actuales: [CHANGELOG](../CHANGELOG.md) y el panel. Cómo se numeran y entregan: [versiones.md](versiones.md).

| Documento | Para quién | Contenido |
|---|---|---|
| [arquitectura.md](arquitectura.md) | Desarrollo | Componentes, flujo de un audio, GPU, concurrencia y archivos de un caso |
| [instalacion.md](instalacion.md) | Instalación | Servidor, acceso remoto y PC del trabajo |
| [linux.md](linux.md) | Instalación | Servidor en Linux: scripts, servicio y diferencias con Windows |
| [uso.md](uso.md) | Usuarios | Flujo de revisión, atajos y marcas |
| [pipeline.md](pipeline.md) | Desarrollo | Whisper, prompt, controles, aprendizaje y evaluación |
| [voz.md](voz.md) | Usuarios / Desarrollo | Médico reconocido por la voz: cómo funciona, pantallas, ajustes y API |
| [configuracion.md](configuracion.md) | Administración | `configuracion.json`, plantillas, reglas, médicos, vocabulario |
| [acceso-remoto.md](acceso-remoto.md) | Administración / Desarrollo | Túnel, autenticación, app del trabajo y actualizaciones |
| [compilacion.md](compilacion.md) | Desarrollo | Compilar, verificar y publicar la app de Windows |
| [versiones.md](versiones.md) | Desarrollo / Operación | Esquemas de versión, notas en «Sin publicar», preparar y activar una entrega, etiquetas |
| [administracion.md](administracion.md) | Administración | Panel, estadísticas, registros y borrado |
| [api.md](api.md) | Desarrollo | Rutas HTTP del servidor |
| [seguridad.md](seguridad.md) | Todos | Datos, amenazas y protecciones |
| [desarrollo.md](desarrollo.md) | Desarrollo | Modo simulado, convenciones y lecciones aprendidas |
| [usuarios.md](usuarios.md) | Usuarios / Administración / Desarrollo | Transcriptores: usuario, contraseña y estilo propio de cada uno (Servidor 2026.11.1 · App 1.23) |
| [refactor.md](refactor.md) | Desarrollo | Refactor por etapas (terminado el 03/11/2026): estructura, reglas y qué quedó de cada etapa — histórico |
| [adr/](adr/README.md) | Desarrollo | Registro de decisiones de arquitectura (ADR) y su plantilla |
| [experimentos.md](experimentos.md) | Desarrollo | Rama `experimental`, ramas `exp/`, promoción a `main` y entorno de pruebas aislado |
| [issues.md](issues.md) | Desarrollo | Plantillas de issues (bug, característica, UX, paraguas), etiquetas y orden de trabajo |
| [ci-cd.md](ci-cd.md) | Desarrollo / Operación | Workflow de CI implementado (`.github/workflows/ci.yml`) y hoja de ruta de staging, promoción y recuperación |
| [persistencia.md](persistencia.md) | Desarrollo / Operación | Etapa 1: borradores confirmados, cola cifrada, compatibilidad y promoción pendiente |
| [editor-audio.md](editor-audio.md) | Desarrollo | Etapa 3: paginación parcial del editor A4 y reproducción de audio más liviana |
| [word-aprendizaje.md](word-aprendizaje.md) | Desarrollo / Operación | Etapa 4: guardado atómico del Word y cola persistente de aprendizaje en segundo plano |
| [aprendizaje-incremental.md](aprendizaje-incremental.md) | Desarrollo / Operación | Etapa 5: correcciones incrementales e historial indexado en SQLite |
| [ia-lotes.md](ia-lotes.md) | Desarrollo / Operación | Etapa 6: lotes FIFO de IA, caché de transcripción y métricas por caso |
| [cola-servidor.md](cola-servidor.md) | Desarrollo / Operación | Cola SQLite de procesamiento, recuperación tras caídas, pausas y respaldos verificables |

## Historial

Documentos de trabajo ya cerrados. No hace falta leerlos para trabajar en el código.

| Documento | Contenido |
|---|---|
| [auditoria-rendimiento-2026-10-29.md](historial/auditoria-rendimiento-2026-10-29.md) | Mediciones sintéticas, 19 hallazgos, prioridades y criterios de rendimiento |
| [ci-listado.md](historial/ci-listado.md) | Etapa 2: CI en Windows e índice del listado de casos |
| [activacion-coordinada.md](historial/activacion-coordinada.md) | Entrega congelada, piloto pc-test, ventana sin trabajo, controles y rollback ensayado |
| [validacion-gpu.md](historial/validacion-gpu.md) | Medición real de lotes 1/2/4, aislamiento, límites y configuración recomendada |
| [comparacion-cpu-gpu.md](historial/comparacion-cpu-gpu.md) | Herramienta opcional para comparar Whisper GPU + Gemma CPU en paralelo con los lotes actuales |
