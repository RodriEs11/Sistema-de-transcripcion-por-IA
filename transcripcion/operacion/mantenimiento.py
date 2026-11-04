# -*- coding: utf-8 -*-
"""
MANTENIMIENTO (panel de administración, tarjeta "Mantenimiento").

- Qué versión de cada archivo de Python cargó el servidor y cuáles cambiaron después en la carpeta
  ("cambios sin tomar": hace falta reiniciar el servidor para que los use).
- Versión del código según git (commit y archivos sin commitear). Usa git si está instalado; si no, lee la
  carpeta .git directamente (solo lo básico).
- Si el servidor se puede reiniciar desde el panel (lo abrió un .bat que lo vuelve a abrir solo) y una prueba
  del código nuevo antes de reiniciar, para no dejar el servidor apagado por un error.

Las páginas (web\\*.html), las plantillas y las reglas se leen en cada pedido: no necesitan reiniciar.
"""
import hashlib
import os
import re
import struct
import subprocess
import sys
import threading
import time
import zlib
from pathlib import Path

from transcripcion import RAIZ
from transcripcion.base import plataforma as P

AQUI = RAIZ          # carpeta del sistema (no la del paquete)
GIT = AQUI / ".git"
CODIGO_REINICIO = 75          # el .bat vuelve a abrir el servidor cuando termina con este código
MARCA_BAT = "REINICIO-DESDE-EL-PANEL"
EXTRA = ("configuracion.json",)       # se lee solo al arrancar
_SIN_VENTANA = getattr(subprocess, "CREATE_NO_WINDOW", 0)

_lock = threading.Lock()
CARGADO = {}          # "servidor.py", "transcripcion/base/registro.py" -> {"hash", "t"}: versión que usa el servidor
_LOCALES = {}         # módulo del sistema -> archivo ("transcripcion.base.registro" -> "transcripcion/base/registro.py")
PAQUETE = "transcripcion"   # paquete con los módulos del sistema (docs/refactor.md)
_HASH = {}            # ruta -> ((tamaño, mtime), hash): no volver a leer archivos que no cambiaron
_ARRANQUE = {"titulo": None, "git": None, "t": None}
_CACHE_GIT = {"t": 0, "v": None}


# ------------------------------------------------------------------ huellas
def _huella(p):
    try:
        st = p.stat()
    except OSError:
        return None
    firma = (st.st_size, st.st_mtime_ns)
    c = _HASH.get(p)
    if c and c[0] == firma:
        return c[1]
    try:
        h = hashlib.sha1(p.read_bytes()).hexdigest()
    except OSError:
        return None
    _HASH[p] = (firma, h)
    return h


def modulos_locales():
    """Módulos del sistema y su archivo relativo: los .py de esta carpeta y los del paquete (no los de .venv,
    respaldo ni pruebas)."""
    out = {p.stem: p.name for p in AQUI.glob("*.py")}
    for p in sorted((AQUI / PAQUETE).rglob("*.py")):
        rel = p.relative_to(AQUI)
        partes = rel.with_suffix("").parts
        nombre = ".".join(partes[:-1] if partes[-1] == "__init__" else partes)
        out[nombre] = rel.as_posix()
    return out


def _archivo_local(f):
    """Ruta relativa (posix) si el archivo `f` es código del sistema; None si es de otro lado."""
    try:
        rel = Path(f).resolve().relative_to(AQUI)
    except (OSError, ValueError):
        return None
    if rel.suffix != ".py" or not (len(rel.parts) == 1 or rel.parts[0] == PAQUETE):
        return None
    return rel.as_posix()


def _anotar(nombre):
    with _lock:
        if nombre in CARGADO:
            return
    h = _huella(AQUI / nombre)
    if h:
        with _lock:
            CARGADO.setdefault(nombre, {"hash": h, "t": time.time()})


def _gancho(evento, args):
    """Se llama en cada import que carga un módulo nuevo: anota la versión de los de esta carpeta que se
    cargan tarde (aprender, transcripcion.asr.huecos y whisper... se importan recién cuando se usan)."""
    if evento != "import":
        return
    try:
        archivo = _LOCALES.get(args[0])
        if archivo and archivo not in CARGADO:
            _anotar(archivo)
    except Exception:
        pass


def empezar(titulo_consola=None):
    """Al arrancar el servidor (main): anota lo que ya está cargado y vigila lo que se cargue después."""
    _ARRANQUE.update(titulo=titulo_consola, t=time.time())
    _LOCALES.update(modulos_locales())
    for m in list(sys.modules.values()):
        f = getattr(m, "__file__", None)
        archivo = _archivo_local(f) if f else None
        if archivo:
            _anotar(archivo)
    for x in EXTRA:
        if (AQUI / x).exists():
            _anotar(x)
    sys.addaudithook(_gancho)
    try:
        _ARRANQUE["git"] = info_git(forzar=True)
    except Exception:
        _ARRANQUE["git"] = None


def cambios_sin_tomar():
    """Archivos que el servidor cargó y que cambiaron (o se borraron) en la carpeta después."""
    out = []
    with _lock:
        cargados = dict(CARGADO)
    for nombre, v in sorted(cargados.items()):
        p = AQUI / nombre
        h = _huella(p)
        if h == v["hash"]:
            continue
        try:
            mt = p.stat().st_mtime
        except OSError:
            mt = None
        out.append({"archivo": nombre, "estado": "borrado" if h is None else "modificado", "modificado": mt,
                    "cargado": v["t"]})
    return out


# ---------------------------------------------------------------------- git
def _git(*args, timeout=6):
    r = subprocess.run(["git", "-c", "core.quotepath=off", *args], cwd=AQUI, capture_output=True, timeout=timeout,
                       creationflags=_SIN_VENTANA)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.decode("utf-8", "replace").strip()[:200] or f"git terminó con {r.returncode}")
    return r.stdout.decode("utf-8", "replace")


def _git_cli():
    sal = _git("log", "-1", "--format=%H%x1f%h%x1f%ct%x1f%s").strip()
    if not sal:
        return None
    completo, corto, t, msg = (sal.split("\x1f") + ["", "", "", ""])[:4]
    try:
        rama = _git("rev-parse", "--abbrev-ref", "HEAD").strip()
    except Exception:
        rama = None
    sucios = []
    for ln in _git("status", "--porcelain", "--untracked-files=no").splitlines():
        if len(ln) > 3:
            ruta = ln[3:].strip().strip('"')
            sucios.append(ruta.split(" -> ")[-1])
    nuevos = [ln[3:].strip().strip('"') for ln in _git("status", "--porcelain").splitlines() if ln.startswith("??")]
    return {"commit": corto, "completo": completo, "fecha": int(t) if t.isdigit() else None, "mensaje": msg,
            "rama": rama, "sucios": sucios, "sin_seguimiento": nuevos, "fuente": "git"}


def _leer_ref(ref):
    f = GIT / ref
    if f.is_file():
        return f.read_text(encoding="utf-8").strip()
    pk = GIT / "packed-refs"
    if pk.is_file():
        for ln in pk.read_text(encoding="utf-8").splitlines():
            partes = ln.split()
            if len(partes) == 2 and partes[1] == ref:
                return partes[0]
    return None


def _objeto(sha):
    f = GIT / "objects" / sha[:2] / sha[2:]
    if not f.is_file():
        return None                      # guardado en un "pack": git lo comprime junto con otros
    return zlib.decompress(f.read_bytes())


def _indice():
    """Entradas de .git/index (versiones 2 y 3): ruta -> sha1 del contenido."""
    d = (GIT / "index").read_bytes()
    if d[:4] != b"DIRC":
        return {}
    ver, n = struct.unpack(">II", d[4:12])
    if ver not in (2, 3):
        return {}
    pos, out = 12, {}
    for _ in range(n):
        sha = d[pos + 40:pos + 60].hex()
        flags = struct.unpack(">H", d[pos + 60:pos + 62])[0]
        ini = pos + 62 + (2 if (ver == 3 and flags & 0x4000) else 0)
        fin = d.index(b"\0", ini)
        out[d[ini:fin].decode("utf-8", "replace")] = sha
        largo = fin - pos + 1
        pos += (largo + 7) // 8 * 8
    return out


def _blob(datos):
    return hashlib.sha1(b"blob %d\0" % len(datos) + datos).hexdigest()


def _git_archivos():
    """Sin el programa git: commit actual y archivos modificados, leyendo .git a mano."""
    head = (GIT / "HEAD").read_text(encoding="utf-8").strip()
    rama, sha = None, head
    if head.startswith("ref: "):
        ref = head[5:]
        rama = ref.rsplit("/", 1)[-1]
        sha = _leer_ref(ref)
    if not sha:
        return None
    msg, t = "", None
    obj = _objeto(sha)
    if obj:
        cuerpo = obj.split(b"\0", 1)[1].decode("utf-8", "replace")
        cab, _, resto = cuerpo.partition("\n\n")
        msg = resto.strip().splitlines()[0] if resto.strip() else ""
        m = re.search(r"^committer .* (\d+) [+-]\d{4}$", cab, re.M)
        t = int(m.group(1)) if m else None
    sucios = []
    try:
        for ruta, h in _indice().items():
            p = AQUI / ruta
            try:
                datos = p.read_bytes()
            except OSError:
                sucios.append(ruta)
                continue
            if _blob(datos) != h and (b"\r\n" not in datos or _blob(datos.replace(b"\r\n", b"\n")) != h):
                sucios.append(ruta)          # (git guarda los textos con fin de línea LF aunque en la carpeta estén con CRLF)
    except (OSError, ValueError, struct.error):
        sucios = None
    return {"commit": sha[:7], "completo": sha, "fecha": t, "mensaje": msg, "rama": rama, "sucios": sucios,
            "sin_seguimiento": None, "fuente": "archivos"}


def info_git(forzar=False):
    """Versión del código en la carpeta (cacheada 15 s)."""
    if not forzar and time.time() - _CACHE_GIT["t"] < 15:
        return _CACHE_GIT["v"]
    if not GIT.is_dir():
        v = {"error": "La carpeta sistema no es un repositorio de git."}
    else:
        try:
            v = _git_cli()
        except (OSError, subprocess.SubprocessError, RuntimeError) as ex:
            try:
                v = _git_archivos()
                if v is not None and isinstance(ex, FileNotFoundError):
                    v["aviso"] = "git no está instalado en esta PC: se leyó la carpeta .git directamente."
            except Exception as ex2:
                v = {"error": f"No se pudo leer la versión: {ex2}"}
    _CACHE_GIT.update(t=time.time(), v=v)
    return v


def git_al_arrancar():
    return _ARRANQUE["git"]


# ------------------------------------------------------------------- reinicio
def bat_del_modo(tunel):
    """El script que abrió el servidor: iniciar_servidor / interfaz (.bat en Windows, .sh en Linux)."""
    return AQUI / P.script("iniciar_servidor" if tunel else "interfaz")


def soporta_reinicio(tunel):
    """(True, None) si el servidor se puede reiniciar desde el panel: lo abrió el .bat (que lo vuelve a abrir
    cuando termina con el código 75). Si no, (False, motivo)."""
    if os.environ.get("REINICIO_BUCLE") == "1":       # pruebas: un script que hace lo mismo que el .bat
        return True, None
    bat = bat_del_modo(tunel)
    if not P.ES_WINDOWS:
        # Linux: los .sh (y el servicio de systemd) avisan con esta variable que vuelven a abrir el servidor
        if os.environ.get("TRANSCRIPCION_REINICIO") != "1":
            return False, (f"El servidor no se abrió con {bat.name} (ni como servicio): cerralo y abrilo con "
                           f"./{bat.name} para poder reiniciarlo desde acá.")
        return True, None
    t = _ARRANQUE["titulo"] or ""
    if not (t.lower().startswith("transcripcion - ") or t.startswith("Transcripción · Servidor")):
        return False, (f"El servidor no se abrió con {bat.name}: cerralo y abrilo con {bat.name} para poder "
                       f"reiniciarlo desde acá.")
    try:
        if MARCA_BAT not in bat.read_text(encoding="utf-8", errors="replace"):
            return False, f"{bat.name} es de una versión anterior: no vuelve a abrir el servidor solo."
    except OSError:
        return False, f"No encuentro {bat.name}."
    return True, None


def titulo_consola():
    """Título de la ventana del servidor al arrancar (lo pone el .bat). En Windows."""
    if os.name != "nt":
        return None
    try:
        import ctypes
        buf = ctypes.create_unicode_buffer(512)
        ctypes.windll.kernel32.GetConsoleTitleW(buf, 512)
        return buf.value
    except Exception:
        return None


PRUEBA = r"""
import glob, py_compile, sys
for f in sorted(glob.glob("*.py")) + sorted(glob.glob("transcripcion/**/*.py", recursive=True)):
    try:
        py_compile.compile(f, doraise=True)
    except py_compile.PyCompileError as ex:
        print("ERROR_SINTAXIS", f, file=sys.stderr)
        print(ex.msg, file=sys.stderr)
        sys.exit(3)
from transcripcion import ajustes
ajustes.cargar(crear_config=False)   # configuracion.json legible (importar el servidor ya no la lee)
import servidor
print("ok")
"""


def prueba_de_arranque(timeout=120):
    """Prueba el código de la carpeta en otro proceso (compila todos los .py, también los del paquete, lee la
    configuración e importa el servidor) antes de reiniciar. Devuelve None si anda o el error (últimas líneas)."""
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1")
    try:
        r = subprocess.run([sys.executable, "-X", "utf8", "-c", PRUEBA], cwd=AQUI, capture_output=True,
                           timeout=timeout, env=env, creationflags=_SIN_VENTANA)
    except subprocess.TimeoutExpired:
        return "La prueba del código nuevo tardó demasiado (más de 2 minutos)."
    except OSError as ex:
        return f"No se pudo probar el código nuevo: {ex}"
    if r.returncode == 0 and b"ok" in r.stdout:
        return None
    err = r.stderr.decode("utf-8", "replace").strip().splitlines()
    return "\n".join(err[-12:]) or f"La prueba terminó con el código {r.returncode}."
