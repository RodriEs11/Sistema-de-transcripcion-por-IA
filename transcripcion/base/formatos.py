"""Formatos chicos que se usan en varios lugares: minutos:segundos, porcentaje, duración de un WAV, resumen de
marcas y mensajes de error entendibles.

Vienen de servidor.py (docs/refactor.md, etapa 5)."""
import io
import wave
from pathlib import Path


def mmss(t):
    return f"{int(t // 60)}:{int(t % 60):02d}"


def pct_voz(p):
    return f"{round((p or 0) * 100)} %"


def duracion_wav(datos=None, ruta=None):
    try:
        with wave.open(io.BytesIO(datos) if datos is not None else str(ruta), "rb") as w:
            return w.getnframes() / float(w.getframerate())
    except Exception:
        return None


def texto_marcas(r):
    partes = []
    for k, uno, varios in (("rojo", "roja", "rojas"), ("amarillo", "amarilla", "amarillas"),
                           ("turq", "turquesa", "turquesa"), ("gris", "gris", "grises")):
        if r.get(k):
            partes.append(f"{r[k]} {uno if r[k] == 1 else varios}")
    return ("marcas: " + ", ".join(partes)) if partes else "sin marcas"


def mensaje_amigable(ex):
    m = str(ex)
    if isinstance(ex, ConnectionRefusedError) or "Connection refused" in m or "urlopen error" in m \
            or "10061" in m:
        return "No se pudo conectar con Ollama. ¿Está abierto?"
    if "out of memory" in m.lower() or "CUDA failed" in m:
        return ("La placa de video se quedó sin memoria. Cerrá otros programas que la usen "
                "y volvé a procesar el audio.")
    if "timed out" in m.lower():
        return "La IA tardó demasiado en responder."
    if isinstance(ex, FileNotFoundError):
        falta = Path(ex.filename).name if getattr(ex, "filename", None) else "un archivo"
        return f"Falta el archivo «{falta}» (¿se borró o se movió?)."
    if isinstance(ex, PermissionError):
        return "Windows no dejó abrir un archivo: puede estar abierto en otro programa."
    if isinstance(ex, (ValueError, KeyError, IndexError, TypeError, AttributeError)):
        return f"Error interno ({type(ex).__name__}). El detalle quedó en la carpeta registros."
    m = m or type(ex).__name__
    return m if len(m) <= 160 else m[:157] + "…"
