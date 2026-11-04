# Compilación de la app del trabajo

La app (`cliente_codigo/`) apunta a **.NET Framework 4.8** (incluido en Windows 10/11) y usa **WebView2**
(paquete NuGet `Microsoft.Web.WebView2` 1.0.3856.49). No usa ZipArchive ni otras bibliotecas fuera de las básicas
del framework para poder correr en las PC del trabajo sin instalar nada.

## Opción A — Windows con el .NET SDK

Requisitos: [.NET SDK](https://dotnet.microsoft.com/download) 6 o superior (para compilar proyectos `net48`
descarga solo los *reference assemblies*).

```bat
cd cliente_codigo
dotnet build -c Release
```

La salida queda en `cliente_codigo\bin\Release\net48\`: `Transcripcion.exe`, `Transcripcion.exe.config`,
las dos DLL de WebView2 y `runtimes\`. También se puede abrir `Transcripcion.csproj` con Visual Studio 2022.

### Compilar y distribuir automáticamente en esta instalación de Windows

Desde `sistema/`:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File cliente_codigo/compilar.ps1
python verificar_versiones.py
```

El script usa el compilador de .NET Framework de Windows y las DLL que ya están en `cliente/`.
`-ExecutionPolicy Bypass` habilita este script solo durante ese proceso, sin modificar la política
de Windows. Usa Python de `.venv` si existe, o `python` del PATH para verificar la documentación
antes de compilar y el manifiesto después de distribuir.
Comprueba los tres valores de versión, compila en `respaldo/compilacion_<fecha>/`, verifica
los metadatos y ejecuta la autoprueba con un límite de 30 segundos. Solo entonces reemplaza
el ejecutable distribuido mediante renombrado, conservando el anterior como `.viejo-<fecha>`.
No cierra la app que esté abierta. Si falla el reemplazo, intenta restaurar el anterior.
Para verificar un candidato sin distribuirlo, agregar `-SoloCompilar`.
Las advertencias del compilador deben revisarse; cualquier error o autoprueba fallida impide publicar.
Los respaldos se conservan para recuperación y se pueden limpiar después de confirmar la actualización.

## Opción B — Linux con Mono (versiones publicadas)

Es el método con el que se compilaron las versiones distribuidas, sin instalar nada en Windows.

```bash
sudo apt install mono-mcs mono-devel     # mono-devel trae /usr/lib/mono/4.8-api
./cliente_codigo/compilar.sh             # genera cliente/Transcripcion.exe
```

`compilar.sh` usa las DLL de WebView2 que haya en `cliente/` o en `cliente_codigo/lib/`; si no están, las
descarga del paquete NuGet oficial. Variables opcionales: `SALIDA`, `MCS`, `MONO_API`, `WEBVIEW2_VERSION`.

Comando equivalente:

```bash
mcs -nostdlib -noconfig -target:winexe -win32icon:app.ico -out:../cliente/Transcripcion.exe \
  -r:/usr/lib/mono/4.8-api/{mscorlib,System,System.Core,System.Windows.Forms,System.Drawing,System.Web.Extensions,System.Security,System.Xml}.dll \
  -r:Microsoft.Web.WebView2.Core.dll -r:Microsoft.Web.WebView2.WinForms.dll *.cs
```

## Métodos prohibidos

Las bibliotecas de referencia de Mono (incluso los perfiles `4.8-api` y `4.5-api`) incluyen sobrecargas que
**.NET Framework 4.8 no tiene**. El código compila, pero en Windows falla con *"Método no encontrado"*.

| No usar | Usar |
|---|---|
| `s.Trim('x')`, `TrimStart(char)`, `TrimEnd(char)` | `s.TrimEnd(new[] { 'x' })` (ej. `Config.Barra`) |
| `s.Split(',', …)` | `s.Split(new[] { ',' }, …)` |
| `StartsWith(char)`, `EndsWith(char)`, `Contains(char)` | Las versiones con `string` |
| `s.Contains(x, StringComparison)` | `s.IndexOf(x, StringComparison) >= 0` |
| `System.IO.Compression.ZipArchive` | Lector ZIP propio (Mono referencia `System.IO.Compression` 4.2.0.0, que .NET 4.8 no tiene) |
| `Form.DeviceDpi` | `Graphics.FromHwnd(IntPtr.Zero).DpiX` |

Otras reglas:
- No crear el *handle* de la ventana en el constructor (`Screen.FromControl`, `CreateGraphics`): rompe el arranque oculto.
- Los relojes que deben funcionar con la ventana oculta usan `System.Threading.Timer` + `BeginInvoke`, no el `Timer` de Windows Forms.

## Verificación

0. **Reorganizaciones sin cambios de comportamiento** (mover métodos entre archivos de una *partial class*, cambiar
   su orden): compilar antes y después con la misma versión y comparar el IL con
   `python pruebas/comparar_il.py antes.exe despues.exe` (necesita `ikdasm`, de Mono). Tiene que decir «IL
   equivalente». Los campos con valor inicial quedan todos en `VentanaPrincipal.cs`: entre archivos de una partial
   class, C# no garantiza el orden de inicialización.
1. **Referencias**: con [Mono.Cecil](https://github.com/jbevain/cecil) listar los métodos externos que usa el `.exe`
   y compararlos con la versión anterior; revisar cada método nuevo contra la API de .NET Framework 4.8. Todas las
   referencias de ensamblado deben ser `4.0.0.0`.
2. **Autoprueba**: `Transcripcion.exe --autoprueba "<carpeta>"` recorre el IL de todos los métodos, resuelve cada
   miembro con `Module.ResolveMember` y los compila con `RuntimeHelpers.PrepareMethod`. Es la misma prueba que
   hace cada PC antes de instalar una actualización.
3. **Prueba visual en Linux**: `xvfb-run` cierra el servidor X cuando termina el proceso que lanzó; para probar
   actualizaciones hay que mantenerlo vivo: `xvfb-run bash -c "mono Transcripcion.exe; sleep 900"`.

## Publicar una versión

Cada cambio en la aplicación de escritorio debe incrementar su versión, incluidos los cambios
en la interfaz de revisión que carga del servidor. Mantener sincronizados los tres valores de `Programa.cs`.

1. Subir la versión en `Programa.cs`: `AssemblyVersion`, `AssemblyFileVersion` y `Programa.VERSION`.
2. Actualizar `cliente/LEEME.txt` y el [CHANGELOG](../CHANGELOG.md).
3. Compilar y verificar (arriba).
4. Copiar el `.exe` a `sistema\cliente\` del servidor. Si el anterior está en uso, renombrarlo antes a
   `Transcripcion.exe.viejo-X.Y` (el manifiesto ignora esos archivos).
5. No hace falta reiniciar el servidor: el manifiesto se recalcula solo. Cada PC se actualiza cuando no se usa.

6. Ejecutar `python verificar_versiones.py`: debe confirmar app, servidor, CHANGELOG, LEEME,
   versión del ejecutable y manifiesto. En un checkout sin distribución, `--sin-binario` verifica
   únicamente las fuentes; no reemplaza la validación del ejecutable.

> Las versiones 1.0 y 1.1 no tienen actualizador: en esas PC hay que copiar una versión ≥ 1.2 a mano una sola vez.
