#!/usr/bin/env bash
# Compila la app del trabajo con Mono (Linux), sin instalar nada en Windows.
# Uso:  ./compilar.sh            -> genera ../cliente/Transcripcion.exe
#       SALIDA=/tmp/x.exe ./compilar.sh
# Requisitos: mcs (paquetes mono-mcs y mono-devel, que traen /usr/lib/mono/4.8-api)
# y las DLL de WebView2 (Microsoft.Web.WebView2.Core.dll y .WinForms.dll) en ../cliente
# o en ./lib. Si faltan, se descargan del paquete NuGet oficial.
# IMPORTANTE: leer docs/compilacion.md (métodos que Mono acepta y .NET 4.8 no tiene).
set -euo pipefail
cd "$(dirname "$0")"

WEBVIEW2_VERSION="${WEBVIEW2_VERSION:-1.0.3856.49}"
API="${MONO_API:-/usr/lib/mono/4.8-api}"
SALIDA="${SALIDA:-../cliente/Transcripcion.exe}"
MCS="${MCS:-mcs}"

buscar_webview2() {
  for d in ../cliente lib; do
    if [[ -f "$d/Microsoft.Web.WebView2.Core.dll" && -f "$d/Microsoft.Web.WebView2.WinForms.dll" ]]; then
      echo "$d"; return 0
    fi
  done
  return 1
}

if ! WV=$(buscar_webview2); then
  echo "Descargando Microsoft.Web.WebView2 $WEBVIEW2_VERSION desde nuget.org..."
  tmp=$(mktemp -d)
  curl -fsSL -o "$tmp/webview2.zip" \
    "https://www.nuget.org/api/v2/package/Microsoft.Web.WebView2/$WEBVIEW2_VERSION"
  mkdir -p lib
  unzip -q -o "$tmp/webview2.zip" 'lib/net462/*.dll' 'runtimes/*/native/WebView2Loader.dll' -d "$tmp/pkg"
  cp "$tmp"/pkg/lib/net462/Microsoft.Web.WebView2.Core.dll "$tmp"/pkg/lib/net462/Microsoft.Web.WebView2.WinForms.dll lib/
  cp -r "$tmp/pkg/runtimes" lib/
  rm -rf "$tmp"
  WV=lib
fi

refs=()
for a in mscorlib System System.Core System.Windows.Forms System.Drawing System.Web.Extensions System.Security System.Xml; do
  refs+=("-r:$API/$a.dll")
done

mkdir -p "$(dirname "$SALIDA")"
"$MCS" -nostdlib -noconfig -target:winexe -optimize+ -win32icon:app.ico -out:"$SALIDA" \
  "${refs[@]}" -r:"$WV/Microsoft.Web.WebView2.Core.dll" -r:"$WV/Microsoft.Web.WebView2.WinForms.dll" \
  ./*.cs

echo "Listo: $SALIDA"
echo "Para distribuir, junto al .exe tienen que estar Transcripcion.exe.config, las dos DLL de WebView2"
echo "y la carpeta runtimes\\ (WebView2Loader.dll). Ver docs/compilacion.md."
