"""Reutilización ASR por contenido y parámetros. No cachea respuestas del LLM."""

import hashlib
import json
from pathlib import Path
from transcripcion.base.persistencia import escribir_atomico


def firma(ruta, parametros, fuentes=()):
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    codigo = [hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in fuentes]
    return {"audio": h.hexdigest(), "parametros": parametros, "codigo": codigo}


def leer(ruta, clave):
    try:
        datos = json.loads(Path(ruta).read_text(encoding="utf-8"))
        t = datos["transcripcion"]
        if (
            datos.get("v") == 1
            and datos["firma"] == clave
            and isinstance(t["texto"], str)
            and isinstance(t["palabras"], list)
            and isinstance(t.get("huecos", []), list)
        ):
            if all(
                isinstance(w, dict)
                and isinstance(w.get("p"), str)
                and all(isinstance(w.get(k), (int, float)) for k in ("ini", "fin", "conf"))
                for w in t["palabras"]
            ):
                return t
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return None


def guardar(ruta, clave, transcripcion):
    escribir_atomico(ruta, json.dumps({"v": 1, "firma": clave, "transcripcion": transcripcion}, ensure_ascii=False))
