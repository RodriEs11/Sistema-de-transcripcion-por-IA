"""Cliente de Ollama (IA local): modelos disponibles, generación y liberación de la placa de video.

`OLLAMA` y `_post` se usan como atributos del módulo: las herramientas de medición los reemplazan.

Viene de nucleo.py (docs/refactor.md, etapa 3).
"""
import json
import re
import time
import urllib.error
import urllib.request
from transcripcion.controles import orden as ORD


OLLAMA = "http://localhost:11434"


# ------------------------------------------------------------------ ollama
def ollama_modelos():
    try:
        with urllib.request.urlopen(OLLAMA + "/api/tags", timeout=5) as r:
            return [m["name"] for m in json.load(r)["models"]]
    except Exception:
        return None


def _post(payload, timeout=600):
    req = urllib.request.Request(OLLAMA + "/api/chat", data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def llamar_ia(modelo, mensajes, num_ctx=12288, pensar=False, metricas=None):
    payload = {"model": modelo, "messages": mensajes, "stream": False, "keep_alive": "15m",
               "options": {"temperature": 0.1, "num_ctx": num_ctx}}
    t0 = time.perf_counter()
    try:
        r = _post(dict(payload, think=pensar))
    except urllib.error.HTTPError as e:  # modelos que no aceptan "think"
        if e.code == 400:
            r = _post(payload)
        else:
            raise
    txt = r["message"]["content"]
    txt = re.sub(r"<think>.*?</think>", "", txt, flags=re.S).strip()
    txt = re.sub(r"^```\w*\n?|```$", "", txt).strip()
    txt = ORD.ordenar_estudios(txt)
    if metricas is not None:
        for clave in ('total_duration', 'load_duration', 'prompt_eval_duration', 'eval_duration'):
            valor = r.get(clave)
            if isinstance(valor, (int, float)) and not isinstance(valor, bool) and valor >= 0:
                metricas[clave + '_s'] = valor / 1_000_000_000
        for clave in ('prompt_eval_count', 'eval_count'):
            if isinstance(r.get(clave), int):
                metricas[clave] = r[clave]
    return txt, time.perf_counter() - t0, r.get("prompt_eval_count"), r.get("eval_count")


def liberar_ia(modelo):
    """Saca el modelo de Ollama de la placa de video (para que entre Whisper)."""
    try:
        req = urllib.request.Request(OLLAMA + "/api/generate",
                                     data=json.dumps({"model": modelo, "keep_alive": 0}).encode(),
                                     headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=30).read()
    except Exception:
        pass
