# Compila y prueba la app con el compilador de .NET Framework incluido en Windows.
# No descarga paquetes ni cierra aplicaciones. Ver docs/compilacion.md.
param([switch]$SoloCompilar)
$ErrorActionPreference = 'Stop'
$raiz = Split-Path $PSScriptRoot -Parent
$python = Join-Path $raiz '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    $python = (Get-Command python -ErrorAction Stop).Source
}
& $python (Join-Path $raiz 'herramientas\verificar_versiones.py') --sin-binario
if ($LASTEXITCODE -ne 0) { throw 'Versiones o documentación incoherentes; no se compila ni publica.' }
$cliente = Join-Path $raiz 'cliente'
$sello = Get-Date -Format 'yyyyMMdd_HHmmss_fff'
$trabajo = Join-Path $raiz "respaldo/compilacion_$sello"
$candidato = Join-Path $trabajo 'Transcripcion.exe'
$destino = Join-Path $cliente 'Transcripcion.exe'
$compiladores = @(
    "$env:WINDIR/Microsoft.NET/Framework64/v4.0.30319/csc.exe",
    "$env:WINDIR/Microsoft.NET/Framework/v4.0.30319/csc.exe"
)
$compilador = $compiladores | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $compilador) { throw 'Falta el compilador de .NET Framework. Ver docs/compilacion.md.' }
$fuente = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'Programa.cs') -Raw
$version = [regex]::Match($fuente, 'public const string VERSION = "([0-9.]+)";').Groups[1].Value
if (-not $version) { throw 'No se encontró Programa.VERSION.' }
$partes = @($version.Split('.'))
if ($partes.Count -lt 2 -or $partes.Count -gt 3) { throw 'Versión de app inválida.' }
while ($partes.Count -lt 4) { $partes += '0' }
$versionArchivo = $partes -join '.'
foreach ($atributo in @('AssemblyVersion', 'AssemblyFileVersion')) {
    if (-not $fuente.Contains(('System.Reflection.{0}("{1}")' -f $atributo, $versionArchivo))) {
        throw "$atributo no coincide con Programa.VERSION ($version)."
    }
}
New-Item -ItemType Directory -Path $trabajo | Out-Null
Copy-Item -LiteralPath (Join-Path $cliente 'Transcripcion.exe.config') -Destination $trabajo
$argumentos = @('/nologo', '/target:winexe', '/optimize+',
    "/win32icon:$PSScriptRoot/app.ico", "/resource:$PSScriptRoot/app.ico,Transcripcion.app.ico",
    "/out:$candidato", '/r:System.Drawing.dll', '/r:System.Security.dll',
    '/r:System.Web.Extensions.dll', '/r:System.Windows.Forms.dll', '/r:System.Xml.dll')
foreach ($dll in @('Microsoft.Web.WebView2.Core.dll', 'Microsoft.Web.WebView2.WinForms.dll')) {
    $ruta = Join-Path $cliente $dll
    if (-not (Test-Path -LiteralPath $ruta)) { throw "Falta $ruta." }
    $argumentos += "/r:$ruta"
}
$argumentos += @(Get-ChildItem -LiteralPath $PSScriptRoot -Filter '*.cs' | ForEach-Object { $_.FullName })
& $compilador @argumentos
if ($LASTEXITCODE -ne 0) { throw 'Falló la compilación; se conserva el ejecutable distribuido.' }
if ([Diagnostics.FileVersionInfo]::GetVersionInfo($candidato).FileVersion -ne $versionArchivo) {
    throw 'El candidato compilado tiene una versión incorrecta.'
}
$inicio = New-Object Diagnostics.ProcessStartInfo
$inicio.FileName = $candidato
$inicio.Arguments = '--autoprueba "' + $cliente + '"'
$inicio.UseShellExecute = $false
$inicio.CreateNoWindow = $true
$proceso = [Diagnostics.Process]::Start($inicio)
if (-not $proceso.WaitForExit(30000)) {
    $proceso.Kill()
    throw 'La autoprueba superó los 30 segundos; no se publica.'
}
$informe = Join-Path $trabajo 'autoprueba.txt'
if ($proceso.ExitCode -ne 0 -or -not (Test-Path -LiteralPath $informe)) {
    throw "Falló la autoprueba; revisar $trabajo. No se publica."
}
Get-Content -LiteralPath $informe
if ($SoloCompilar) {
    Write-Output "Candidato verificado: $candidato (sin distribuir)."
    return
}
# Copiar primero a la misma unidad: el reemplazo final es un renombrado, no una copia parcial.
$nuevo = Join-Path $cliente "Transcripcion.exe.nuevo-$sello"
$anterior = Join-Path $cliente "Transcripcion.exe.viejo-$sello"
Copy-Item -LiteralPath $candidato -Destination $nuevo
$habiaAnterior = Test-Path -LiteralPath $destino
if ($habiaAnterior) { Move-Item -LiteralPath $destino -Destination $anterior }
try {
    Move-Item -LiteralPath $nuevo -Destination $destino
} catch {
    if ($habiaAnterior -and -not (Test-Path -LiteralPath $destino)) {
        Move-Item -LiteralPath $anterior -Destination $destino
    }
    throw
}
Write-Output "App $version distribuida en $destino. Las PC se actualizarán cuando estén libres."
Write-Output "Candidato e informe conservados en $trabajo."
& $python (Join-Path $raiz 'herramientas\verificar_versiones.py')
if ($LASTEXITCODE -ne 0) { throw 'Falló la verificación final de la distribución; revisar antes de dar por terminada la entrega.' }
