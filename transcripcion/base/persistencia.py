"""Publicación atómica de archivos en el mismo volumen, sin truncar el anterior."""

import os
import tempfile
from pathlib import Path


def escribir_atomico(ruta, contenido):
    ruta = Path(ruta)
    fd, temporal = tempfile.mkstemp(prefix=".guardado-", suffix=".tmp", dir=ruta.parent)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(contenido if isinstance(contenido, bytes) else contenido.encode("utf-8"))
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporal, ruta)
    finally:
        Path(temporal).unlink(missing_ok=True)
