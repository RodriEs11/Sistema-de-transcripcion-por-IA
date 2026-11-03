# -*- coding: utf-8 -*-
"""
TRANSCRIPTORES: cada persona entra con su usuario y su contraseña, y tiene su propio estilo.

- usuarios.json (junto a este archivo, no se versiona): nombre, huella PBKDF2 de la contraseña, si está activo
  y si tiene que cambiar la contraseña (la inicial la pone el administrador desde el panel).
- conocimiento/usuarios/<clave>/: el estilo de cada transcriptor, en capas sobre lo general.
    plantillas.md           solo las secciones que cambió (mismo formato «## NOMBRE»); reemplazan a la general
    medicos/<Médico>.md     sus notas de cómo dicta ese médico (reemplazan a las generales)
    reglas_dictado.md       reglas propias: se SUMAN a las generales
    correcciones_aprendidas.md   se genera solo (aprender.py)
    formato.json            fuente, tamaño, renglones de encabezado... del Word (sobre configuracion.json)
    preferencias.json       preferencias de la pantalla (tema, atajos, velocidad...): siguen al usuario, no a la PC

Mientras no haya ningún transcriptor creado, el sistema funciona como antes (sin pedir usuario).
"""
import hashlib
import hmac
import json
import re
import secrets
import threading
import time
import unicodedata
from pathlib import Path

from persistencia import escribir_atomico

AQUI = Path(__file__).resolve().parent
ARCH = AQUI / "usuarios.json"
CARPETA = AQUI / "conocimiento" / "usuarios"
MIN_CONTRASENA = 6
_lock = threading.RLock()
_CACHE = {"mt": None, "d": None}


# ---------------------------------------------------------------- datos
def _leer():
    with _lock:
        try:
            mt = ARCH.stat().st_mtime_ns
        except FileNotFoundError:
            return {"usuarios": {}}
        if _CACHE["mt"] != mt:
            try:
                d = json.loads(ARCH.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                d = {}
            d.setdefault("usuarios", {})
            _CACHE.update(mt=mt, d=d)
        return json.loads(json.dumps(_CACHE["d"]))      # copia: nadie modifica la caché por error


def _grabar(d):
    with _lock:
        escribir_atomico(ARCH, json.dumps(d, ensure_ascii=False, indent=1))
        _CACHE.update(mt=None, d=None)


def _huella(c, sal):
    return hashlib.pbkdf2_hmac("sha256", c.encode("utf-8"), bytes.fromhex(sal), 200_000).hex()


def clave_de(nombre):
    """«María José Pérez» → «maria-jose-perez» (nombre de carpeta seguro y estable)."""
    t = unicodedata.normalize("NFKD", str(nombre or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-")[:40]


def validar_nombre(nombre):
    if not isinstance(nombre, str):
        raise ValueError("Escribí el nombre del transcriptor.")
    nombre = " ".join(nombre.split())
    if len(nombre) < 2 or len(nombre) > 60 or not any(c.isalpha() for c in nombre) or re.search(r"[^\w .'-]", nombre):
        raise ValueError("Usá un nombre de 2 a 60 caracteres, con letras y sin símbolos especiales.")
    if len(clave_de(nombre)) < 2:
        raise ValueError("El nombre tiene que tener al menos dos letras comunes (sin acentos alcanza).")
    return nombre


def validar_contrasena(c):
    if not isinstance(c, str) or len(c) < MIN_CONTRASENA:
        raise ValueError(f"La contraseña tiene que tener al menos {MIN_CONTRASENA} caracteres.")
    if len(c) > 200:
        raise ValueError("La contraseña es demasiado larga.")
    return c


def hay_usuarios():
    """True si hay al menos un transcriptor activo: desde ahí se pide usuario para usar la página."""
    return any(u.get("activo", True) for u in _leer()["usuarios"].values())


def existe(clave):
    u = _leer()["usuarios"].get(clave or "")
    return bool(u and u.get("activo", True))


def nombre_de(clave):
    if not clave:
        return ""
    u = _leer()["usuarios"].get(clave)
    return u["nombre"] if u else clave


def datos(clave):
    u = _leer()["usuarios"].get(clave or "")
    if not u:
        return None
    return {"clave": clave, "nombre": u["nombre"], "activo": u.get("activo", True), "cambiar": bool(u.get("cambiar")),
            "creado": u.get("creado"), "ultima": u.get("ultima")}


def lista(incluir_inactivos=True):
    out = [datos(k) for k in _leer()["usuarios"]]
    return sorted((u for u in out if incluir_inactivos or u["activo"]), key=lambda u: u["nombre"].casefold())


def crear(nombre, contrasena):
    """Alta desde el panel. La contraseña inicial se cambia en la primera entrada."""
    nombre = validar_nombre(nombre)
    validar_contrasena(contrasena)
    clave = clave_de(nombre)
    with _lock:
        d = _leer()
        if clave in d["usuarios"]:
            raise FileExistsError(f"Ya existe un transcriptor con ese nombre: {d['usuarios'][clave]['nombre']}.")
        sal = secrets.token_hex(16)
        d["usuarios"][clave] = {"nombre": nombre, "sal": sal, "huella": _huella(contrasena, sal), "activo": True,
                                "cambiar": True, "creado": time.strftime("%Y-%m-%d %H:%M")}
        _grabar(d)
    return clave


def poner_contrasena(clave, nueva, *, cambiar=False):
    validar_contrasena(nueva)
    with _lock:
        d = _leer()
        u = d["usuarios"].get(clave or "")
        if not u:
            raise FileNotFoundError("Ese transcriptor ya no existe. Actualizá la lista.")
        u["sal"] = secrets.token_hex(16)
        u["huella"] = _huella(nueva, u["sal"])
        u["cambiar"] = bool(cambiar)
        _grabar(d)


def cambiar_propia(clave, actual, nueva):
    """El transcriptor cambia su contraseña. Devuelve un mensaje de error o '' si salió bien."""
    if not verificar_clave(clave, actual):
        return "La contraseña actual no es correcta."
    try:
        validar_contrasena(nueva)
    except ValueError as ex:
        return str(ex)
    if hmac.compare_digest(actual, nueva):
        return "La contraseña nueva tiene que ser distinta de la actual."
    poner_contrasena(clave, nueva, cambiar=False)
    return ""


def activar(clave, activo):
    with _lock:
        d = _leer()
        u = d["usuarios"].get(clave or "")
        if not u:
            raise FileNotFoundError("Ese transcriptor ya no existe. Actualizá la lista.")
        u["activo"] = bool(activo)
        _grabar(d)


def renombrar(clave, nombre):
    """Cambia el nombre que se muestra; la clave (carpeta de su estilo) no cambia."""
    nombre = validar_nombre(nombre)
    with _lock:
        d = _leer()
        u = d["usuarios"].get(clave or "")
        if not u:
            raise FileNotFoundError("Ese transcriptor ya no existe. Actualizá la lista.")
        otro = clave_de(nombre)
        if otro != clave and otro in d["usuarios"]:
            raise FileExistsError(f"Ya existe un transcriptor con ese nombre: {d['usuarios'][otro]['nombre']}.")
        u["nombre"] = nombre
        _grabar(d)


def _buscar(d, nombre):
    clave = clave_de(nombre)
    if clave in d["usuarios"]:
        return clave
    n = " ".join(str(nombre or "").split()).casefold()
    for k, u in d["usuarios"].items():
        if u["nombre"].casefold() == n:
            return k
    return None


_HUELLA_FALSA = {"sal": "00" * 16, "huella": ""}


def verificar(nombre, contrasena):
    """Devuelve la clave del transcriptor si el nombre y la contraseña son correctos (y está activo)."""
    d = _leer()
    clave = _buscar(d, nombre)
    u = d["usuarios"].get(clave) if clave else None
    ref = u or _HUELLA_FALSA                       # mismo trabajo aunque el usuario no exista
    ok = hmac.compare_digest(_huella(str(contrasena or ""), ref["sal"]), ref["huella"])
    if not (u and ok and contrasena and u.get("activo", True)):
        return None
    return clave


def verificar_clave(clave, contrasena):
    u = _leer()["usuarios"].get(clave or "")
    return bool(u and contrasena and hmac.compare_digest(_huella(contrasena, u["sal"]), u["huella"]))


def anotar_entrada(clave):
    with _lock:
        d = _leer()
        u = d["usuarios"].get(clave or "")
        if u:
            u["ultima"] = time.strftime("%Y-%m-%d %H:%M")
            _grabar(d)


# ------------------------------------------------------ estilo propio (capas)
def carpeta(clave):
    if not clave or clave != clave_de(clave):
        raise ValueError("Transcriptor inválido")
    return CARPETA / clave


def archivo(clave, nombre):
    return carpeta(clave) / nombre


def leer_archivo(clave, nombre):
    if not clave:
        return ""
    f = archivo(clave, nombre)
    try:
        return f.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        return ""


def escribir_archivo(clave, nombre, texto):
    f = archivo(clave, nombre)
    if not (texto or "").strip():
        f.unlink(missing_ok=True)
        return
    f.parent.mkdir(parents=True, exist_ok=True)
    escribir_atomico(f, texto)


def claves_con_carpeta():
    return sorted(p.name for p in CARPETA.iterdir() if p.is_dir()) if CARPETA.is_dir() else []


def _leer_json(clave, nombre):
    t = leer_archivo(clave, nombre)
    try:
        v = json.loads(t) if t.strip() else {}
    except ValueError:
        v = {}
    return v if isinstance(v, dict) else {}


# --- preferencias de la pantalla (las mismas claves que la página guarda en localStorage)
PREF_VALIDA = re.compile(r"^(pref_[A-Za-z0-9_]{1,40}|tema|listaOculta|velUltima|barraFormatoOculta|zoomVp|"
                         r"anchoLista|anchoLista2|propInforme|filtroCasos)$")


def preferencias(clave):
    return {k: v for k, v in _leer_json(clave, "preferencias.json").items()
            if PREF_VALIDA.match(k) and isinstance(v, str)}


def guardar_preferencias(clave, prefs):
    if not isinstance(prefs, dict):
        raise ValueError("Preferencias inválidas")
    limpias = {}
    for k, v in prefs.items():
        if not isinstance(k, str) or not PREF_VALIDA.match(k):
            continue
        if not isinstance(v, str) or len(v) > 4000:
            continue
        limpias[k] = v
        if len(limpias) >= 120:
            break
    escribir_archivo(clave, "preferencias.json", json.dumps(limpias, ensure_ascii=False, indent=1))
    return limpias


# --- formato del Word: opciones de configuracion.json que cada transcriptor puede cambiar
FORMATO = {
    "fuente": str,
    "tamano_fuente": int,
    "lineas_vacias_para_encabezado": int,
    "linea_vacia_entre_titulo_y_texto": bool,
    "negrita_titulos": bool,
    "centrar_titulos": bool,
}
FUENTES = ("Tahoma", "Arial", "Calibri", "Times New Roman", "Verdana", "Segoe UI", "Cambria", "Georgia")


def formato(clave):
    out = {}
    for k, v in _leer_json(clave, "formato.json").items():
        try:
            out[k] = _validar_formato(k, v)
        except ValueError:
            pass
    return out


def _validar_formato(k, v):
    tipo = FORMATO.get(k)
    if tipo is None:
        raise ValueError(f"Opción desconocida: {k}")
    if tipo is bool:
        if not isinstance(v, bool):
            raise ValueError(f"{k}: tiene que ser sí o no")
        return v
    if tipo is int:
        if isinstance(v, bool) or not isinstance(v, (int, float)) or int(v) != v:
            raise ValueError(f"{k}: tiene que ser un número entero")
        v = int(v)
        lim = (8, 24) if k == "tamano_fuente" else (0, 20)
        if not lim[0] <= v <= lim[1]:
            raise ValueError(f"{k}: tiene que estar entre {lim[0]} y {lim[1]}")
        return v
    if not isinstance(v, str) or v not in FUENTES:
        raise ValueError("Elegí una fuente de la lista.")
    return v


def guardar_formato(clave, cambios):
    """cambios: {opción: valor}; None (o ausente) = usar el general."""
    if not isinstance(cambios, dict):
        raise ValueError("Formato inválido")
    actual = formato(clave)
    for k, v in cambios.items():
        if k not in FORMATO:
            raise ValueError(f"Opción desconocida: {k}")
        if v is None:
            actual.pop(k, None)
        else:
            actual[k] = _validar_formato(k, v)
    escribir_archivo(clave, "formato.json", json.dumps(actual, ensure_ascii=False, indent=1) if actual else "")
    return actual


def cfg_de(cfg, clave):
    """configuracion.json con el formato propio del transcriptor encima."""
    if not clave:
        return cfg
    propio = formato(clave)
    return {**cfg, **propio} if propio else cfg
