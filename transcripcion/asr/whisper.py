"""Whisper (faster-whisper): librerías de CUDA, carga del modelo, lectura de audio propia (sin PyAV), vocabulario
médico como prompt y transcripción con tiempos por palabra.

Viene de fase1_transcribir.py (docs/refactor.md, etapa 4).
"""
import glob
import os
import sys
import wave
from pathlib import Path
from transcripcion import RAIZ


VOCAB_DEF = RAIZ / "vocabulario.txt"     # vocabulario médico para el prompt de Whisper


# ----------------------------------------------------------------- GPU
def preparar_cuda():
    """Hace visibles las bibliotecas de CUDA/cuDNN instaladas con pip (paquetes nvidia-*)."""
    bases = {sys.prefix, os.path.join(sys.prefix, "Lib", "site-packages")}
    try:
        import site
        bases.update(site.getsitepackages())
    except Exception:
        pass
    if os.name != "nt":
        _preparar_cuda_linux(bases)
        return
    for base in bases:
        for d in glob.glob(os.path.join(base, "nvidia", "*", "bin")):
            try:
                os.add_dll_directory(d)
            except Exception:
                pass
            os.environ["PATH"] = d + os.pathsep + os.environ.get("PATH", "")


def _preparar_cuda_linux(bases):
    """Linux: los .sh ya ponen las carpetas nvidia/*/lib en LD_LIBRARY_PATH. Si el programa se abrió de otra
    forma, se cargan acá a mano (RTLD_GLOBAL) para que CTranslate2 las encuentre. Si no hay GPU o las
    bibliotecas son las del sistema, no hace nada."""
    import ctypes
    ld = os.environ.get("LD_LIBRARY_PATH", "")
    pendientes = []
    for base in bases:
        for d in glob.glob(os.path.join(base, "nvidia", "*", "lib")):
            if d in ld:
                continue
            for patron in ("libcublasLt.so*", "libcublas.so*", "libcudnn*.so*"):
                pendientes += sorted(glob.glob(os.path.join(d, patron)))
    for _ in range(3):                  # algunas dependen de otras: reintentar las que fallaron
        fallaron = []
        for f in pendientes:
            try:
                ctypes.CDLL(f, mode=ctypes.RTLD_GLOBAL)
            except OSError:
                fallaron.append(f)
        if not fallaron or len(fallaron) == len(pendientes):
            break
        pendientes = fallaron


def cargar_modelo(nombre, device):
    preparar_cuda()
    from faster_whisper import WhisperModel
    compute = "float16" if device == "cuda" else "int8"
    print(f"Cargando modelo '{nombre}' en {device} ({compute})...")
    print("(la primera vez se descarga, ~3 GB; despues queda guardado)")
    return WhisperModel(nombre, device=device, compute_type=compute)


# --------------------------------------------------------------- transcripcion
def leer_vocabulario(ruta):
    if not ruta or not Path(ruta).exists():
        return None
    terms = [l.strip() for l in Path(ruta).read_text(encoding="utf-8-sig").splitlines()
             if l.strip() and not l.strip().startswith("#")]
    return "Informe médico de diagnóstico por imágenes: " + ", ".join(terms) + "."


def cargar_audio(ruta, sr=16000):
    """Lee un WAV PCM y lo pasa a 16 kHz mono float32 (sin depender de PyAV)."""
    import numpy as np
    try:
        with wave.open(str(ruta)) as w:
            n, ch, ancho, fr = w.getnframes(), w.getnchannels(), w.getsampwidth(), w.getframerate()
            crudo = w.readframes(n)
    except Exception:
        from faster_whisper import decode_audio  # otros formatos (mp3, etc.)
        return decode_audio(str(ruta), sampling_rate=sr)
    if ancho == 1:
        x = (np.frombuffer(crudo, np.uint8).astype(np.float32) - 128) / 128
    elif ancho == 2:
        x = np.frombuffer(crudo, "<i2").astype(np.float32) / 32768
    elif ancho == 3:
        b = np.frombuffer(crudo, np.uint8).reshape(-1, 3).astype(np.int32)
        v = b[:, 0] | (b[:, 1] << 8) | (b[:, 2] << 16)
        x = (np.where(v >= 1 << 23, v - (1 << 24), v)).astype(np.float32) / (1 << 23)
    else:
        x = np.frombuffer(crudo, "<i4").astype(np.float32) / 2147483648
    if ch > 1:
        x = x.reshape(-1, ch).mean(axis=1)
    if fr != sr and len(x):
        # remuestreo por FFT (sin aliasing)
        m = int(round(len(x) * sr / fr))
        X = np.fft.rfft(x)
        Y = np.zeros(m // 2 + 1, dtype=X.dtype)
        k = min(len(X), len(Y))
        Y[:k] = X[:k]
        x = np.fft.irfft(Y, n=m) * (m / len(x))
    return np.ascontiguousarray(x, dtype=np.float32)


def transcribir(modelo, ruta_wav, prompt, al_avanzar=None):
    """al_avanzar(pos, total): se llama después de cada tramo (el servidor lo usa para mostrar por dónde va y
    para la pausa: si la función no vuelve, Whisper queda detenido ahí con lo transcrito hasta ese momento)."""
    segs, info = modelo.transcribe(
        cargar_audio(ruta_wav), language="es", beam_size=5, vad_filter=True,
        word_timestamps=True, condition_on_previous_text=False,
        initial_prompt=prompt)
    palabras, textos = [], []
    for s in segs:
        textos.append(s.text.strip())
        for w in (s.words or []):
            palabras.append({"p": w.word, "ini": round(w.start, 2),
                             "fin": round(w.end, 2), "conf": round(w.probability, 3)})
        if al_avanzar:
            al_avanzar(s.end, getattr(info, "duration", None))
    return {"texto": " ".join(textos), "palabras": palabras}


def duracion(ruta):
    try:
        with wave.open(str(ruta)) as w:
            return w.getnframes() / float(w.getframerate())
    except Exception:
        return 0.0
