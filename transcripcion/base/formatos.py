"""Formatos chicos que se usan en varios lugares: minutos:segundos, porcentaje y duración de un WAV.

Vienen de servidor.py (docs/refactor.md, etapa 5)."""
import io
import wave


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
