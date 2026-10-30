# Flujo recomendado de CI/CD

Diseño propuesto el 29/10/2026 para servidor Python + cliente .NET 4.8/WebView2.
**Estado:** implementado `.github/workflows/ci.yml` para Windows/Python 3.12: PR y push a
main/master ejecutan pruebas Python, navegador, cola nativa, compilación .NET y autoprueba.
Un despacho manual agrega la entrega del candidato probado como artefacto por commit (14 días).
Las Actions están fijadas por SHA; el job solo tiene lectura del repositorio y no accede a producción.
La ejecución remota y los checks obligatorios requieren publicar estos archivos y configurar GitHub;
no se activaron remotamente desde esta instalación. Las secciones siguientes mantienen la hoja de
ruta para ampliar plataformas, evaluación GPU y promoción final a producción.
Ver [auditoría de rendimiento](auditoria-rendimiento-2026-10-29.md).

## Desarrollo y revisión

Trabajar en checkout separado de la instalación utilizada por las personas. Rama corta por
cambio, PR pequeño y revisión de evidencia. Conservar `main` publicable; usar un commit o tag
inmutable para identificar cada candidato. Evitar desarrollar o ejecutar CI sobre datos reales.
Mantener las reglas de [AGENTS.md](../AGENTS.md) y los respaldos locales obligatorios.

Cada PR debe describir problema, comportamiento final, compatibilidad, pruebas, mediciones y
rollback. Si toca interfaz compartida, subir versión App y Servidor juntas; documentación y
herramientas sin cambios funcionales no necesitan incremento. Revisar CHANGELOG y LEEME.

## Puertas de integración

| Puerta | Entorno | Qué debe bloquear el merge |
|---|---|---|
| Higiene | Checkout limpio | `git diff --check`, secretos/datos prohibidos versionados, Python/JS inválidos, funciones globales duplicadas, versiones incoherentes |
| Python | Windows y Linux; empezar por Python 3.12 | `unittest discover`, Word y APIs ficticias; agregar contratos de casos, bloqueos, cola, rangos, persistencia y errores |
| Navegador | Edge Windows; Chromium Linux como segundo objetivo | Los tres scripts de `pruebas/`, errores de página y regresiones de selección/pegado/autoguardado |
| Escritorio | Windows .NET Framework 4.8 | Compilación, versión PE y `--autoprueba`; no aceptar solo compilación Mono |
| Rendimiento | Runner estable separado | Regresiones contra línea base; listado, edición, memoria y guardado con fixtures sintéticos |
| IA | Equipo GPU de ensayo, separado de producción | Calidad y latencia por duración/carga; obligatorio al cambiar modelos, prompt, recuperación de huecos o controles |

La compatibilidad declarada con Python 3.10–3.13 exige ampliar la matriz o reducir explícitamente
el rango documentado. No interpretar un pase en 3.12 como validación de todas las versiones.
Agregar pruebas de convivencia cliente actual/anterior y servidor actual/candidato para APIs y
formatos persistidos. Los checks requeridos deben ejecutarse incluso en PR de documentación;
los trabajos pesados pueden decidir internamente si aplica su ejecución.

## Entornos reproducibles

Hoy `requirements.txt` es una especificación amplia, no un lock. Crear locks verificados por
plataforma/Python, con hashes; separar dependencias de runtime, pruebas CPU y stack GPU.
Mantener versiones compatibles de faster-whisper, CTranslate2, CUDA/cuDNN y PyAV; registrar
driver y modelo/digest en los benchmarks de IA. No actualizar paquetes automáticamente en
producción ni congelar a ciegas el entorno local, que puede contener dependencias ajenas.

Se agregaron `package.json`/lock para Playwright 1.56.1; instalar con `npm ci`.
La aplicación puede seguir siendo HTML/JS sin build: estas dependencias son de desarrollo.
Fijar SDK .NET y dependencias NuGet. La versión WebView2 del csproj ya es explícita.
Cachear paquetes por lock/plataforma; nunca carpetas clínicas, secretos ni salidas de producción.

## Comandos actuales aprovechables

En un checkout de ensayo con dependencias instaladas y configuración de ejemplo:

```powershell
python -m unittest discover -s pruebas -p 'test_*.py' -v
python verificar_versiones.py --sin-binario
node pruebas/editor_word.cjs
node pruebas/revision_word.cjs
node pruebas/medicos.cjs
python pruebas/medir_listado.py --casos 100 1000 --repeticiones 5
```

Los scripts del navegador usan `PLAYWRIGHT_MODULE` opcional y `BROWSER_CHANNEL` (por defecto
`msedge`). `medicos.cjs` acepta `PYTHON` y necesita `respaldo/` existente. Crear esa carpeta antes
de ejecutarlo. No depender de que otra prueba la haya creado. En Linux elegir explícitamente
un canal instalado y validar ese job; no asumir que Edge está disponible.

`test_medicos.py` importa el servidor, que carga configuración y crea carpetas; parchear solo
el catálogo de médicos no aísla toda la instalación. Por eso ejecutar estas pruebas en checkout
limpio con carpetas de datos ficticias bajo la raíz de ensayo. El nuevo microbenchmark realiza
su propio aislamiento y no inicia HTTP ni modelos.

La comprobación de sintaxis Python debe enumerar archivos explícitamente (PowerShell no expande
`*.py` para todos los ejecutables). Para JS verificar scripts externos y extraer los inline de
HTML; `node --check index.html` no sustituye ese paso. La detección de duplicados debe cubrir
el espacio global compartido entre `index.html` y `editor_word.js`, además de cada página.

## Compilar una vez y promover el mismo artefacto

En Windows CI limpio, restaurar NuGet y compilar `cliente_codigo/Transcripcion.csproj` en Release.
Ejecutar `--autoprueba` sobre el candidato con las DLL requeridas y timeout; reunir ejecutable,
config y runtimes en staging. `compilar.ps1` necesita DLL locales en `cliente/`, que no están
versionadas: su uso en CI requiere prepararlas desde dependencias verificadas.

En esta instalación, el camino vigente es:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File cliente_codigo/compilar.ps1 -SoloCompilar
```

Ese comando valida un candidato sin distribuirlo. El flujo futuro de promoción debe instalar
**ese candidato probado**, sin recompilarlo; el script actual sin `-SoloCompilar` compila de nuevo
y distribuye, por lo que necesita un paso adicional de promoción para ese flujo futuro.
Después de instalar en staging/servidor, ejecutar `python verificar_versiones.py` sin omitir binario.
El manifiesto siempre lo calcula `app_cliente.py`, nunca se escriben hashes manualmente.

Guardar metadatos de release: commit, versiones, locks, compilador, resultados de pruebas,
SHA-256 y compatibilidad de esquema/API. Publicar paquetes con lista explícita de archivos;
no comprimir el workspace entero. Excluir `conexion.json` de artefactos públicos y conservar
configuración local fuera del paquete. Evaluar firma del ejecutable y del manifiesto: un hash
verifica integridad, pero por sí solo no identifica al editor de una distribución comprometida.

## Promoción y recuperación

La [preparación local 1.22/2026.10.46](activacion-coordinada.md) genera candidato/rollback con
SHA-256 y respaldos privados separados. Su verificador detecta alteraciones y archivos extra;
no autoriza por sí solo a activar. Las condiciones de PC y servidor se repiten durante la ventana.

1. Integración aprobada → candidato inmutable → staging aislado con datos ficticios.
2. Prueba de abrir caso, reproducir, editar, guardar Word, desconectar/reconectar y actualizar app.
3. Ensayo de recuperación de servidor/cliente y de migración de datos, si aplica.
4. Autorizar promoción de la entrega concreta; verificar trabajos activos, ediciones y audios pendientes.
5. Respaldar fuentes/configuración/datos necesarios de forma consistente; drenar cola y coordinar
   reinicio Python. No matar procesos ni perder ediciones por un push a `main`.
6. Desplegar código y conjunto de cliente consistente; verificar versiones/manifiesto y salud.
7. Piloto en una PC de ensayo; observar errores, guardado y latencias antes del resto.
8. Registrar por separado versión publicada, proceso servidor reiniciado y PC que confirmó instalación.

El actualizador actual ofrece la carpeta `cliente/` a todas las PC; **no implementa canales de
canary**. El piloto necesita distribución de ensayo separada o agregar soporte explícito de canales.
La automatización de reinicio existente coordina trabajo, pero no reemplaza un despliegue
transaccional ni el ensayo de cortes abruptos.

Rollback: detener promoción, conservar cola/borradores, recuperar artefacto anterior compatible y
reiniciar solo tras coordinación. Si cambió esquema, usar migración inversa ensayada o restauración
consistente sin borrar trabajo nuevo. Nunca restaurar datos antiguos automáticamente sobre datos
generados después del despliegue. Conservar historial de artefactos y respaldos con retención definida.

## Configuración de GitHub pendiente

El workflow implementa PR/main/master y candidato por despacho manual; falta configurar checks
requeridos y protección de rama. Usar permisos mínimos, Actions fijadas por SHA completo y
timeouts. No dar secretos ni acceso al servidor real a PR de forks. Evitar ejecutar código no
confiable en un runner persistente conectado a datos reales.
[Guía oficial de seguridad de Actions](https://docs.github.com/en/actions/reference/security/secure-use).

Cancelar ejecuciones CI obsoletas de una rama; serializar despliegues y no cancelarlos a mitad
de una promoción. Usar environments y revisores si el plan/tipo de repositorio lo permite;
confirmar disponibilidad antes de depender de esa barrera.
[Entornos de despliegue](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments).

Subir únicamente resultados sintéticos y reportes de pruebas con retención acotada. Mantener
trazas, métricas y alarmas sin contenido clínico. Avisar por fallo de publicación o cambio de salud,
con procedimiento de recuperación y responsable. Medir tasa de entregas fallidas y tiempo de
recuperación además de duración de CI.

## Criterio de entrega terminada

Fuentes y documentación coherentes, checks aprobados, candidato reproducible probado en Windows,
mediciones comparables, rollback ensayado y confirmación del estado real del despliegue.
CI verde no prueba que la GPU funcione ni que todas las PC hayan instalado una versión.
Las primeras entregas deberían automatizar CI y staging; mantener promoción a producción
controlada hasta contar con esas garantías.
