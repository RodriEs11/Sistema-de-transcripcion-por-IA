# Transcriptores con estilo propio

> Servidor 2026.11.1 · App 1.23. Probado en la rama `exp/estilos-por-transcriptor` (PR #9 → `experimental`) y
> promovido a `main` con `feat/estilos-por-transcriptor`. Activación: ver «Activar en producción» al final.

## Problema

Cada transcriptor arma los informes de un mismo médico a su manera. Hasta ahora todo lo que define el estilo era
común (`plantillas.md`, notas de los médicos, `reglas_dictado.md`, ejemplos y correcciones aprendidas) y el sistema
solo sabía **qué PC** hacía cada cosa, no **quién**. Resultado: los estilos se mezclaban y lo que aprendía de uno se
le aplicaba a todos.

## Decisiones (tomadas con el usuario el 02/11/2026)

| Tema | Decisión |
|---|---|
| Quién transcribe | Usuario y contraseña propios. **Reemplaza** a la contraseña compartida del sistema. |
| Altas | Solo desde el panel de administración (contraseña inicial; se cambia al entrar). |
| PC del servidor | También pide usuario. |
| Sesión | Dura mientras la app esté abierta, **también escondida junto al reloj** (al volver a abrir la ventana no se piden las credenciales). Termina con «Cerrar sesión», «Salir», al cerrarse la app o el navegador (cookie de sesión) o tras 12 h sin que la página consulte (PC apagada o suspendida). Mientras se usa, se renueva sola. |
| Datos anteriores | Los ejemplos y correcciones que ya existían quedan **generales**. |
| Editar plantillas / notas | Se pregunta «¿Solo para mí o para todos?», con «Solo para mí» por defecto. |
| Ejemplos para la IA | Primero los propios; si no alcanzan, generales y de otros (marcados como «de otro transcriptor»). |
| Correcciones aprendidas | De un solo transcriptor: solo para él. Pasan a generales cuando las hacen dos distintos. |
| Informe armado con el estilo de otro | Aviso «La IA armó este informe con el estilo de X» y botón **Regenerar con mi estilo**. |
| Audios que la app toma sola | Se asignan a quien está usando la página en esa PC (si no hay nadie: estilo general). |
| Qué es propio | Plantillas, notas de cada médico, reglas de dictado, formato del Word y preferencias de la pantalla. |

**Transición:** mientras no haya ningún transcriptor activo, todo funciona como antes (sin pedir usuario y con la
contraseña compartida). Desde el primero, se pide usuario en todas las PC y la contraseña compartida deja de servir
para entrar o vincular PC.

## Capas: gana la más específica

```
General  →  Médico ("(estilo X)" en plantillas.md)  →  Transcriptor  →  Transcriptor + médico
```

| Qué | General | Propio del transcriptor (`conocimiento/usuarios/<clave>/`) | Cómo se combinan |
|---|---|---|---|
| Plantillas | `plantillas.md` | `plantillas.md` (solo las secciones cambiadas o nuevas) | La sección propia **reemplaza** a la general del mismo nombre; las nuevas se agregan. Una sección propia «… (estilo X)» cubre el caso transcriptor + médico. |
| Notas de un médico | `medicos/<Médico>.md` | `medicos/<Médico>.md` | Las propias **reemplazan** a las generales. Siguen al médico si se renombra. |
| Reglas de dictado | `reglas_dictado.md` | `reglas_dictado.md` | Se **suman**; si se contradicen, valen las propias. |
| Correcciones aprendidas | `correcciones_aprendidas.md` | `correcciones_aprendidas.md` | Se suman las dos en el prompt. Se generan solas. |
| Formato del Word | `configuracion.json` | `formato.json` | Fuente, tamaño, renglones de encabezado, títulos centrados / en negrita, renglón vacío después del título. |
| Preferencias de pantalla | `localStorage` de la PC | `preferencias.json` | Tema, atajos, velocidad, paneles… siguen al usuario en cualquier PC. |

Los **controles** (frases de plantilla en gris, texto fijo, estudios conocidos, vocabulario) usan las plantillas de
todos juntas: una frase de la plantilla de cualquiera es frase de plantilla.

## Archivos

| Archivo | Contenido | Git |
|---|---|---|
| `usuarios.json` | Nombre, huella PBKDF2 de la contraseña, activo, «tiene que cambiar la contraseña», última entrada | no (`.gitignore`) |
| `sesiones.json` | Sesiones con transcriptor, por **huella** del identificador (un reinicio del servidor no obliga a volver a entrar) | no |
| `conocimiento/usuarios/<clave>/…` | El estilo propio (tabla de arriba) y `copias/` de sus plantillas | no (`conocimiento/`) |
| `ejemplos/<clave>.usuario.txt` | Transcriptor que revisó ese ejemplo (sin archivo = general) | no |
| `resultados/historial.sqlite3` → tabla `ejemplo_usuario` | Lo mismo, indexado para repartir las correcciones (se crea sola) | no |
| `Informes/revision/datos/<caso>.usuario.txt` | Con el estilo de quién se arma el caso | no |
| `Informes/revision/datos/<caso>.estilo.txt` | Con el estilo de quién lo armó la IA la última vez (vacío = general) | no |

`registros/actividad.csv` suma la columna `usuario` (se agrega sola al archivo existente).

## Cómo funciona

### Entrar
- **Navegador:** `/entrar` pide usuario y contraseña (y el nombre de la PC si se entra por el túnel sin la app).
- **App del trabajo:** la PC sigue teniendo su llave (`Bearer`), pero ahora la llave **sola** solo sirve para
  enviar audios, consultar el estado y actualizarse. La app abre la página con el código de un solo uso; la página
  ya sabe qué PC es y pide usuario y contraseña en **`/ingresar`**. Es otra dirección que `/entrar` a propósito: la
  app intercepta `/entrar` (sin código) para volver a entrar sola con la llave, y con esa dirección haría un ciclo.
  Así también funciona con la app 1.22 sin cambios. **Salir** (arriba de la lista) deja la PC identificada para que
  entre el siguiente.
- **Vincular una PC nueva:** usuario y contraseña de cualquier transcriptor (el nombre de la PC sale solo del nombre
  de Windows). El Servidor devuelve además un código de un solo uso con ese usuario, así que la página abre ya con
  esa persona: no se le vuelve a pedir el usuario. Las PC ya vinculadas siguen funcionando. Requiere la app con el campo «Tu usuario» (cambio en `VentanaVincular.cs`); la app 1.22 solo
  puede vincular mientras no haya transcriptores.
- **Si el servidor se cae o se reinicia, no hay que volver a entrar** (Servidor 2026.11.2 · App 1.24). Las sesiones
  se guardan en `sesiones.json` y, cuando la app vuelve a abrir la pantalla con un código nuevo, el servidor conserva
  la sesión que la pantalla ya tenía. Si la pantalla perdió su cookie (dirección nueva del túnel), la app pide el
  código con `reconectar` y vuelve la persona que tenía la sesión abierta en esa PC. Al abrir la app de cero, después
  de «Cerrar sesión» o con la sesión vencida, se pide el usuario.
- **Cerrar la ventana de la app no cierra la sesión.** La app queda junto al reloj tomando audios y, al volver a
  abrirla, sigue la misma persona (los audios que toma mientras tanto se arman con su estilo).
- **Opciones ▾ (y el ícono junto al reloj):** **Cerrar sesión** sale la persona y la app queda abierta pidiendo usuario
  (para cambiar de usuario); **Salir** cierra la app enseguida: la página avisa al Servidor por detrás
  (`salirDeSesion({navegar:false})`, un `fetch` con `keepalive`) sin mostrar la pantalla de entrar.
- Cinco contraseñas mal desde la misma IP (o con el mismo usuario en la PC del servidor) bloquean 10 minutos.

### Generar
`servidor.py` lee `<caso>.usuario.txt` y lo pasa a `elegir_ejemplos(..., usuario)` y `armar_mensajes(..., usuario)`
(`transcripcion/ia/ejemplos.py` y `transcripcion/ia/prompt.py`): plantillas propias, notas propias del médico, reglas propias, correcciones propias y ejemplos propios
primero. Guarda `<caso>.estilo.txt`. **Volver a generar** usa siempre el estilo de quien lo pide.

### Aprender
Al guardar, el ejemplo queda con el transcriptor que lo revisó (`registrar_ejemplo(..., usuario)`).
`analizar_correcciones` reparte (`repartir_correcciones`): una corrección repetida es general si se repite entre
los ejemplos generales o la hicieron dos fuentes distintas; si la repite uno solo, va a su
`correcciones_aprendidas.md`.

## Pantallas

- **Lista:** arriba, el nombre de quien transcribe, **Mi cuenta** y **Cerrar sesión**.
- **Configuración → Mi cuenta:** cambiar contraseña (obligatorio con la inicial: no se puede cerrar hasta
  cambiarla), formato del Word propio, reglas de dictado propias y resumen de su estilo. Las reglas se ven en lista
  (Editar / Quitar); **Añadir regla** abre una ventana para cargar varias de una vez (Enter agrega otro renglón).
- **Plantillas / Médicos:** etiqueta «mía» / «solo mía», al guardar pregunta *¿Solo para mí o para todos?*, y botón
  **Volver a la general**.
- **Informe:** aviso de estilo ajeno con **Regenerar con mi estilo**.
- **Panel → Transcriptores:** alta, restablecer contraseña, cambiar nombre, desactivar / reactivar, en qué PC está
  ahora y qué tiene propio.

## Probar

```bat
python crear_entorno_pruebas.py --rama exp/estilos-por-transcriptor --destino ..\pruebas_usuarios --puerto 8875
```
En el entorno de pruebas no hay `usuarios.json`: el sistema arranca como antes. Crear transcriptores desde el panel
(`http://127.0.0.1:8875/admin`) y entrar con cada uno en navegadores distintos.

Para probar también la app, en la misma PC: ver [experimentos.md](experimentos.md#probar-la-app-del-trabajo)
(perfil de pruebas, no pisa a la app de producción).

Pruebas automáticas: `pruebas/test_usuarios.py` (usuarios, sesiones, capas, ejemplos, correcciones y HTTP) y
`pruebas/usuarios.cjs` (navegador: entrar, contraseña inicial, plantillas y notas propias, formato, aviso de estilo,
preferencias y salir).

## Activar en producción

El primer transcriptor cambia todo el sistema de una vez: desde ese momento todas las PC piden usuario. Por eso:

1. **Código, sin transcriptores.** Respaldo (`respaldo\respaldo_AAAAMMDD_HHMMSS_antes_de_usuarios\`, que incluya
   `usuarios.json` y `sesiones.json` si ya existen: `preparar_activacion.py` los copia) y una etiqueta en git del
   commit actual. `git pull` en `sistema\`, reiniciar el servidor desde el panel y compilar la App 1.23
   (`cliente_codigo\compilar.ps1`). Sin transcriptores todo funciona como antes, también con la App 1.22.
2. **Esperar a que todas las PC muestren 1.23** en el panel. La 1.22 sigue andando con el Servidor 2026.11.1, pero
   no puede vincular PC nuevas cuando ya hay transcriptores.
3. **Día D:** avisar al equipo y crear a todos en Panel → Transcriptores con una contraseña inicial cada uno; cada
   persona la cambia al entrar.
4. **Vuelta atrás:** problema con los usuarios → desactivarlos a todos (el sistema vuelve al modo anterior al
   instante; su estilo se conserva). Problema en el servidor → volver a la etiqueta y reiniciar. Problema en la
   app → volver a poner el ejecutable anterior (`Transcripcion.exe.viejo-…`) en `cliente\`; las PC vuelven solas.

Pendiente de decidir: estadísticas por transcriptor en el panel y filtro «Míos» en la lista.
