# -*- coding: utf-8 -*-
"""
ACTUALIZACION DE LA APP DEL TRABAJO (Transcripcion.exe)

La carpeta sistema\\cliente es "la version oficial" de la app. Cada PC del trabajo compara cada
10 s la huella de esa carpeta (viene en /api/cliente/estado) con la de sus propios archivos;
si cambio algo, pide el manifiesto, baja solo los archivos distintos, los prueba y se reemplaza
sola cuando nadie la esta usando. Para actualizar todas las PC alcanza con poner el
Transcripcion.exe nuevo en sistema\\cliente (con el servidor andando o no).

Solo se ofrecen estos archivos (nunca otra cosa de la carpeta):
  Transcripcion.exe, Transcripcion.exe.config, LEEME.txt, conexion.json y las .dll (incluida runtimes\\).
"""
import hashlib
import re
import threading
import time
from pathlib import Path

import registro as L

AQUI = Path(__file__).resolve().parent
CARPETA = AQUI / "cliente"
FIJOS = {"transcripcion.exe", "transcripcion.exe.config", "leeme.txt", "conexion.json"}
_lock = threading.Lock()
_CACHE = {"firma": None, "t": 0, "man": None}
VERSION_PC = {}          # pc -> version de la app que usa (segun su User-Agent)
_UA = re.compile(r"Transcripcion/([0-9][0-9.]{0,15})")


def _ofrecido(rel):
    p = rel.lower()
    if any(x.startswith(".") for x in p.split("/")):
        return False
    if any(m in p for m in (".viejo", ".nuevo", ".fallida")):
        return False
    return p in FIJOS or p.endswith(".dll")


def _sha(ruta):
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def version_exe(ruta):
    """Lee la 'FileVersion' que trae el .exe (ej. 1.2.0.0 -> '1.2'). '' si no la encuentra."""
    try:
        datos = Path(ruta).read_bytes()
    except OSError:
        return ""
    i = datos.find("FileVersion".encode("utf-16-le") + b"\x00\x00")
    if i < 0:
        return ""
    i += len("FileVersion") * 2 + 2
    while i < len(datos) - 1 and datos[i:i + 2] == b"\x00\x00":
        i += 2
    fin = i
    while fin < len(datos) - 1 and datos[fin:fin + 2] != b"\x00\x00" and fin - i < 64:
        fin += 2
    v = datos[i:fin].decode("utf-16-le", "replace").strip()
    if not re.fullmatch(r"[0-9]+(\.[0-9]+){0,3}", v):
        return ""
    partes = v.split(".")
    while len(partes) > 2 and partes[-1] == "0":
        partes.pop()
    return ".".join(partes)


def manifiesto():
    """{'version', 'huella', 'archivos': [{'ruta', 'sha256', 'tam'}]} de sistema\\cliente.
    Se recalcula solo si cambio algun archivo (tamano o fecha), revisando como mucho cada 5 s."""
    with _lock:
        ahora = time.time()
        if _CACHE["man"] is not None and ahora - _CACHE["t"] < 5:
            return _CACHE["man"]
        _CACHE["t"] = ahora
        lista = []
        if CARPETA.is_dir():
            for p in CARPETA.rglob("*"):
                if p.is_file():
                    rel = p.relative_to(CARPETA).as_posix()
                    if _ofrecido(rel):
                        st = p.stat()
                        lista.append((rel, st.st_size, st.st_mtime_ns, p))
        lista.sort(key=lambda x: x[0].lower())
        firma = tuple(x[:3] for x in lista)
        if firma == _CACHE["firma"] and _CACHE["man"] is not None:
            return _CACHE["man"]
        archivos = []
        for rel, tam, _, p in lista:
            try:
                archivos.append({"ruta": rel, "sha256": _sha(p), "tam": tam})
            except OSError:      # se esta copiando justo ahora: se vuelve a intentar en 5 s
                _CACHE["t"] = 0
                return _CACHE["man"] or {"version": "", "huella": "", "archivos": []}
        exe = CARPETA / "Transcripcion.exe"
        man = {"version": version_exe(exe) if exe.exists() else "",
               "huella": huella_de(archivos), "archivos": archivos}
        if _CACHE["man"] is not None and _CACHE["man"]["huella"] != man["huella"] and archivos:
            L.ok("APP", f"Hay una versión nueva de la app del trabajo ({man['version'] or 'sin número'}): "
                        f"las PC se actualizan solas cuando nadie la está usando.")
        _CACHE["firma"], _CACHE["man"] = firma, man
        return man


def huella_de(archivos):
    """Huella de todo el conjunto (la misma cuenta hace la app con sus archivos)."""
    texto = "".join(f"{a['ruta'].lower()}:{a['sha256']}\n" for a in sorted(archivos, key=lambda a: a["ruta"].lower()))
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def resumen():
    """Lo que va dentro de /api/cliente/estado."""
    m = manifiesto()
    return {"version": m["version"], "huella": m["huella"]}


def archivo(rel):
    """Ruta del archivo pedido, solo si esta en el manifiesto."""
    for a in manifiesto()["archivos"]:
        if a["ruta"] == rel:
            return CARPETA / rel
    return None


def anotar_version(pc, user_agent):
    m = _UA.search(user_agent or "")
    if not m or not pc:
        return
    v = m.group(1)
    antes = VERSION_PC.get(pc)
    VERSION_PC[pc] = v
    if antes and antes != v:
        L.ok("APP", f"{pc} se actualizó: versión {antes} → {v}.")
    elif not antes:
        L.debug("APP", f"{pc} usa la app versión {v}.")


def texto_panel():
    """Renglón del encabezado de la ventana del servidor."""
    m = manifiesto()
    if not m["archivos"]:
        return None
    v = m["version"] or "?"
    pcs = ", ".join(f"{p} {x}" for p, x in sorted(VERSION_PC.items()))
    return f"versión {v} en sistema\\cliente" + (f" · {pcs}" if pcs else "")
