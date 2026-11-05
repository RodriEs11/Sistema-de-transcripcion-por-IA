"""Prepara una entrega: sube las versiones de la app y/o del servidor en todos sus lugares (ver docs/versiones.md).

Uso, desde la carpeta del sistema y en la rama release/…:

    python herramientas/subir_version.py --app menor --servidor --leeme "Texto corto para quien usa la app."
    python herramientas/subir_version.py --servidor
    python herramientas/subir_version.py --app parche --leeme "…" --sin-escribir    (muestra qué haría)

Qué cambia:
- cliente_codigo/Programa.cs: VERSION, AssemblyVersion y AssemblyFileVersion, juntos.
- servidor.py: VERSION (AAAA.M.N con la fecha de Buenos Aires; N se reinicia cada mes).
- CHANGELOG.md: pasa las notas de «Sin publicar» (### App / ### Servidor) a entradas fechadas.
- cliente/LEEME.txt: versión actual, fecha y la línea para quien usa la app.

No compila, no hace commits ni etiquetas: eso sigue los pasos de docs/versiones.md.
"""
import argparse
import re
import sys
import textwrap
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from verificar_versiones import FORMATO, RAIZ, sin_publicar  # noqa: E402

# Argentina no usa horario de verano. Un desplazamiento fijo evita depender de tzdata (zoneinfo en Windows).
BUENOS_AIRES = timezone(timedelta(hours=-3), "Buenos Aires")
PASOS = ("parche", "menor", "mayor")
PROGRAMA, SERVIDOR, HISTORIAL, LEEME = "cliente_codigo/Programa.cs", "servidor.py", "CHANGELOG.md", "cliente/LEEME.txt"


class ErrorEntrega(Exception):
    """La entrega no se puede preparar así; el mensaje dice por qué."""


def hoy():
    return datetime.now(BUENOS_AIRES).date()


def siguiente_app(actual, paso):
    """1.28 -> parche 1.28.1 · menor 1.29 · mayor 2.0 (versionado semántico)."""
    if not re.fullmatch(FORMATO["App"], actual):
        raise ErrorEntrega(f"La versión actual de la app ({actual}) no sigue MAYOR.MENOR[.PARCHE].")
    mayor, menor, parche = (int(x) for x in (actual.split(".") + ["0"])[:3])
    if paso == "mayor":
        return f"{mayor + 1}.0"
    if paso == "menor":
        return f"{mayor}.{menor + 1}"
    if paso == "parche":
        return f"{mayor}.{menor}.{parche + 1}"
    raise ErrorEntrega(f"Paso desconocido: {paso} (usar {', '.join(PASOS)}).")


def siguiente_servidor(actual, fecha):
    """2026.11.15 -> 2026.11.16 en el mismo mes; 2026.12.1 al cambiar de mes."""
    if not re.fullmatch(FORMATO["Servidor"], actual):
        raise ErrorEntrega(f"La versión actual del servidor ({actual}) no sigue AAAA.M.N.")
    anio, mes, n = (int(x) for x in actual.split("."))
    if (fecha.year, fecha.month) == (anio, mes):
        return f"{anio}.{mes}.{n + 1}"
    if (fecha.year, fecha.month) < (anio, mes):
        raise ErrorEntrega(f"La fecha {fecha.isoformat()} es anterior al mes de la versión actual ({actual}).")
    return f"{fecha.year}.{fecha.month}.1"


def para_ensamblado(version):
    """1.29 -> 1.29.0.0; 1.28.1 -> 1.28.1.0 (AssemblyVersion y AssemblyFileVersion)."""
    partes = version.split(".")
    return ".".join(partes + ["0"] * (4 - len(partes)))


def _leer(ruta):
    datos = ruta.read_bytes()
    return datos.decode("utf-8-sig"), datos.startswith(b"\xef\xbb\xbf")


def _guardar(ruta, texto, bom):
    ruta.write_bytes((b"\xef\xbb\xbf" if bom else b"") + texto.encode("utf-8"))


def _actual(patron, texto, nombre, flags=0):
    """Valor (grupo 2) de la única coincidencia de `patron`."""
    encontrados = re.findall(patron, texto, flags)
    if len(encontrados) != 1:
        raise ErrorEntrega(f"{nombre}: se esperaba una única definición y hay {len(encontrados)}.")
    return encontrados[0][1]


def _poner(patron, texto, valor, nombre, flags=0):
    """Cambia el grupo 2 de la única coincidencia de `patron`; los grupos 1 y 3 quedan igual."""
    _actual(patron, texto, nombre, flags)
    return re.sub(patron, lambda m: m.group(1) + valor + m.group(3), texto, flags=flags)


def _entrada(nombre, version, fecha, acompania, notas):
    cabecera = f"## [{nombre} {version}] — {fecha.isoformat()}\n\n" + (f"{acompania}\n\n" if acompania else "")
    cuerpo = re.sub(r"^#### ", "### ", notas.strip("\r\n"), flags=re.M)  # en «Sin publicar» las categorías son ####
    return cabecera + cuerpo + "\n\n"


def _linea_leeme(prefijo, texto):
    return textwrap.fill(f"{prefijo}: {texto.strip()}", width=118, break_long_words=False, break_on_hyphens=False)


def subir(raiz=RAIZ, app=None, servidor=False, fecha=None, leeme=None, escribir=True):
    """Prepara la entrega. `app`: None o uno de PASOS. Devuelve {"App": (antes, después), "Servidor": (…)} con lo
    que se subió. Con escribir=False no toca ningún archivo (sirve para ver qué haría)."""
    if not app and not servidor:
        raise ErrorEntrega("Indicar qué se entrega: --app parche|menor|mayor y/o --servidor.")
    if app and not (leeme and leeme.strip()):
        raise ErrorEntrega("Una entrega de la app necesita --leeme con una línea para quien la usa (va en LEEME.txt).")
    fecha = fecha or hoy()
    rutas = {n: raiz / n for n in (PROGRAMA, SERVIDOR, HISTORIAL, LEEME)}
    textos = {n: _leer(r) for n, r in rutas.items()}
    nuevos = {}
    subidas = {}

    inicio, pendiente, notas, resto = sin_publicar(textos[HISTORIAL][0])
    componentes = {"App": bool(app), "Servidor": servidor}
    for nombre, entra in componentes.items():
        if entra and nombre not in notas:
            raise ErrorEntrega(f"No hay notas de {nombre} en «Sin publicar» de CHANGELOG.md: ¿qué cambia en esta entrega?")
        if not entra and nombre in notas:
            opcion = "--app parche|menor|mayor" if nombre == "App" else "--servidor"
            raise ErrorEntrega(f"Hay notas de {nombre} en «Sin publicar»: lo fusionado entra en esta entrega, así que "
                               f"también sube su versión ({opcion}).")

    if app:
        codigo = textos[PROGRAMA][0]
        patron = r'(public const string VERSION = ")([0-9.]+)(";)'
        antes = _actual(patron, codigo, "Programa.VERSION")
        despues = siguiente_app(antes, app)
        codigo = _poner(patron, codigo, despues, "Programa.VERSION")
        for atributo in ("AssemblyVersion", "AssemblyFileVersion"):
            patron = r'(\[assembly: System\.Reflection\.' + atributo + r'\(")([0-9.]+)("\)\])'
            codigo = _poner(patron, codigo, para_ensamblado(despues), atributo)
        nuevos[PROGRAMA] = codigo
        subidas["App"] = (antes, despues)
    if servidor:
        texto = textos[SERVIDOR][0]
        patron = r'^(VERSION = ")([0-9.]+)(")'
        antes = _actual(patron, texto, "Servidor.VERSION", re.M)
        despues = siguiente_servidor(antes, fecha)
        nuevos[SERVIDOR] = _poner(patron, texto, despues, "Servidor.VERSION", re.M)
        subidas["Servidor"] = (antes, despues)

    entradas = ""
    if "App" in subidas:
        acompania = f"Acompaña al Servidor {subidas['Servidor'][1]}." if "Servidor" in subidas else ""
        entradas += _entrada("App", subidas["App"][1], fecha, acompania, notas["App"])
    if "Servidor" in subidas:
        acompania = f"Acompaña a la App {subidas['App'][1]}." if "App" in subidas else ""
        entradas += _entrada("Servidor", subidas["Servidor"][1], fecha, acompania, notas["Servidor"])
    pendiente = pendiente.strip("\r\n")
    nuevos[HISTORIAL] = inicio + "\n" + (pendiente + "\n\n" if pendiente else "") + entradas + resto.lstrip("\r\n")

    texto = textos[LEEME][0]
    actual = re.search(r"^Versión actual: [0-9.]+ \(\d{4}-\d{2}-\d{2}\)\.[ \t]*$", texto, re.M)
    if not actual:
        raise ErrorEntrega("LEEME.txt no tiene la línea «Versión actual: X (AAAA-MM-DD).».")
    if "App" in subidas:
        version = subidas["App"][1]
        prefijo = version + (f" / Servidor {subidas['Servidor'][1]}" if "Servidor" in subidas else "")
        linea = f"Versión actual: {version} ({fecha.isoformat()}).\n" + _linea_leeme(prefijo, leeme)
        texto = texto[:actual.start()] + linea + texto[actual.end():]
    elif leeme and leeme.strip():
        prefijo = f"Servidor {subidas['Servidor'][1]} ({fecha.isoformat()})"
        texto = texto[:actual.end()] + "\n" + _linea_leeme(prefijo, leeme) + texto[actual.end():]
    nuevos[LEEME] = texto

    if escribir:
        for nombre, texto in nuevos.items():
            if texto != textos[nombre][0]:
                _guardar(rutas[nombre], texto, textos[nombre][1])
    return subidas


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--app", choices=PASOS, help="Sube la app: parche (correcciones), menor (funciones nuevas o "
                                                     "cambios visibles) o mayor (rompe compatibilidad).")
    parser.add_argument("--servidor", action="store_true", help="Sube el servidor al siguiente AAAA.M.N.")
    parser.add_argument("--leeme", help="Línea para LEEME.txt (obligatoria con --app; opcional solo con --servidor).")
    parser.add_argument("--fecha", type=date.fromisoformat, help="AAAA-MM-DD; por omisión, hoy en Buenos Aires.")
    parser.add_argument("--sin-escribir", action="store_true", help="Solo muestra las versiones nuevas.")
    args = parser.parse_args()
    try:
        subidas = subir(app=args.app, servidor=args.servidor, fecha=args.fecha, leeme=args.leeme,
                        escribir=not args.sin_escribir)
    except (ErrorEntrega, ValueError, OSError) as ex:
        parser.exit(1, f"ERROR: {ex}\n")
    for nombre, (antes, despues) in subidas.items():
        print(f"{nombre}: {antes} -> {despues}")
    if args.sin_escribir:
        print("(sin escribir: no se cambió ningún archivo)")
        return 0
    print("Actualizados Programa.cs/servidor.py, CHANGELOG.md y LEEME.txt. Revisar el diff y seguir con "
          "docs/versiones.md: compilar si cambió la app y `python herramientas/verificar_versiones.py --entrega`.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
