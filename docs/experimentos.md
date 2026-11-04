# Ramas experimentales y entorno de pruebas

Para probar ideas que pueden no llegar nunca a la versión final, sin arriesgar la instalación
en uso ni ensuciar `main`.

## Ramas

| Rama | Para qué | Dura |
|---|---|---|
| `main` | Lo que está en producción o listo para estarlo. Solo se cambia por PR | siempre |
| `experimental` | Rama de integración de pruebas: junta varios experimentos para probarlos juntos. Puede tener cosas a medio hacer | siempre |
| `exp/<tema>` | Un experimento puntual (`exp/whisper-turbo`, `exp/editor-colores`). Sale de `experimental` y vuelve a ella por PR | lo que dure la prueba |
| `feat/`, `fix/`, … | Trabajo destinado a la versión final (ver [AGENTS.md](../AGENTS.md)) | hasta fusionarse |

No usar `test/` para experimentos: ese prefijo es para ramas de pruebas automáticas.
Tampoco `dev`/`develop`: dan a entender que todo lo que entra termina en producción.

### Reglas

1. **`experimental` nunca se fusiona entera en `main`.** Cuando un experimento sirve, se
   **promueve**: rama nueva `feat/<tema>` desde `main`, se trae el cambio (`git cherry-pick <commits>`
   o rehaciéndolo prolijo) y se completa como cualquier entrega (versiones, CHANGELOG, pruebas, PR a `main`).
2. **Actualizar `experimental` con `main` seguido** (`git merge origin/main` en una rama
   `exp/actualizar-main` o directo si no hay conflictos) para que no se aleje.
3. **Sin versiones nuevas en la rama experimental.** No se tocan `Programa.VERSION` ni `VERSION`
   de `servidor.py`: la versión se asigna al promover. Así nunca se publica un número que después
   no existe en `main`, y `herramientas/verificar_versiones.py` sigue pasando.
4. **Nunca se distribuye la app compilada desde `experimental`** a las PC del trabajo: el servidor
   de pruebas usa otro puerto y no abre túnel, así que ninguna PC del trabajo se actualiza desde él.
5. Commits con Conventional Commits igual que siempre (`feat(editor): probar …`). Los mismos cuidados:
   sin datos de pacientes, secretos ni binarios.
6. Un experimento descartado: se borra la rama `exp/…`, o se archiva con una etiqueta si se quiere
   conservar la idea (`git tag archivo/exp-tema exp/tema && git push origin archivo/exp-tema`).
7. El CI corre en los PR hacia `experimental` y en cada push a `experimental`. Un CI rojo ahí no bloquea
   producción, pero hay que arreglarlo antes de promover.

## Entorno de pruebas aislado

La carpeta `sistema\` es a la vez el repositorio y la instalación que atiende al trabajo: **no hay que
cambiar de rama ahí**. Para probar, se crea una copia separada:

```bat
cd "E:\Desktop\Transcripcion con claude\sistema"
python scripts/crear_entorno_pruebas.py                       :: rama experimental en ..\sistema_pruebas
python scripts/crear_entorno_pruebas.py --rama exp/mi-idea --destino ..\pruebas_mi_idea --puerto 8875
```

`scripts/crear_entorno_pruebas.py` solo **lee** la instalación en uso. La copia:

| | Instalación en uso | Entorno de pruebas |
|---|---|---|
| Carpeta | `sistema\` | `sistema_pruebas\` (repositorio independiente, `origin` = GitHub) |
| Puertos | 8765 / 8766 | 8865 / 8866 (o `--puerto`) |
| Túnel y acceso remoto | sí | no (no se copia `acceso_remoto.json`) |
| Audios e informes | `..\Audios_nuevos`, `..\Informes` | `sistema_pruebas\Audios_nuevos`, `sistema_pruebas\Informes` |
| Cola, registros, resultados, voces | propios | propios y vacíos |
| `conocimiento\`, `modelos\` | originales | copias (se pueden modificar sin afectar producción) |
| IA | real | simulada (`SIMULAR_IA=1`) salvo `iniciar_pruebas.bat real` |
| Python | `.venv` | el mismo `.venv` de producción (solo se ejecuta; no se instala nada) |

Para abrirlo: `sistema_pruebas\iniciar_pruebas.bat` (o `./iniciar_pruebas.sh` en Linux). La ventana
dice **EXPERIMENTAL** y la interfaz queda en `http://127.0.0.1:8865`. El panel muestra la rama y el commit.

**IA real (`iniciar_pruebas.bat real`)**: Whisper y Ollama son los mismos que usa producción y comparten la
GPU. Usarlo solo cuando no haya informes en proceso; si el experimento necesita otro modelo o paquetes
nuevos de Python, crear una `.venv` propia dentro de `sistema_pruebas` (`instalar.bat`) en lugar de tocar la
de producción.

El modo simulado necesita datos ficticios con la estructura descrita en [desarrollo.md](desarrollo.md#modo-simulado-sin-gpu-ni-ollama).

### Probar la app del trabajo

El entorno de pruebas no tiene túnel, así que las PC del trabajo no lo ven: la app de prueba se usa en la misma PC
del servidor, contra `http://127.0.0.1:<puerto>`.

1. `scripts/crear_entorno_pruebas.py` deja en `sistema_pruebas\cliente\` las bibliotecas de WebView2 de producción (nunca el
   `.exe` ni `conexion.json`) y el archivo **`perfil_pruebas.txt`**. En un entorno creado antes de esto:
   `python scripts/crear_entorno_pruebas.py --preparar-app` desde `sistema_pruebas`.
2. Compilar ahí: `powershell -NoProfile -ExecutionPolicy Bypass -File cliente_codigo\compilar.ps1`. Queda
   `sistema_pruebas\cliente\Transcripcion.exe`; la carpeta `cliente` de producción no se toca.
3. Abrirlo, elegir «Escribí la dirección del Servidor» y poner `http://127.0.0.1:<puerto>`.

Con `perfil_pruebas.txt` la app se llama **Transcripción (PRUEBAS)** y usa otra carpeta de datos
(`%LOCALAPPDATA%\Transcripcion-pruebas`: configuración, llave, cola, WebView2), otra instancia y otra clave de inicio
con Windows, así que puede abrirse junto a la app de producción sin pisarla. Arranca **sin tomar los audios de
`%TEMP%`** (Opciones → Configuración → Esta PC para activarlo). El archivo no está en el manifiesto de
actualización, así que nunca llega a las PC.

Para borrar el entorno: cerrar su ventana y eliminar la carpeta `sistema_pruebas` (antes, publicar con
`git push` lo que se quiera conservar). La instalación en uso no se entera.

## Flujo típico

```bat
cd ..\sistema_pruebas
git switch experimental && git pull
git switch -c exp/editor-colores
:: ... cambios, probar con iniciar_pruebas.bat ...
git commit -am "feat(editor): probar paleta de colores alternativa"
git push -u origin exp/editor-colores
:: PR en GitHub: exp/editor-colores -> experimental (no hacia main)
```

Si funciona y se decide incluirlo: `git switch -c feat/editor-colores origin/main`,
`git cherry-pick <commits>`, versiones + CHANGELOG + pruebas, PR hacia `main` y activación normal en
`sistema\` (ver [activacion-coordinada.md](activacion-coordinada.md)).
