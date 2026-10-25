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

1. **Referencias**: con [Mono.Cecil](https://github.com/jbevain/cecil) listar los métodos externos que usa el `.exe`
   y compararlos con la versión anterior; revisar cada método nuevo contra la API de .NET Framework 4.8. Todas las
   referencias de ensamblado deben ser `4.0.0.0`.
2. **Autoprueba**: `Transcripcion.exe --autoprueba "<carpeta>"` recorre el IL de todos los métodos, resuelve cada
   miembro con `Module.ResolveMember` y los compila con `RuntimeHelpers.PrepareMethod`. Es la misma prueba que
   hace cada PC antes de instalar una actualización.
3. **Prueba visual en Linux**: `xvfb-run` cierra el servidor X cuando termina el proceso que lanzó; para probar
   actualizaciones hay que mantenerlo vivo: `xvfb-run bash -c "mono Transcripcion.exe; sleep 900"`.

## Publicar una versión

1. Subir la versión en `Programa.cs`: `AssemblyVersion`, `AssemblyFileVersion` y `Programa.VERSION`.
2. Actualizar `cliente/LEEME.txt` y el [CHANGELOG](../CHANGELOG.md).
3. Compilar y verificar (arriba).
4. Copiar el `.exe` a `sistema\cliente\` del servidor. Si el anterior está en uso, renombrarlo antes a
   `Transcripcion.exe.viejo-X.Y` (el manifiesto ignora esos archivos).
5. No hace falta reiniciar el servidor: el manifiesto se recalcula solo. Cada PC se actualiza cuando no se usa.

> Las versiones 1.0 y 1.1 no tienen actualizador: en esas PC hay que copiar una versión ≥ 1.2 a mano una sola vez.
