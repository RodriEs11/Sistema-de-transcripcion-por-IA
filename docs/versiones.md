# Versiones y entregas

Cómo se numeran la app del trabajo y el servidor, cuándo se suben esos números y cómo se publica una entrega.
La decisión y sus motivos están en [ADR 0002](adr/0002-versiones-por-entrega.md); las reglas cortas para agentes,
en [AGENTS.md](../AGENTS.md).

## Idea general

- **Un número por entrega, no por PR.** Los PR de trabajo solo dejan sus notas en el CHANGELOG. Las versiones
  se suben una vez, en un PR propio, cuando se decide entregar.
- **Cada entrega queda marcada en git** con etiquetas (`app-v1.29`, `servidor-v2026.11.16`). La instalación en uso
  se actualiza a esa etiqueta, así el número que muestra el panel corresponde siempre a un commit exacto.
- **Se automatiza lo repetitivo:** `herramientas/subir_version.py` cambia todos los lugares a la vez y
  `herramientas/verificar_versiones.py` comprueba que estén de acuerdo (también en el CI).

## Palabras que disparan acciones

| El usuario dice | Significa |
|---|---|
| «subí a GitHub», «subí los cambios» | Publicar la rama y abrir un PR hacia `main`. **No** fusionar ni crear una entrega. |
| «sacá versión», «publicá», «distribuí», «hacé la entrega» | Preparar una entrega: rama `release/…`, versiones, PR, y después de fusionar, etiquetas. |
| «fusioná», «mergeá» | Fusionar el PR indicado. No crea etiquetas por sí solo. |

Si un pedido no deja claro si es una entrega, preguntar.

## Esquemas

| Componente | Dónde está | Esquema | Ejemplos |
|---|---|---|---|
| App del trabajo | `cliente_codigo/Programa.cs`: `Programa.VERSION`, `AssemblyVersion`, `AssemblyFileVersion` | [Versionado semántico](https://semver.org/lang/es/) `MAYOR.MENOR[.PARCHE]`; en los ensamblados, con cuatro números | `1.29` → `1.29.0.0`; `1.29.1` → `1.29.1.0` |
| Servidor | `servidor.py`: `VERSION` | Fecha de Buenos Aires `AAAA.M.N`: año, mes sin cero y un correlativo que vuelve a 1 cada mes | `2026.11.16`, `2026.12.1` |

Además, en cada entrega: `CHANGELOG.md` (entradas fechadas) y `cliente/LEEME.txt` («Versión actual» y una línea
para quien usa la app).

## Qué número subir

| Cambio incluido en la entrega | App | Servidor |
|---|---|---|
| Corrección en la app sin funciones nuevas | PARCHE: 1.28 → 1.28.1 | — |
| Función nueva o cambio visible en la app | MENOR: 1.28 → 1.29 (el parche vuelve a 0) | — |
| La app deja de funcionar con servidores anteriores (protocolo, formato, API quitada) | MAYOR: 1.x → 2.0 | también sube |
| Página principal (`web/index.html`, `web/js/principal/`, `web/css/principal/`) | MENOR (ver [decisión pendiente](#decisión-pendiente-página-principal-y-versión-de-la-app)) | sube |
| Comportamiento, API, procesamiento o páginas del servidor | — | siguiente N del mes |
| Refactor con los contratos en verde | sin versión propia: «Interno», sale con la próxima entrega | ídem |
| Solo documentación, pruebas, CI o herramientas de desarrollo | — | — |

Si una entrega junta varios cambios, gana el más grande (una función nueva y una corrección → MENOR).

## En cada PR de trabajo

Ramas `feat/`, `fix/`, `refactor/`, `perf/` y similares.

1. **No tocar** `Programa.VERSION`, `AssemblyVersion`, `AssemblyFileVersion` ni `VERSION` de `servidor.py`.
2. Agregar las notas en `CHANGELOG.md` → «Sin publicar»:

   ```markdown
   ## Sin publicar

   (texto libre: trabajo pendiente que todavía no está hecho)

   ### App

   #### Corregido
   - Editor: … (#31).

   ### Servidor

   #### Agregado
   - Panel: … (#33).
   ```

   - Las subsecciones son `### App` y `### Servidor`. Las categorías van con `####`: Agregado, Cambiado,
     Corregido, Quitado o Interno. «Interno» es para reorganizaciones y herramientas sin cambios visibles.
   - Escribir el resultado para quien usa el sistema, con el issue (`#NN`), no la lista de archivos.
   - Si el PR toca la página principal, va una nota en cada subsección, como pide la tabla.
3. En el PR, decir qué componente afecta y si rompe compatibilidad con versiones anteriores del otro componente.
   En ese caso, la nota lo dice: «Requiere Servidor ≥ …» o «Requiere App ≥ …».

`python herramientas/verificar_versiones.py --sin-binario` tiene que seguir pasando: como el PR no cambia
números, no hace falta tocar entradas fechadas ni LEEME.

## Preparar una entrega

Se hace cuando el usuario lo pide. Incluye **todo lo fusionado** en `main` hasta ese momento: la etiqueta marca un
commit y ese commit contiene todo lo anterior.

1. Rama nueva desde `main` actualizado: `release/app-1.29-servidor-2026.11.16`, o solo el componente que cambia
   (`release/servidor-2026.11.16`). Para saber los números, usar `--sin-escribir`:

   ```bat
   python herramientas/subir_version.py --app menor --servidor --sin-escribir
   ```

2. Subir las versiones:

   ```bat
   python herramientas/subir_version.py --app menor --servidor --leeme "Texto corto para las PC: qué cambia para ellos."
   ```

   La herramienta:
   - cambia los tres valores de `Programa.cs` y la versión de `servidor.py`;
   - pasa las notas de «Sin publicar» a `## [App X] — fecha` y `## [Servidor Y] — fecha`, con «Acompaña a…»
     cuando salen juntas;
   - actualiza LEEME.

   Se niega a seguir en estos casos:
   - falta la línea de LEEME para la app;
   - un componente que se entrega no tiene notas;
   - un componente tiene notas en «Sin publicar» y no se entrega. Lo fusionado viaja en la etiqueta igual, así
     que también sube su número.

3. Revisar el diff y retocar las entradas si hace falta: unir notas que hablan de lo mismo, agregar
   «Requiere …».
4. Actualizar la documentación que nombra versiones (por ejemplo, «desde la versión …» en `docs/`).
5. `python herramientas/verificar_versiones.py --sin-binario --entrega`. En la instalación, sin `--sin-binario`
   después de compilar. Con `--entrega` también exige versiones posteriores a la última etiqueta y «Sin publicar»
   sin notas de App ni de Servidor.
6. Commit `chore(release): App 1.29 y Servidor 2026.11.16` y PR hacia `main`. En las ramas `release/` el CI baja
   las etiquetas y corre la verificación con `--entrega`; también compila la app y ejecuta su autoprueba en Windows.
7. Fusionar cuando el usuario lo indique.
8. Etiquetar el commit de la fusión, con autorización del usuario para publicar:

   ```bat
   git switch main
   git pull --ff-only
   git tag -a app-v1.29 -m "App 1.29"
   git tag -a servidor-v2026.11.16 -m "Servidor 2026.11.16"
   git push origin app-v1.29 servidor-v2026.11.16
   ```

   Si después de la entrega se fusionó otro PR, etiquetar el commit de la fusión de `release/…` (`git tag -a … <commit>`).
   Las etiquetas no se mueven ni se borran: si una entrega salió mal, se corrige con otra.

## Activar la entrega en la instalación

En `sistema\`, en una ventana sin trabajo en curso (ver [activacion-coordinada.md](historial/activacion-coordinada.md)):

```bat
git fetch origin --tags
git switch main
git merge --ff-only servidor-v2026.11.16
powershell -NoProfile -ExecutionPolicy Bypass -File cliente_codigo/compilar.ps1
python herramientas/verificar_versiones.py
```

- `merge --ff-only` lleva `main` justo hasta la etiqueta, sin arrastrar lo que se haya fusionado después.
- Si la entrega no cambia la app, `compilar.ps1` no hace falta.
- Si cambió código Python, coordinar el reinicio desde el panel. El panel (Mantenimiento) muestra el commit y la
  etiqueta «En uso» y «En la carpeta»: si son distintos, todavía falta reiniciar.
- Las PC instalan la app nueva solas cuando están libres. No afirmar que se actualizaron sin verlo en el panel.

**Volver atrás**:
1. `git switch --detach servidor-v<anterior>`.
2. Recompilar si cambió la app.
3. Reiniciar.

Para retomar: `git switch main`.

## Correcciones urgentes

Rama `fix/…`, PR con su nota y, apenas se fusiona, una entrega solo con esa corrección: PARCHE de la app o
siguiente número del servidor. Mismo procedimiento, sin esperar a juntar otros cambios.

## Experimentos

En `exp/` y `experimental` no se tocan versiones ni notas de entrega. Al promover un experimento con `feat/…`
hacia `main`, se agregan las notas en «Sin publicar» como en cualquier PR. El número se asigna en la próxima
entrega. Ver [experimentos.md](experimentos.md).

## Decisión pendiente: página principal y versión de la app

La app carga la página principal desde el servidor (WebView2). Hoy, un cambio solo en la página igual sube la app
(MENOR). Eso obliga a recompilar y redistribuir un ejecutable que no cambió, solo para que el número de la app
avise a las PC que hay novedades.

La alternativa es que esos cambios suban solo el servidor y que LEEME los anuncie por número de servidor.
Mientras no se decida otra cosa (con un ADR nuevo), sigue la regla actual de la tabla.

## Primera vez

Las entregas anteriores a este esquema no tienen etiquetas. Para que las comprobaciones contra la «última
entrega» funcionen desde el principio, etiquetar una vez el commit que publicó la App 1.28 y el Servidor 2026.11.15
(fusión del PR #46, `8db07f5`):

```bat
git tag -a app-v1.28 -m "App 1.28" 8db07f5
git tag -a servidor-v2026.11.15 -m "Servidor 2026.11.15" 8db07f5
git push origin app-v1.28 servidor-v2026.11.15
```
