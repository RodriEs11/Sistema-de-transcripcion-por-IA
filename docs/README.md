# Documentación

Versiones actuales: **Servidor 2026.10.47 · App 1.22**. La entrega App 1.22 / Servidor 2026.10.46
se documenta por etapas (persistencia, CI y listado, editor y audio, Word y aprendizaje, correcciones
incrementales, lotes de IA); su activación y piloto están en [activacion-coordinada.md](activacion-coordinada.md).

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
| [administracion.md](administracion.md) | Administración | Panel, estadísticas, registros y borrado |
| [api.md](api.md) | Desarrollo | Rutas HTTP del servidor |
| [seguridad.md](seguridad.md) | Todos | Datos, amenazas y protecciones |
| [desarrollo.md](desarrollo.md) | Desarrollo | Modo simulado, convenciones y lecciones aprendidas |
| [experimentos.md](experimentos.md) | Desarrollo | Rama `experimental`, ramas `exp/`, promoción a `main` y entorno de pruebas aislado |
| [auditoria-rendimiento-2026-10-29.md](auditoria-rendimiento-2026-10-29.md) | Desarrollo / Operación | Mediciones sintéticas, 19 hallazgos, prioridades y criterios de rendimiento |
| [ci-cd.md](ci-cd.md) | Desarrollo / Operación | Workflow de CI implementado (`.github/workflows/ci.yml`) y hoja de ruta de staging, promoción y recuperación |
| [persistencia.md](persistencia.md) | Desarrollo / Operación | Etapa 1: borradores confirmados, cola cifrada, compatibilidad y promoción pendiente |
| [ci-listado.md](ci-listado.md) | Desarrollo | Etapa 2: CI en Windows e índice del listado de casos |
| [editor-audio.md](editor-audio.md) | Desarrollo | Etapa 3: paginación parcial del editor A4 y reproducción de audio más liviana |
| [word-aprendizaje.md](word-aprendizaje.md) | Desarrollo / Operación | Etapa 4: guardado atómico del Word y cola persistente de aprendizaje en segundo plano |
| [aprendizaje-incremental.md](aprendizaje-incremental.md) | Desarrollo / Operación | Etapa 5: correcciones incrementales e historial indexado en SQLite |
| [ia-lotes.md](ia-lotes.md) | Desarrollo / Operación | Etapa 6: lotes FIFO de IA, caché de transcripción y métricas por caso |
| [cola-servidor.md](cola-servidor.md) | Desarrollo / Operación | Cola SQLite de procesamiento, recuperación tras caídas, pausas y respaldos verificables |
| [activacion-coordinada.md](activacion-coordinada.md) | Operación | Entrega congelada, piloto pc-test, ventana sin trabajo, controles y rollback ensayado |
| [validacion-gpu.md](validacion-gpu.md) | Desarrollo / Operación | Medición real de lotes 1/2/4, aislamiento, límites y configuración recomendada |
| [comparacion-cpu-gpu.md](comparacion-cpu-gpu.md) | Desarrollo | Herramienta opcional para comparar Whisper GPU + Gemma CPU en paralelo con los lotes actuales |
