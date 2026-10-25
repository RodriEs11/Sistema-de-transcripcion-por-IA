# Guía de desarrollo

## Entorno

```bat
instalar.bat                         :: crea .venv e instala requirements.txt
.venv\Scripts\activate
python servidor.py                   :: igual que interfaz.bat
python servidor.py --tunel           :: igual que iniciar_servidor.bat
python servidor.py --sin-navegador   :: no abre el navegador al iniciar
```

No hay dependencias de JavaScript: las páginas de `web/` son HTML + CSS + JS sin compilar.

## Modo simulado (sin GPU ni Ollama)

Permite probar la interfaz, el acceso remoto, la cola y el panel en cualquier PC (incluso Linux):

```bash
SIMULAR_IA=1 SIMULAR_DEMORA=2 python servidor.py --sin-navegador
```

| Variable | Efecto |
|---|---|
| `SIMULAR_IA=1` | No carga Whisper ni llama a Ollama: usa transcripciones y salidas grabadas |
| `SIMULAR_SIN_IA=1` | Hace de cuenta que Ollama está cerrado hasta que exista el archivo `_ia_vuelve` |
| `SIMULAR_HUECOS='[...]'` | Lista JSON de huecos a informar en cada transcripción |
| `SIMULAR_DEMORA=N` | Segundos de espera simulados en cada etapa |

Con `SIMULAR_IA=1`, para un audio `X.wav` el servidor lee:
- `resultados/fase1/json/X.json` → clave `con_vocab` (`{"texto": ..., "palabras": [...]}`), y
- `resultados/fase2/gemma4_12b/X.json` → clave `salida` (texto del informe).

Estas carpetas no se versionan (salen de audios reales); para pruebas hay que generar datos ficticios con esa estructura.
Para probar el túnel sin Cloudflare se puede reemplazar `cloudflared.exe` por un script que imprima una dirección
`https://….trycloudflare.com` y simular los encabezados `Cf-Ray` / `Cf-Connecting-Ip` en los pedidos.

## Convenciones de código

- **Idioma**: nombres, comentarios y mensajes en español rioplatense, como el resto del código y la interfaz.
- **Python**: biblioteca estándar siempre que se pueda; las únicas dependencias son las de `requirements.txt`.
  Todo lo que se muestra o registra pasa por `registro.py` (`L.ok/info/aviso/error`), nunca `print`.
- **Mensajes al usuario**: claros y sin jerga técnica (`mensaje_amigable`); el detalle técnico va al registro.
- **`web/index.html` es un solo script**: dos `function` con el mismo nombre no dan error, la última pisa a la
  primera. Antes de agregar funciones, verificar que no haya nombres repetidos (debe salir vacío):

  ```bash
  grep -oE "^\s*(async )?function [A-Za-z0-9_]+" web/index.html | sed -E 's/.*function //' | sort | uniq -d
  ```

- `admin.html` y `estadisticas.html` comparten estilos y utilidades copiados: si se cambia el aspecto de una, revisar la otra.
- **App de Windows**: respetar las reglas de [compilacion.md](compilacion.md#métodos-prohibidos).
- **Respaldos locales**: antes de modificar archivos en la instalación en uso, copiarlos a
  `respaldo/respaldo_AAAAMMDD_antes_de_<cambio>/` (no versionado).

## Commits

Se usa [Conventional Commits](https://www.conventionalcommits.org/es/v1.0.0/) en español:

```
<tipo>(<ámbito>): <resumen en imperativo, minúscula, sin punto>

<cuerpo opcional: qué cambia y por qué>
```

| Tipo | Uso |
|---|---|
| `feat` | Funcionalidad nueva |
| `fix` | Corrección de un error |
| `docs` | Solo documentación |
| `refactor` | Cambio de código sin cambiar el comportamiento |
| `perf` | Mejora de rendimiento |
| `test` | Pruebas |
| `build` | Compilación, dependencias, scripts de instalación |
| `chore` | Mantenimiento del repositorio |

Ámbitos habituales: `transcripcion`, `ia`, `informe`, `aprendizaje`, `servidor`, `interfaz`, `remoto`, `admin`, `cliente`.

Ejemplo: `fix(cliente): reemplazar TrimEnd(char) por la sobrecarga de .NET 4.8`.

## Checklist antes de publicar un cambio

- [ ] `python -m py_compile *.py` sin errores.
- [ ] Sin funciones repetidas en `web/index.html`.
- [ ] Probado en modo simulado (y en la PC real si toca Whisper, Ollama o Windows).
- [ ] Si cambió la app: versión subida, API revisada contra .NET 4.8, autoprueba OK ([compilacion.md](compilacion.md)).
- [ ] `git status` sin datos de pacientes, secretos ni binarios.
- [ ] CHANGELOG actualizado.

## Lecciones aprendidas

| Problema | Solución |
|---|---|
| PyAV 16 rompe faster-whisper | Lector WAV propio y `av<16` |
| Un audio usado como su propio ejemplo daba 0 % de error en la evaluación | Se excluye siempre el mismo audio |
| La detección de "texto fijo" tomaba la línea de Bi-Rads como fija | Solo cuentan los bloques `TEXTO FIJO` |
| El historial duplicaba filas al volver a guardar | Se reemplaza la fila del mismo día |
| Un error de tipeo en una corrección se propagaba como ejemplo | Revisar `correcciones_aprendidas.md` |
| La IA seguía el orden del dictado | `ordenar_estudios` impone el orden estándar |
| Un estudio no reconocido producía "Protocolo normal." literal | Más sinónimos de reconocimiento y marca roja `[COMPLETAR]` |
| "un birrastre" quedaba en rojo aunque coincidía | Se desmarca si el número coincide con el Bi-Rads dictado |
| `String.TrimEnd(Char)` compilaba con Mono y fallaba en Windows | Reglas de API y autoprueba antes de instalar |
| Dos funciones `alinear` en `index.html` (una pisaba a la otra) | Renombrar y verificar nombres repetidos |
| Leer como JSON la página HTML de error del túnel (530) | `pedir()` nunca interpreta HTML: lo trata como "sin conexión" |

## Hoja de ruta

- Ajuste fino de Whisper con las voces de los médicos (con unos cientos de informes revisados).
- Detección de autocorrecciones del médico dentro del dictado ("perdón", "no, mejor").
- Controles de coherencia clínica (Bi-Rads contra hallazgos, lateralidad).
- Cálculos automáticos (volumen tiroideo y prostático, TI-RADS).
- Copia de seguridad automática y limpieza de audios antiguos.
- Ctrl+Enter para guardar y pasar al siguiente; deshacer en "Regenerar".
