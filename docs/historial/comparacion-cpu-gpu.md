# Comparación de Whisper GPU y Gemma CPU en paralelo

Ensayo manual solicitado el 30/10/2026, Buenos Aires. No cambia la configuración
de uso, no reemplaza ejecutables y no requiere una nueva versión de aplicación.

## Protocolo

- Mismos cuatro dictados ficticios de la [campaña anterior](validacion-gpu.md),
  con validación del texto conocido y SHA-256 de cada WAV antes de copiarlos.
  Voz Microsoft Sabina Desktop, mono PCM16, 16 kHz; 157,89 segundos en total.
- Whisper large-v3, CUDA/float16, español, beam 5, VAD y reparación de huecos.
- Gemma `gemma4:12b`, misma cuantización instalada, contexto 12.288,
  temperatura 0,1, sin pensamiento, tres ejemplos ficticios fijos,
  marcado y detección de omisiones del código de la aplicación.
- **Actual:** dos lotes consecutivos de dos audios, transcripción y adaptación
  secuenciales por lote, liberando Whisper antes de cargar Gemma y viceversa.
  Coincide con los valores efectivos 2/180 de la configuración guardada.
- **Paralelo:** Whisper permanece en GPU durante los cuatro audios; Gemma se
  precarga en CPU mientras se carga Whisper y consume las transcripciones en
  orden, mientras Whisper continúa con el siguiente dictado. Un único consumidor
  de IA; no se ejecutan varias generaciones de Gemma simultáneamente.
- Orden de seis ensayos: actual/paralelo/paralelo/actual/actual/paralelo,
  tres repeticiones por opción. Cada ensayo empieza con los modelos descargados
  y un nuevo trabajador. Se conserva la caché de disco/SO; no son arranques
  completamente fríos. ASR se ejecuta siempre, sin reutilizar transcripciones.
- Se mide desde el comienzo de las cargas hasta cada informe con controles,
  tiempo total de la cola de cuatro, espera media, tokens/s de generación y
  solapamiento de los intervalos de ASR e IA. Las cargas concurrentes de la
  opción CPU están incluidas en la espera; no se ocultan precalentamientos.
- Daemons propios en 11435 (GPU) y 11436 (CPU), uno a la vez. El daemon CPU
  recibe `CUDA_VISIBLE_DEVICES=-1`, GPU AMD/Vulkan deshabilitadas y `num_gpu=0`
  en sus solicitudes. El trabajador comprueba Whisper CUDA y `size_vram=0`
  para Gemma CPU, además de conservar logs del dispositivo usado.

## Protección de la instalación

El servidor habitual puede continuar escuchando. Solo se autoriza carga cuando
la cola está vacía, no hay estudios abiertos ni tareas ASR/IA o pausas. Si Gemma
está cargado en la instancia habitual, se espera su liberación natural; no se le
envían solicitudes de descarga, generación o cambio de parámetros.

Durante la medición se consultan esos contadores y los modelos de la instancia
habitual aproximadamente cada segundo. Ante trabajo nuevo, API inaccesible o
un Python ajeno nuevo, se cancela exclusivamente el árbol del ensayo. Esta
vigilancia reduce la posibilidad de interferencia, pero no reserva los recursos
del SO ni elimina la carrera entre una llegada nueva y su detección.

Se copian solamente los módulos necesarios y `conocimiento.ejemplo/` a
`respaldo/comparacion_cpu_gpu_FECHA_HORA/`. Los casos, ejemplos aprendidos,
audios e informes reales no se usan como entradas. La API administrativa se
reduce en memoria a contadores; no se guardan sus nombres de casos ni registros.
Se compara la huella de `configuracion.json` antes/después, sin conservar su
contenido en los artefactos del ensayo. Al cerrar se comprueba el estado de
producción y la liberación de los puertos propios.

## Ejecución

Desde `sistema/`, con ventana libre y el corpus sintético previo disponible:

```powershell
.venv/Scripts/python.exe herramientas/comparar_cpu_gpu.py --ejecutar --corpus respaldo/gpu_real_20261029_213721
```

Sin `--ejecutar` solo muestra ayuda. No tiene modo de reanudación: una campaña
interrumpida conserva sus resultados parciales, pero no produce un resumen
completo. El máximo de espera por liberación natural es 1.200 segundos;
`--espera` permite acotarlo. No se deben iniciar otras tareas Python durante
la medición, porque la vigilancia las considera trabajo ajeno.

Las pruebas CPU de guardas/agregación se ejecutan **antes o después** de la
campaña, sin modelos:

```powershell
.venv/Scripts/python.exe -m unittest discover -s pruebas -p test_comparar_cpu_gpu.py -v
```

## Alcance

Compara los caminos de inferencia y controles con una cola inicial de cuatro
dictados. No arranca otro servidor de aplicación ni mide la interfaz, el túnel,
el reconocimiento del médico, Word, la selección de ejemplos reales o SQLite de
producción. No mide llegada continua, latencia de un único audio aislado ni una
cola indefinida con modelos permanentemente calientes. La voz sintética y los
controles automáticos no validan precisión clínica ni tiempo humano de revisión.

Los resultados se agregan únicamente cuando terminaron los seis ensayos, todos
tienen cuatro informes en orden y hubo solapamiento en la variante paralela.
Tres repeticiones por opción no permiten estimar percentiles de producción.
