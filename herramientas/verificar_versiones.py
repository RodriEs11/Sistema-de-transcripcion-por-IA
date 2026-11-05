"""Comprueba la coherencia de las versiones sin modificar archivos ni iniciar la app (ver docs/versiones.md).

Sin opciones: fuentes, documentación, ejecutable y manifiesto de esta instalación.
--sin-binario: solo fuentes y documentación (CI, checkout sin ejecutable).
--entrega: además, que sea una entrega lista: versiones nuevas respecto de la última etiqueta y nada fusionado
           esperando en «Sin publicar». Se usa en la rama release/… antes de fusionar.
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path


RAIZ = Path(__file__).resolve().parents[1]     # carpeta del sistema (este archivo está en herramientas/)
sys.path.insert(0, str(RAIZ))                  # para importar transcripcion

PREFIJOS = {"App": "app-v", "Servidor": "servidor-v"}   # etiquetas de git de cada entrega publicada
FORMATO = {"App": r"\d+\.\d+(?:\.\d+)?", "Servidor": r"\d{4}\.(?:[1-9]|1[0-2])\.[1-9]\d*"}


def numeros(version):
    """'1.28' -> (1, 28, 0); '2026.11.15' -> (2026, 11, 15): para comparar versiones del mismo componente."""
    partes = tuple(int(x) for x in version.split("."))
    return partes + (0,) * (3 - len(partes))


def sin_publicar(historial):
    """Separa la sección «## Sin publicar» del CHANGELOG.

    Devuelve (inicio, pendiente, notas, resto): `inicio` es todo hasta el título de la sección inclusive,
    `pendiente` el texto libre antes de la primera subsección, `notas` un dict {"App": texto, "Servidor": texto} con
    lo que hay bajo «### App» y «### Servidor» (solo las que tienen contenido) y `resto` desde la siguiente «## ».
    """
    m = re.search(r"^## Sin publicar[ \t]*\r?\n", historial, re.M)
    if not m:
        raise ValueError("CHANGELOG.md no tiene la sección «## Sin publicar».")
    fin = re.search(r"^## ", historial[m.end():], re.M)
    corte = m.end() + fin.start() if fin else len(historial)
    partes = re.split(r"^### (App|Servidor)[ \t]*\r?\n", historial[m.end():corte], flags=re.M)
    notas = {}
    for nombre, texto in zip(partes[1::2], partes[2::2]):
        if nombre in notas:
            raise ValueError(f"«Sin publicar» tiene dos subsecciones «### {nombre}».")
        if texto.strip():
            notas[nombre] = texto
    return historial[:m.end()], partes[0], notas, historial[corte:]


def ultimas_etiquetas(raiz=RAIZ):
    """{"App": "1.28", "Servidor": "2026.11.15"} según las etiquetas app-v… / servidor-v… del repositorio.

    Vacío si no hay git, no es un repositorio o no se bajaron las etiquetas (el CI clona sin ellas): en ese caso
    las comprobaciones contra la última entrega se omiten.
    """
    try:
        r = subprocess.run(["git", "tag", "--list", "app-v*", "servidor-v*"], cwd=raiz, capture_output=True,
                           text=True, timeout=10, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.SubprocessError):
        return {}
    if r.returncode != 0:
        return {}
    ultimas = {}
    for etiqueta in r.stdout.split():
        for nombre, prefijo in PREFIJOS.items():
            version = etiqueta[len(prefijo):] if etiqueta.startswith(prefijo) else ""
            if re.fullmatch(FORMATO[nombre], version) and (
                    nombre not in ultimas or numeros(version) > numeros(ultimas[nombre])):
                ultimas[nombre] = version
    return ultimas


def comprobar(raiz=RAIZ, sin_binario=False, entrega=False, etiquetas=None):
    """Lista de errores (vacía si todo está bien), versión de la app y del servidor.

    `etiquetas`: últimas versiones publicadas ({"App": …, "Servidor": …}); None = leerlas de git en `raiz`.
    """
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
    versiones = {"App": app, "Servidor": actual}
    for nombre, version in versiones.items():
        if not version:
            continue
        if not re.fullmatch(FORMATO[nombre], version):
            esquema = "MAYOR.MENOR[.PARCHE]" if nombre == "App" else "AAAA.M.N"
            errores.append(f"{nombre} {version}: no sigue el esquema {esquema}.")
            versiones[nombre] = None
            continue
        fecha = re.search(r'^## \[(?:' + nombre + r' )?' + re.escape(version)
                          + r'\] — (\d{4})-(\d{2})-\d{2}\s*$', historial, re.MULTILINE)
        if not fecha:
            errores.append(f"Falta la entrada fechada de {nombre} {version} en CHANGELOG.md.")
        elif nombre == "Servidor" and numeros(version)[:2] != (int(fecha.group(1)), int(fecha.group(2))):
            errores.append(f"Servidor {version}: el año y mes no coinciden con la fecha de su entrada en CHANGELOG.md "
                           f"({fecha.group(1)}-{fecha.group(2)}).")
    if etiquetas is None:
        etiquetas = ultimas_etiquetas(raiz)
    for nombre, version in versiones.items():
        publicada = etiquetas.get(nombre)
        if version and publicada and numeros(version) < numeros(publicada):
            errores.append(f"{nombre} {version} es anterior a la última entrega publicada ({publicada}).")
    if entrega:
        try:
            notas = sin_publicar(historial)[2]
        except ValueError as ex:
            errores.append(str(ex))
            notas = {}
        for nombre in notas:
            errores.append(f"Quedaron notas de {nombre} en «Sin publicar»: la entrega incluye todo lo fusionado "
                           "(herramientas/subir_version.py las pasa a la entrada fechada).")
        nuevas = [n for n, v in versiones.items() if v and etiquetas.get(n) and numeros(v) > numeros(etiquetas[n])]
        if etiquetas and not nuevas:
            errores.append("Ninguna versión es posterior a la última entrega publicada: no hay nada que entregar.")
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
    parser.add_argument("--entrega", action="store_true",
                        help="Rama release/…: versiones nuevas y «Sin publicar» sin notas de App ni Servidor.")
    args = parser.parse_args()
    try:
        errores, app, servidor = comprobar(sin_binario=args.sin_binario, entrega=args.entrega)
    except (OSError, UnicodeError) as exc:
        parser.exit(1, f"No se pudo verificar: {exc}\n")
    for error in errores:
        print("ERROR: " + error)
    if errores:
        return 1
    alcance = "solo fuentes" if args.sin_binario else "fuentes, ejecutable y manifiesto"
    if args.entrega:
        alcance += "; entrega lista"
    print(f"Versiones OK: app {app}; servidor {servidor} ({alcance}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
