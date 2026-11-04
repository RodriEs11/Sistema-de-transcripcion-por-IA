"""Comprueba la coherencia de una entrega sin modificar archivos ni iniciar la app."""
import argparse
import re
from pathlib import Path


RAIZ = Path(__file__).resolve().parent


def comprobar(raiz=RAIZ, sin_binario=False):
    errores = []
    codigo = (raiz / "cliente_codigo/Programa.cs").read_text(encoding="utf-8-sig")
    servidor = (raiz / "servidor.py").read_text(encoding="utf-8-sig")
    historial = (raiz / "CHANGELOG.md").read_text(encoding="utf-8-sig")
    leeme = (raiz / "cliente/LEEME.txt").read_text(encoding="utf-8-sig")

    def extraer(patron, texto, nombre):
        encontrados = re.findall(patron, texto, re.MULTILINE)
        if len(encontrados) != 1:
            errores.append(f"{nombre}: se esperaba una única definición.")
            return None
        return encontrados[0]

    app = extraer(r'public const string VERSION = "([0-9.]+)";', codigo, "Programa.VERSION")
    for atributo in ("AssemblyVersion", "AssemblyFileVersion"):
        valor = extraer(r'\[assembly: System\.Reflection\.' + atributo + r'\("([0-9.]+)"\)\]',
                        codigo, atributo)
        if app and valor:
            partes = app.split(".")
            if len(partes) not in (2, 3):
                errores.append("La versión de la app debe tener dos o tres componentes.")
            elif valor != ".".join(partes + ["0"] * (4 - len(partes))):
                errores.append(f"{atributo} ({valor}) no coincide con la app ({app}).")
    actual = extraer(r'^VERSION = "([0-9.]+)"', servidor, "Servidor.VERSION")
    for nombre, version in (("App", app), ("Servidor", actual)):
        if version and not re.search(r'^## \[(?:' + nombre + r' )?' + re.escape(version)
                                     + r'\] — \d{4}-\d{2}-\d{2}\s*$', historial, re.MULTILINE):
            errores.append(f"Falta la entrada fechada de {nombre} {version} en CHANGELOG.md.")
    if app and not re.search(r'^Versión actual: ' + re.escape(app) + r' \(\d{4}-\d{2}-\d{2}\)\.',
                             leeme, re.MULTILINE):
        errores.append(f"LEEME.txt no anuncia la versión actual {app} con su fecha.")
    if not sin_binario:
        from transcripcion.operacion import app_cliente
        # Usar la misma lectura que realiza el servidor, sin consultar ni modificar su caché.
        exe = raiz / "cliente/Transcripcion.exe"
        distribuida = app_cliente.version_exe(exe)
        if not distribuida:
            errores.append("Falta el ejecutable distribuido o no tiene FileVersion legible.")
        elif distribuida != app:
            errores.append(f"El ejecutable distribuido es {distribuida}; el código es {app}.")
        if raiz.resolve() == RAIZ.resolve():
            manifiesto = app_cliente.manifiesto()
            if manifiesto["version"] != app:
                errores.append("El manifiesto de actualización no anuncia la versión del código.")
            if any(any(marca in a["ruta"].lower() for marca in (".viejo", ".nuevo", ".fallida"))
                   for a in manifiesto["archivos"]):
                errores.append("El manifiesto incluye un archivo temporal o de recuperación.")
    return errores, app, actual


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sin-binario", action="store_true",
                        help="Solo código y documentación; no valida una distribución.")
    args = parser.parse_args()
    try:
        errores, app, servidor = comprobar(sin_binario=args.sin_binario)
    except (OSError, UnicodeError) as exc:
        parser.exit(1, f"No se pudo verificar: {exc}\n")
    for error in errores:
        print("ERROR: " + error)
    if errores:
        return 1
    alcance = "solo fuentes" if args.sin_binario else "fuentes, ejecutable y manifiesto"
    print(f"Versiones OK: app {app}; servidor {servidor} ({alcance}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
