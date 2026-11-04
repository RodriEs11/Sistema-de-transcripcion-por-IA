"""Borrador y omisiones en una única escritura atómica, con lectura del formato anterior."""

import json
import os
import tempfile
import threading
from pathlib import Path

_lock = threading.RLock()


class Conflicto(ValueError):
    """Otra escritura modificó el borrador desde que el cliente lo leyó."""


class Corrupto(ValueError):
    """El archivo existente requiere recuperación; nunca se reemplaza por un borrador nuevo."""


def _validar(d):
    if (
        not isinstance(d, dict)
        or type(d.get("v")) is not int
        or d["v"] != 1
        or not isinstance(d.get("html"), str)
        or not isinstance(d.get("omisiones_ok"), list)
        or not all(isinstance(x, str) for x in d["omisiones_ok"])
        or type(d.get("revision", 0)) is not int
        or d.get("revision", 0) < 0
    ):
        raise Corrupto(
            "El borrador guardado tiene un formato inválido o incompatible. Conservá los archivos para recuperarlo."
        )
    return d


def leer(carpeta, nombre):
    with _lock:
        ruta = Path(carpeta) / (nombre + ".borrador.json")
        if ruta.exists():
            try:
                return _validar(json.loads(ruta.read_text(encoding="utf-8")))
            except (json.JSONDecodeError, UnicodeError) as ex:
                raise Corrupto("No se pudo leer el borrador guardado. Conservá los archivos para recuperarlo.") from ex
        html = Path(carpeta) / (nombre + ".borrador.html")
        omisiones = Path(carpeta) / (nombre + ".omisiones_ok.json")
        try:
            d = {
                "v": 1,
                "html": html.read_text(encoding="utf-8") if html.exists() else "",
                "omisiones_ok": json.loads(omisiones.read_text(encoding="utf-8")) if omisiones.exists() else [],
                "revision": 0,
            }
            _validar(d)
        except (json.JSONDecodeError, UnicodeError) as ex:
            raise Corrupto("No se pudo leer el borrador anterior. Conservá los archivos para recuperarlo.") from ex
        if not html.exists():
            d["html"] = None
        return d


def guardar(carpeta, nombre, datos):
    if not isinstance(datos, dict) or "html" not in datos:
        raise ValueError("Falta el contenido del borrador")
    html = datos.get("html", "")
    if not isinstance(html, str):
        raise ValueError("El borrador debe ser texto")
    if "omisiones_ok" in datos and (
        not isinstance(datos["omisiones_ok"], list) or not all(isinstance(x, str) for x in datos["omisiones_ok"])
    ):
        raise ValueError("Las omisiones deben ser una lista de textos")
    with _lock:
        anterior = leer(carpeta, nombre)
        revision = anterior.get("revision", 0)
        esperada = datos.get("revision")
        if esperada is not None and (type(esperada) is not int or esperada < 0):
            raise ValueError("Revisión de borrador inválida")
        if esperada is not None and esperada != revision:
            if (
                html == anterior["html"]
                and datos.get("omisiones_ok", anterior["omisiones_ok"]) == anterior["omisiones_ok"]
            ):
                return revision  # respuesta perdida: reintento idempotente del mismo contenido
            raise Conflicto(
                "El borrador cambió en otra sesión. Conservá tus cambios en esta pantalla antes de volver a abrirlo."
            )
        d = {
            "v": 1,
            "html": html,
            "omisiones_ok": datos.get("omisiones_ok", anterior["omisiones_ok"]),
            "revision": revision + 1,
        }
        ruta = Path(carpeta) / (nombre + ".borrador.json")
        # Temporal en el mismo volumen. El lector ve la versión anterior o la nueva, nunca media escritura.
        fd, temporal = tempfile.mkstemp(prefix=".borrador-", suffix=".tmp", dir=carpeta)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(d, f, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temporal, ruta)
        finally:
            Path(temporal).unlink(missing_ok=True)
        return d["revision"]
