# Segunda etapa: CI y listado de casos — 29/10/2026

Los cambios se agrupan en el candidato todavía no distribuido App **1.22** / Servidor
**2026.10.46**, junto con la primera etapa de persistencia. No se reutiliza una versión publicada.

## Implementado

- `.github/workflows/ci.yml`: integración Windows/Python 3.12 en PR y push a main/master;
  despacho manual para generar un artefacto con fuentes y cliente probado, identificado por commit.
- Pruebas Python, sintaxis JS, versiones, navegador Edge, cola DPAPI, compilación .NET y autoprueba.
- Dependencias CPU de ensayo fijadas y lock npm para Playwright. No se modifica el entorno GPU real.
- Actions fijadas por SHA completo, permisos de lectura, timeout y cancelación de CI obsoleto.
- Distribución del candidato mediante artefacto con lista explícita y retención de 14 días.
  No hay credenciales ni acceso al servidor real; el workflow no reinicia esta instalación.

La activación remota requiere subir el código a GitHub y configurar protección de rama/checks
obligatorios. No se ejecutó GitHub Actions ni se modificaron ajustes remotos en esta entrega.
El despliegue final sigue siendo una promoción coordinada, según [ci-cd.md](ci-cd.md).
Quedan pendientes matriz Linux/otras versiones Python, firma de distribución, hashes del entorno
Python, evaluación GPU y despliegue automático con drenaje/rollback probado.

## Listado

`indice_casos.py` reutiliza metadatos por caso mientras coincidan tamaño y mtime de sus archivos;
incluye la firma global de las muestras de voz y la ruta del directorio de datos. Un cambio de
médico, paciente, informe, marcas, borrador u omisiones invalida la entrada del caso. Los casos
borrados se eliminan de la caché. Se inventarían archivos con `os.scandir` para aprovechar sus
metadatos; el recorrido de directorios continúa para detectar modificaciones externas.

No se cachean bloqueos, permisos, estado del procesamiento, pausa ni espera. Se calculan por
pedido para no mostrar autorización vieja a otra PC. `/api/cliente/estado` usa un solo listado
para sus casos y contador de cola. La web comparte una consulta activa entre llamadas de timer
y acciones del usuario; no acumula pedidos cuando la red tarda.

El índice sigue teniendo costo proporcional al número de archivos. No agrega paginación,
notificaciones push ni virtualización de filas. Modificaciones externas que preservan exactamente
tamaño y mtime pueden no invalidarlo; las escrituras normales de la aplicación cambian su firma.

## Medición y comprobación

`python pruebas/medir_listado.py`, cinco repeticiones tras la primera lectura, datos ficticios:

| Casos | Mediana anterior registrada | Mediana con índice | Máximo con índice |
|---:|---:|---:|---:|
| 100 | 108,9 ms | 21,9 ms | 22,9 ms |
| 1.000 | 1.151,1 ms | 252,7 ms | 258,0 ms |

La reducción observada para 1.000 casos es aproximadamente 78 %. Se compara con la medición
registrada en la auditoría, en el mismo equipo y fixture; no es un ensayo controlado de carga
de producción. No incluye red, serialización ni DOM. Primera lectura de 1.000 casos: 5.156,5 ms;
la mejora principal corresponde a las consultas posteriores.

Validación: 24 pruebas Python aprobadas, incluyendo cambio de metadatos, borrado y permisos
frescos. Cuatro scripts de navegador aprobados, con prueba de pedidos de lista simultáneos.
Se comprobó instalación desde cero de `requirements-ci.txt` y `npm ci` en staging; sus pruebas
también pasaron. YAML parseado, sintaxis de fuentes y `git diff --check` correctos.

Compilación con `compilar.ps1 -SoloCompilar`: autoprueba de 390 métodos OK. Persisten las dos
advertencias previas CS4014 de notificaciones en segundo plano, fuera del cambio de listado.
El candidato está en `respaldo/compilacion_20261029_204011_067/Transcripcion.exe`.
Ensayo: `respaldo/ci_listado_pruebas/sistema`. Respaldo previo:
`respaldo/respaldo_20261029_203710_antes_de_ci_listado`.

El ejecutable distribuido sigue siendo 1.21 y el servidor en uso no fue reiniciado. Por eso el
verificador completo en producción detecta la diferencia intencional entre fuentes y ejecutable;
staging se valida con el candidato. Las páginas abiertas conservan el JS ya cargado; una apertura
nueva toma los archivos web nuevos. La optimización Python requiere iniciar el proceso nuevo
en una ventana coordinada. No se afirma que las PC remotas estén actualizadas.
