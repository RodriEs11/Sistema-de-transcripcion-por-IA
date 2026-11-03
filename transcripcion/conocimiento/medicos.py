"""Médicos y sus notas de cómo dictan (generales y propias de cada transcriptor).

Viene de nucleo.py (docs/refactor.md, etapa 3).
"""
import re
import threading
from fase1_transcribir import sin_acentos
from transcripcion.acceso import usuarios as U
from transcripcion.conocimiento import archivos as CON


# ----------------------------------------------------------------- medicos
DIR_MED = CON.CONOC / "medicos"
_MED_LOCK = threading.RLock()


def clave_medico(nombre):
    return " ".join(sin_acentos(nombre).casefold().split())


def validar_nombre_medico(nombre):
    if not isinstance(nombre, str):
        raise ValueError("Escribí el nombre del médico.")
    nombre = " ".join(nombre.split())
    if (len(nombre) < 2 or len(nombre) > 120 or not any(c.isalpha() for c in nombre)
            or re.search(r"[^\w .,-]", nombre) or nombre.endswith(".")
            or nombre.split(".")[0].upper() in {"CON", "PRN", "AUX", "NUL", "COM1", "COM2", "COM3", "COM4",
                                                  "COM5", "COM6", "COM7", "COM8", "COM9", "LPT1", "LPT2",
                                                  "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9"}):
        raise ValueError("Usá un nombre de 2 a 120 caracteres, con letras y sin símbolos especiales ni punto final.")
    return nombre


def _archivo_medico(nombre):
    seguro = re.sub(r"[^\w .,-]", "", nombre).strip()
    return DIR_MED / f"{seguro}.md"


def lista_medicos():
    if not DIR_MED.exists():
        return []
    return sorted(p.stem for p in DIR_MED.glob("*.md"))


def notas_medico(nombre, usuario=None):
    """Notas de cómo dicta el médico. Si el transcriptor tiene las suyas, reemplazan a las generales."""
    propias = notas_propias(nombre, usuario)
    if propias is not None:
        return propias
    f = _archivo_medico(nombre) if nombre else None
    return f.read_text(encoding="utf-8") if f and f.exists() else ""


def _archivo_medico_usuario(nombre, usuario):
    return U.carpeta(usuario) / "medicos" / _archivo_medico(nombre).name


def notas_propias(nombre, usuario):
    """Notas «solo para mí» del transcriptor sobre ese médico, o None si usa las generales."""
    if not nombre or not usuario:
        return None
    f = _archivo_medico_usuario(nombre, usuario)
    return f.read_text(encoding="utf-8") if f.exists() else None


def guardar_notas_propias(nombre, usuario, notas):
    """notas=None: vuelve a usar las generales."""
    with _MED_LOCK:
        if nombre not in lista_medicos():
            raise FileNotFoundError("El médico ya no existe. Actualizá la lista.")
        f = _archivo_medico_usuario(nombre, usuario)
        if notas is None:
            f.unlink(missing_ok=True)
            return
        if not isinstance(notas, str):
            raise ValueError("Las notas deben ser texto.")
        f.parent.mkdir(parents=True, exist_ok=True)
        temporal = f.with_suffix(".md.nuevo")
        temporal.write_text(notas, encoding="utf-8")
        temporal.replace(f)


def medicos_con_notas_propias(usuario):
    d = U.carpeta(usuario) / "medicos" if usuario else None
    return sorted(p.stem for p in d.glob("*.md")) if d and d.is_dir() else []


def guardar_medico(nombre, notas, *, crear=False, original=None):
    nombre = validar_nombre_medico(nombre)
    if not isinstance(notas, str):
        raise ValueError("Las notas deben ser texto.")
    with _MED_LOCK:
        existentes = lista_medicos()
        if original is not None and original not in existentes:
            raise FileNotFoundError("El médico ya no existe. Actualizá la lista.")
        for otro in existentes:
            if clave_medico(otro) == clave_medico(nombre) and (crear or otro != (original or nombre)):
                raise FileExistsError(f"Ya existe un médico con ese nombre: {otro}.")
        DIR_MED.mkdir(parents=True, exist_ok=True)
        f = _archivo_medico(nombre)
        if original and original != nombre:
            anterior = _archivo_medico(original)
            # El renombrado también admite cambios de mayúsculas en Windows.
            anterior.rename(f)
            for clave in U.claves_con_carpeta():      # las notas propias de cada transcriptor siguen al médico
                viejo = _archivo_medico_usuario(original, clave)
                if viejo.exists():
                    viejo.rename(_archivo_medico_usuario(nombre, clave))
        temporal = f.with_suffix(".md.nuevo")
        temporal.write_text(notas, encoding="utf-8")
        temporal.replace(f)
        return nombre


def eliminar_medico(nombre):
    with _MED_LOCK:
        if nombre not in lista_medicos():
            raise FileNotFoundError("El médico ya no existe. Actualizá la lista.")
        _archivo_medico(nombre).unlink()
        for clave in U.claves_con_carpeta():
            _archivo_medico_usuario(nombre, clave).unlink(missing_ok=True)
