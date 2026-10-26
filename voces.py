"""Reconocimiento del médico por la voz ("huella de voz").

Cada audio se resume en una huella: un vector de 256 números que describe la voz de quien habla (modelo
WeSpeaker ResNet34 entrenado con VoxCeleb; corre con onnxruntime en el procesador, no usa la placa de video).
La huella no permite reconstruir la voz ni lo que se dijo.

La huella de un audio nuevo se compara con las muestras de cada médico (las huellas de los informes que ya se
guardaron con su médico confirmado) y el resultado es uno de estos:
  seguro       se asigna el médico solo: la IA usa sus plantillas "(estilo X)", sus notas y sus ejemplos
  dudoso       se sugiere el médico, pero la IA arma el informe con la plantilla general (sin estilo de médico)
  desconocido  voz sin reconocer (médico nuevo o con pocas muestras)
  corto        el audio tiene muy poca voz para reconocerla

Archivos:
  modelos/wespeaker_resnet34.onnx            el modelo (se baja solo la primera vez, unos 26 MB)
  voces/huellas.json                         muestras etiquetadas {"v":1, "muestras": {caso: {medico, h, ...}}}
  Informes/revision/datos/<caso>.voz.json    huella del caso y resultado de la detección (lo maneja servidor.py)
"""
import hashlib
import json
import os
import threading
import time
import urllib.request
from pathlib import Path

import numpy as np

AQUI = Path(__file__).resolve().parent
DIR_MODELOS = AQUI / "modelos"
MODELO = DIR_MODELOS / "wespeaker_resnet34.onnx"
URL_MODELO = ("https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-recongition-models/"
              "wespeaker_en_voxceleb_resnet34_LM.onnx")
SHA_MODELO = "e9848563da86f263117134dfd7ad63c92355b37de492b55e325400c9d9c39012"
DIR_VOCES = AQUI / "voces"
HUELLAS = DIR_VOCES / "huellas.json"
VERSION_HUELLA = "wespeaker-r34-1"     # si cambia el modelo o el cálculo, las huellas viejas no se mezclan

# Valores por defecto (se pueden cambiar en configuracion.json → "voces": {...}).
# El parecido es el coseno entre huellas (1 = misma voz). Con este modelo, dos audios de la misma persona
# suelen dar 0,65 a 0,90; dos personas distintas grabadas con el mismo equipo, 0,2 a 0,55. Por eso, además del
# parecido, se exige que el primer médico le saque una ventaja clara al segundo.
DEF = {
    "umbral_seguro": 0.62,     # parecido mínimo para asignar el médico solo
    "margen": 0.10,            # y tiene que superar al segundo médico por al menos esto
    "umbral_dudoso": 0.45,     # por debajo: voz sin reconocer
    "margen_propio": 0.15,     # y no puede parecerse mucho menos de lo que sus muestras se parecen entre sí
    "min_muestras": 3,         # un médico con menos muestras nunca se asigna solo
    "max_muestras": 40,        # se comparan las últimas N muestras de cada médico
    "min_voz_s": 2.0,          # menos voz que esto: no se intenta
    "max_voz_s": 120.0,        # más voz que esto no mejora la huella y tarda más
    "agrupar": 0.65,           # parecido mínimo para juntar dos audios sin etiquetar en un grupo
}

SR = 16000
_LOCK = threading.RLock()        # huellas.json
_SES_LOCK = threading.Lock()     # sesión de onnxruntime
_SES = {"s": None}
_DESCARGA = {"estado": "", "error": "", "lock": threading.Lock()}


class SinModelo(Exception):
    """El modelo de voz no está (y no se pudo bajar)."""


def parametros(cfg=None):
    p = dict(DEF)
    if cfg and isinstance(cfg.get("voces"), dict):
        for k, v in cfg["voces"].items():
            if k in DEF and isinstance(v, (int, float)):
                p[k] = float(v)
    return p


# ------------------------------------------------------------------ modelo
def modelo_listo():
    return MODELO.exists() and MODELO.stat().st_size > 1_000_000


def estado_modelo():
    if modelo_listo():
        return "listo"
    return _DESCARGA["estado"] or "falta"


def descargar_modelo(timeout=120):
    """Baja el modelo de GitHub (sherpa-onnx) y verifica su SHA-256. Devuelve True si quedó listo."""
    if modelo_listo():
        return True
    with _DESCARGA["lock"]:
        if modelo_listo():
            return True
        _DESCARGA.update(estado="bajando", error="")
        DIR_MODELOS.mkdir(exist_ok=True)
        tmp = MODELO.with_name(MODELO.name + ".descarga")
        try:
            h = hashlib.sha256()
            req = urllib.request.Request(URL_MODELO, headers={"User-Agent": "Transcripcion"})
            with urllib.request.urlopen(req, timeout=timeout) as r, open(tmp, "wb") as f:
                while True:
                    b = r.read(1 << 16)
                    if not b:
                        break
                    h.update(b)
                    f.write(b)
            if h.hexdigest() != SHA_MODELO:
                raise ValueError("el archivo bajado no coincide con el esperado (SHA-256 distinto)")
            os.replace(tmp, MODELO)
            _DESCARGA.update(estado="listo")
            return True
        except Exception as ex:
            _DESCARGA.update(estado="error", error=str(ex) or type(ex).__name__)
            try:
                tmp.unlink()
            except OSError:
                pass
            return False


def _sesion():
    with _SES_LOCK:
        if _SES["s"] is None:
            if not modelo_listo():
                raise SinModelo(_DESCARGA["error"] or "falta el modelo de voz")
            import onnxruntime as ort
            op = ort.SessionOptions()
            op.intra_op_num_threads = max(1, min(4, (os.cpu_count() or 2) // 2))
            op.log_severity_level = 3
            _SES["s"] = ort.InferenceSession(str(MODELO), op, providers=["CPUExecutionProvider"])
        return _SES["s"]


# ------------------------------------------------------------------ características (fbank como Kaldi)
def _mel(f):
    return 1127.0 * np.log(1.0 + f / 700.0)


def _banco_mel(n_mel=80, n_fft=512, sr=SR, low=20.0):
    high = sr / 2
    nb = n_fft // 2
    ml, mh = _mel(low), _mel(high)
    delta = (mh - ml) / (n_mel + 1)
    f = (sr / n_fft) * np.arange(nb)
    m = _mel(f)
    banco = np.zeros((n_mel, nb + 1), dtype=np.float32)
    for i in range(n_mel):
        izq, cen, der = ml + i * delta, ml + (i + 1) * delta, ml + (i + 2) * delta
        sube = (m - izq) / (cen - izq)
        baja = (der - m) / (der - cen)
        banco[i, :nb] = np.maximum(0.0, np.minimum(sube, baja))
    return banco


_BANCO = None
_VENTANA = None


def fbank(x):
    """80 bandas log-mel, ventanas de 25 ms cada 10 ms (igual que torchaudio.compliance.kaldi.fbank con dither 0,
    que es lo que usa WeSpeaker). x: audio a 16 kHz en float con escala de entero de 16 bits."""
    global _BANCO, _VENTANA
    if _BANCO is None:
        _BANCO = _banco_mel()
        n = np.arange(400)
        _VENTANA = (0.5 - 0.5 * np.cos(2 * np.pi * n / 399)) ** 0.85      # ventana "povey"
    x = np.asarray(x, dtype=np.float64)
    if len(x) < 400:
        return np.zeros((0, 80), dtype=np.float32)
    nf = 1 + (len(x) - 400) // 160
    idx = np.arange(400)[None, :] + 160 * np.arange(nf)[:, None]
    fr = x[idx]
    fr = fr - fr.mean(axis=1, keepdims=True)                              # quita la componente continua
    fr = np.concatenate([fr[:, :1] - 0.97 * fr[:, :1], fr[:, 1:] - 0.97 * fr[:, :-1]], axis=1)  # preénfasis
    fr = fr * _VENTANA
    esp = np.abs(np.fft.rfft(fr, n=512, axis=1)) ** 2
    mel = esp @ _BANCO.T.astype(np.float64)
    return np.log(np.maximum(mel, np.finfo(np.float32).eps)).astype(np.float32)


# ------------------------------------------------------------------ huella
def tramos_de_voz(palabras, total_s, pegar=0.6, borde=0.15):
    """Tramos con voz según los tiempos de las palabras de Whisper (se juntan las pausas cortas)."""
    t = []
    for w in palabras or []:
        a, b = w.get("ini"), w.get("fin")
        if a is None or b is None or b <= a:
            continue
        a, b = max(0.0, a - borde), min(total_s, b + borde)
        if b <= a:                            # palabra fuera del audio
            continue
        if t and a - t[-1][1] <= pegar:
            t[-1][1] = max(t[-1][1], b)
        else:
            t.append([a, b])
    return t


def _embedding(feats):
    ses = _sesion()
    f = feats - feats.mean(axis=0, keepdims=True)                         # normalización por media (CMN)
    out = ses.run(None, {ses.get_inputs()[0].name: f[None, :, :].astype(np.float32)})[0][0]
    return np.asarray(out, dtype=np.float64)


def _normalizar(v):
    n = float(np.linalg.norm(v))
    return v / n if n > 0 else v


def huella(audio, palabras=None, cfg=None):
    """audio: float32 a 16 kHz (-1..1). Devuelve (huella como lista de 256 floats o None, segundos de voz usados).
    Si el audio es largo se calcula por partes de 20 s y se promedian."""
    p = parametros(cfg)
    audio = np.asarray(audio, dtype=np.float32)
    total = len(audio) / SR
    tramos = tramos_de_voz(palabras, total) if palabras else []
    if not tramos:
        tramos = [[0.0, total]]
    partes, seg = [], 0.0
    for a, b in tramos:
        if seg >= p["max_voz_s"]:
            break
        b = min(b, a + p["max_voz_s"] - seg)
        partes.append(audio[int(a * SR):int(b * SR)])
        seg += b - a
    if seg < p["min_voz_s"]:
        return None, round(seg, 1)
    voz = np.concatenate(partes) * 32768.0
    trozo = 20 * SR
    embs, pesos = [], []
    for i in range(0, len(voz), trozo):
        z = voz[i:i + trozo]
        if len(z) < 3 * SR and embs:          # el resto corto se suma al trozo anterior
            z = voz[max(0, i - trozo):i + trozo]
            embs.pop(), pesos.pop()
        feats = fbank(z)
        if len(feats) < 50:
            continue
        embs.append(_normalizar(_embedding(feats)))
        pesos.append(len(feats))
    if not embs:
        return None, round(seg, 1)
    h = _normalizar(np.average(np.stack(embs), axis=0, weights=pesos))
    return [round(float(v), 5) for v in h], round(seg, 1)


def huella_archivo(ruta, palabras=None, cfg=None):
    from fase1_transcribir import cargar_audio
    return huella(cargar_audio(ruta), palabras, cfg)


# ------------------------------------------------------------------ muestras etiquetadas
def _leer():
    try:
        d = json.loads(HUELLAS.read_text(encoding="utf-8"))
        if isinstance(d, dict) and isinstance(d.get("muestras"), dict):
            return d
    except (OSError, ValueError):
        pass
    return {"v": 1, "modelo": VERSION_HUELLA, "muestras": {}}


_CACHE = {"mt": None, "d": None}


def _datos():
    """huellas.json en memoria (se vuelve a leer si cambió en el disco)."""
    with _LOCK:
        try:
            mt = HUELLAS.stat().st_mtime_ns
        except OSError:
            mt = None
        if _CACHE["d"] is None or _CACHE["mt"] != mt:
            _CACHE.update(d=_leer(), mt=mt)
        return _CACHE["d"]


def _grabar(d):
    with _LOCK:
        DIR_VOCES.mkdir(exist_ok=True)
        tmp = HUELLAS.with_name(HUELLAS.name + ".nuevo")
        tmp.write_text(json.dumps(d, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        os.replace(tmp, HUELLAS)
        _CACHE.update(d=d, mt=HUELLAS.stat().st_mtime_ns)


def agregar(caso, medico, h, fuente="guardado", seg=None):
    """Guarda (o reemplaza) la muestra de voz de un caso como del médico indicado.
    Devuelve cuántas muestras tiene ahora ese médico."""
    if not h or not medico:
        return None
    with _LOCK:
        d = _datos()
        d["muestras"][caso] = {"medico": medico, "h": h, "fecha": time.time(), "fuente": fuente, "seg": seg,
                               "modelo": VERSION_HUELLA}
        _grabar(d)
        return sum(1 for m in d["muestras"].values() if m.get("medico") == medico)


def quitar(caso):
    """Saca la muestra de un caso. Devuelve el médico que tenía (o None)."""
    with _LOCK:
        d = _datos()
        m = d["muestras"].pop(caso, None)
        if m is not None:
            _grabar(d)
        return m.get("medico") if m else None


def muestra(caso):
    return _datos()["muestras"].get(caso)


def muestras(medico=None):
    """[(caso, muestra)] ordenadas de la más nueva a la más vieja."""
    ms = [(c, m) for c, m in _datos()["muestras"].items()
          if (medico is None or m.get("medico") == medico) and m.get("modelo", VERSION_HUELLA) == VERSION_HUELLA]
    ms.sort(key=lambda x: x[1].get("fecha") or 0, reverse=True)
    return ms


def resumen():
    """{médico: {"n": muestras, "ultima": fecha}}"""
    r = {}
    for _, m in muestras():
        x = r.setdefault(m["medico"], {"n": 0, "ultima": 0})
        x["n"] += 1
        x["ultima"] = max(x["ultima"], m.get("fecha") or 0)
    return r


def renombrar_medico(viejo, nuevo):
    with _LOCK:
        d = _datos()
        n = 0
        for m in d["muestras"].values():
            if m.get("medico") == viejo:
                m["medico"] = nuevo
                n += 1
        if n:
            _grabar(d)
        return n


# ------------------------------------------------------------------ detección
def puntajes(h, excluir=None, cfg=None):
    """[(médico, parecido, cantidad de muestras, parecido típico entre sus muestras)] de mayor a menor parecido.
    Parecido = promedio de las 3 muestras más parecidas del médico (entre sus últimas max_muestras).
    Típico = mediana del parecido entre sus muestras (None con menos de 3): cuánto se parece su voz a sí misma."""
    p = parametros(cfg)
    v = np.asarray(h, dtype=np.float64)
    por_med = {}
    for caso, m in muestras():
        if caso == excluir:
            continue
        lst = por_med.setdefault(m["medico"], [])
        if len(lst) < p["max_muestras"]:
            lst.append(m["h"])
    out = []
    for med, hs in por_med.items():
        M = np.asarray(hs, dtype=np.float64)
        top = np.sort(M @ v)[::-1][:3]
        tip = None
        if len(hs) >= 3:
            S = M @ M.T
            tip = float(np.median(S[np.triu_indices(len(hs), 1)]))
        out.append((med, float(top.mean()), len(hs), tip))
    out.sort(key=lambda x: x[1], reverse=True)
    return out


def detectar(h, excluir=None, cfg=None):
    """Resultado de comparar una huella con las muestras de los médicos."""
    if not h:
        return {"estado": "corto"}
    p = parametros(cfg)
    r = puntajes(h, excluir, cfg)
    if not r:
        return {"estado": "desconocido", "motivo": "todavía no hay muestras de voz de ningún médico"}
    med, s1, n1, tip = r[0]
    s2 = r[1][1] if len(r) > 1 else 0.0
    d = {"medico": med, "puntaje": round(s1, 3), "muestras": n1, "tipico": round(tip, 3) if tip is not None else None,
         "segundo": r[1][0] if len(r) > 1 else None, "puntaje2": round(s2, 3) if len(r) > 1 else None,
         "ranking": [[m, round(s, 3)] for m, s, _, _ in r[:3]]}
    propio = tip is None or s1 >= tip - p["margen_propio"]
    if s1 >= p["umbral_seguro"] and s1 - s2 >= p["margen"] and n1 >= p["min_muestras"] and propio:
        d["estado"] = "seguro"
    elif s1 >= p["umbral_dudoso"]:
        d["estado"] = "dudoso"
        if n1 < p["min_muestras"]:
            d["motivo"] = f"{med} tiene {n1} de {int(p['min_muestras'])} muestras necesarias para asignarlo solo"
        elif s1 < p["umbral_seguro"]:
            d["motivo"] = "el parecido no alcanza para asignarlo solo"
        elif not propio:
            d["motivo"] = f"se parece menos de lo habitual a las muestras de {med} (suelen parecerse {round(tip * 100)} %)"
        else:
            d["motivo"] = f"se parece casi igual a {d['segundo']}"
    else:
        d["estado"] = "desconocido"
        d["motivo"] = "no se parece lo suficiente a ningún médico con muestras"
    return d


def agrupar(items, cfg=None):
    """Junta huellas parecidas (sin etiquetar) para etiquetarlas de a grupos.
    items: [(clave, huella)]. Devuelve [[claves]] del grupo más grande al más chico.
    Agrupamiento jerárquico por promedio: se juntan los dos grupos más parecidos mientras su parecido promedio
    sea al menos p["agrupar"]."""
    p = parametros(cfg)
    items = [(k, np.asarray(h, dtype=np.float64)) for k, h in items if h]
    if not items:
        return []
    M = np.stack([h for _, h in items])
    S = M @ M.T
    grupos = [[i] for i in range(len(items))]
    while len(grupos) > 1:
        mejor, par = -2.0, None
        for a in range(len(grupos)):
            for b in range(a + 1, len(grupos)):
                s = float(S[np.ix_(grupos[a], grupos[b])].mean())
                if s > mejor:
                    mejor, par = s, (a, b)
        if mejor < p["agrupar"]:
            break
        a, b = par
        grupos[a] = grupos[a] + grupos[b]
        del grupos[b]
    grupos.sort(key=len, reverse=True)
    return [[items[i][0] for i in g] for g in grupos]


def centro(hs):
    v = _normalizar(np.mean(np.asarray(hs, dtype=np.float64), axis=0))
    return [float(x) for x in v]
