# -*- coding: utf-8 -*-
"""
INTERFAZ WEB. Se abre con interfaz.bat o .sh (solo esta PC) o con iniciar_servidor.bat o .sh
(esta PC + las PC del trabajo por un tunel: el rapido de Cloudflare o Microsoft Dev Tunnels).
Todo se procesa en esta PC: las otras solo envian audios y muestran la pagina.
"""
import contextlib
import csv
import gc
import hashlib
import io
import json
import mimetypes
import os
import queue
import re
import shutil
import sys
import threading
import time
import urllib.parse
import wave
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import admin as ADM
import correcciones as CORR
import estadisticas as EST
import app_cliente as A
import lotes_ia as LOTES
import cache_transcripcion as CACHE_ASR
import borradores as BOR
import cola_procesamiento as CP
from indice_casos import IndiceCasos
from persistencia import escribir_atomico
from aprendizaje_pendiente import ColaAprendizaje
import mantenimiento as M
import nucleo as N
import paciente as PAC
import plataforma as P
import registro as L
import remoto as R
import usuarios as U
import voces as VOZ
from informe import config, escribir_docx, parrafos_docx, pagina, aplicar_formato, texto_parrafo, EXT_AUDIO

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

AQUI = Path(__file__).resolve().parent
WEB = AQUI / "web"
PUERTO = int(os.environ.get("PUERTO_INTERFAZ", "8765"))
RECIBIR_AUDIO_LOCK = threading.RLock()
# Puerto propio del túnel de Microsoft (Dev Tunnels): todo lo que entra por acá es de las PC del trabajo,
# tenga los encabezados que tenga. Solo escucha en 127.0.0.1 y solo con ese túnel elegido.
PUERTO_TUNEL = int(os.environ.get("PUERTO_TUNEL", str(PUERTO + 1)))
CFG = config()
NUEVOS = CFG["carpeta_audios_nuevos"]
INFORMES = CFG["carpeta_informes"]
DATOS = INFORMES / "revision" / "datos"
for d in (NUEVOS, DATOS):
    d.mkdir(parents=True, exist_ok=True)

SIMULAR = os.environ.get("SIMULAR_IA") == "1"   # solo para pruebas
VERSION = "2026.11.1"
LOCAL = "Servidor"    # nombre con el que aparecen los casos subidos en esta misma PC
# páginas del panel de administración (solo en esta PC); cada una se abre en su pestaña del navegador
PAGINAS_ADMIN = {"/admin": "admin.html", "/admin/estadisticas": "estadisticas.html",
                 "/admin/correcciones": "correcciones.html", "/admin/medicos": "medicos.html"}
FIN_LOCK = threading.Lock()
INICIO = time.time()
TUNEL = {"modo": False, "http": None, "error": None}     # "modo": se abrió con iniciar_servidor.bat (--tunel)
_IA_CACHE = {"t": 0, "ok": False}


def ia_simulada():
    """Pruebas: SIMULAR_SIN_IA=1 hace de cuenta que Ollama está cerrado hasta que exista el archivo _ia_vuelve."""
    if os.environ.get("SIMULAR_SIN_IA") == "1" and not (AQUI / "_ia_vuelve").exists():
        return "caida"
    return "ok"


def ia_lista():
    if SIMULAR:
        return ia_simulada() != "caida"
    if time.time() - _IA_CACHE["t"] > 5:
        _IA_CACHE.update(t=time.time(), ok=N.ollama_modelos() is not None)
    return _IA_CACHE["ok"]


def modelo_presente(mods):
    m = CFG["modelo_ia"]
    return any(x == m or x == f"{m}:latest" or x.startswith(m + "-") for x in mods)


def estado_ia():
    """'ok', 'caida' (Ollama no responde) o 'sin_modelo'."""
    if SIMULAR:
        return ia_simulada()
    mods = N.ollama_modelos()
    if mods is None:
        return "caida"
    return "ok" if modelo_presente(mods) else "sin_modelo"


E_IA = {"e": "ok"}      # último estado de Ollama visto (para el encabezado)
VISTO = {}              # PC del trabajo -> hora de su último pedido


def vigilar_ia(previo):
    """Cada 20 s mira si Ollama responde; avisa solo cuando cambia."""
    while True:
        time.sleep(20)
        e = estado_ia()
        E_IA["e"] = e
        _IA_CACHE.update(t=time.time(), ok=e != "caida")
        if e == previo:
            continue
        if e == "ok":
            L.ok("IA", "Ollama responde de nuevo: la IA está lista.")
        elif e == "caida":
            L.aviso("IA", "Ollama dejó de responder. Abrí Ollama: sin él no se pueden generar informes "
                          "(los audios que lleguen quedan con error y se pueden volver a procesar).")
        else:
            L.aviso("IA", f"Ollama está abierto pero no tiene el modelo {CFG['modelo_ia']}.")
        L.estado(ia=e == "ok")
        previo = e


def titulo_de(n):
    """Nombre para mostrar: el nombre original del audio que llegó de otra PC."""
    f = DATOS / f"{n}.original.txt"
    return Path(f.read_text(encoding="utf-8").strip()).stem if f.exists() else n


_ESTUDIOS = {}         # nombre -> (firma del archivo, "Mamografía + Eco mamaria")


def estudios_de(n):
    """Estudios del informe, abreviados, para la lista (del final si ya se guardó; si no, de la IA)."""
    f = DATOS / f"{n}.final.txt"
    if not f.exists():
        f = DATOS / f"{n}.informe_ia.txt"
    try:
        st = f.stat()
    except OSError:
        return None
    firma = (f.name, st.st_size, st.st_mtime_ns)
    c = _ESTUDIOS.get(n)
    if c and c[0] == firma:
        return c[1]
    try:
        t = N.estudios_del_informe(f.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError):
        return None
    _ESTUDIOS[n] = (firma, t)
    return t


def origen_de(n):
    f = DATOS / f"{n}.origen.txt"
    return f.read_text(encoding="utf-8").strip() if f.exists() else LOCAL
ESTADO = {}           # nombre -> {"estado":..., "msg":...}
LOCK = threading.Lock()
COLA = queue.Queue()
COLA_DURADERA = None  # se abre únicamente en main, después de reservar el puerto


def mmss(t):
    return f"{int(t // 60)}:{int(t % 60):02d}"


def poner_estado(nombre, estado, msg=""):
    with LOCK:
        if nombre in BORRADOS: return
        if COLA_DURADERA is not None and not COLA_DURADERA.cambiar(nombre, estado): return
        ESTADO[nombre] = {"estado": estado, "msg": msg, "t": time.time()}
    L.estado(cola=en_proceso())


EN_PROCESO = ("en cola", "transcribiendo", "en pausa", "generando")
ENCOLADO = {}         # nombre -> cuándo entró a la cola (para el orden y la espera estimada)
DURACION = {}         # nombre -> duración del audio en segundos (cache)
BORRADOS = set()      # casos borrados mientras esperaban en la cola: el trabajador los saltea
# Pausa de la transcripción (solo desde la PC del servidor). Whisper se detiene entre tramo y tramo y se queda
# esperando con lo transcrito hasta ese momento; como todo se procesa de a uno, lo que sigue en la cola espera.
PAUSAS = {}           # nombre -> {"pedida": t, "por": dónde se pidió, "desde": t en que quedó detenida}
PAUSA_CV = threading.Condition()
PAUSADO_S = {}        # nombre -> segundos que estuvo en pausa (no cuentan como tiempo de Whisper)


class Cancelado(Exception):
    """El caso se borró mientras estaba en pausa: el trabajador deja de transcribirlo y sigue con el próximo."""
# Tiempos de referencia para estimar cuánto falta. Arrancan con los de actividad.csv y se ajustan con cada informe.
TIEMPOS = {"whisper_x": 0.15, "ia": 25.0, "n": 0}


def cargar_tiempos():
    """Promedio de los últimos 30 informes generados (actividad.csv)."""
    try:
        f = L.CARPETA / "actividad.csv"
        filas = [r for r in csv.DictReader(io.StringIO(f.read_text(encoding="utf-8-sig")), delimiter=";")
                 if r.get("evento") == "generado"][-30:]
    except (OSError, csv.Error, UnicodeDecodeError):
        return
    num = lambda v: float(v.replace(",", ".")) if v else None
    for r in filas:
        try:
            anotar_tiempo(num(r.get("duracion_audio_s")), num(r.get("whisper_s")), num(r.get("ia_s")))
        except ValueError:
            pass


def anotar_tiempo(dur, whisper_s, ia_s):
    a = 0.3 if TIEMPOS["n"] >= 3 else 1.0 / (TIEMPOS["n"] + 1)     # promedio móvil
    if dur and whisper_s and dur > 1:
        TIEMPOS["whisper_x"] += a * (whisper_s / dur - TIEMPOS["whisper_x"])
    if ia_s:
        TIEMPOS["ia"] += a * (ia_s - TIEMPOS["ia"])
    TIEMPOS["n"] += 1


def duracion_de(n):
    """Duración del audio en segundos (de la cabecera del WAV; si no es WAV, del final de la transcripción)."""
    if DURACION.get(n) is None:
        a = ruta_audio(n)
        d = duracion_wav(ruta=a) if a else None
        if d is None and (DATOS / f"{n}.json").exists():
            try:
                pal = json.loads((DATOS / f"{n}.json").read_text(encoding="utf-8")).get("palabras") or []
                d = pal[-1].get("fin") if pal else None
            except (ValueError, OSError):
                d = None
        if d is None:
            return None         # no se guarda: se vuelve a intentar cuando esté transcrito
        DURACION[n] = round(d, 1)
    return DURACION[n]


def trabajo_pendiente(n, est, ahora):
    """Segundos de trabajo que le quedan a un caso en proceso (aproximado)."""
    dur = duracion_de(n) or 60
    w, ia = TIEMPOS["whisper_x"] * dur + 2, TIEMPOS["ia"]
    desde = ahora - est.get("t", ahora)
    e, msg = est.get("estado"), est.get("msg", "")
    if e == "generando":
        return max(ia - desde, 3)
    if e == "transcribiendo":
        return max(w - desde, 2) + ia
    if e == "en pausa":
        return w + ia
    if e == "en cola" and msg.startswith("Esperando a la IA"):
        return ia
    return w + ia


def esperas():
    """Para cada caso en proceso: desde cuándo está en esa etapa, cuántos tiene adelante y cuánto falta."""
    ahora = time.time()
    with LOCK:
        enp = {n: dict(v) for n, v in ESTADO.items() if v.get("estado") in EN_PROCESO}
    orden = sorted(enp, key=lambda n: ENCOLADO.get(n, enp[n].get("t", 0)))
    out, acum = {}, 0.0
    for i, n in enumerate(orden):
        acum += trabajo_pendiente(n, enp[n], ahora)
        out[n] = {"desde": round(ahora - enp[n].get("t", ahora)), "adelante": i, "eta": round(acum)}
    return out


def empezar(nombre, estado, msg=""):
    """Como poner_estado, pero no arranca la etapa si el caso se borró mientras esperaba en la cola."""
    with LOCK:
        if nombre in BORRADOS:
            return False
        if COLA_DURADERA is not None and not COLA_DURADERA.cambiar(nombre, estado): return False
        ESTADO[nombre] = {"estado": estado, "msg": msg, "t": time.time()}
    L.estado(cola=en_proceso())
    return True


def en_proceso():
    with LOCK:
        return sum(1 for v in ESTADO.values() if v.get("estado") in EN_PROCESO)


def visible(n):
    """Cómo se nombra un caso en la ventana del servidor: «tmp7957» (info-01)."""
    try:
        return f"«{titulo_de(n)}» ({origen_de(n)})"
    except OSError:
        return f"«{n}»"


def datos_csv(n):
    return {"caso": n, "audio_original": titulo_de(n), "pc": origen_de(n), "medico": medico_de(n),
            "estudios": estudios_de(n), "usuario": U.nombre_de(usuario_de(n))}


# ------------------------------------------------- tiempo de revisión
# La página cuenta los segundos en que el caso está abierto y alguien lo está trabajando (teclado, mouse o audio
# sonando en el último minuto) y los manda con cada renovación del bloqueo, al cerrar y al guardar. Se acumulan acá,
# por caso, aunque se abra varias veces o desde otra PC. Al guardar se anotan en actividad.csv (columna revision_s).
REV_LOCK = threading.Lock()
REV_MAX_POR_PEDIDO = 600      # lo que puede juntar la página si se cortó la conexión un rato


def sumar_revision(n, seg_, pc):
    try:
        seg_ = float(seg_ or 0)
    except (TypeError, ValueError):
        return
    if not (0 < seg_ <= REV_MAX_POR_PEDIDO) or not (DATOS / f"{n}.dictado.txt").exists():
        return
    f = DATOS / f"{n}.revision.json"
    with REV_LOCK:
        try:
            d = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
        except (OSError, ValueError):
            d = {}
        d["s"] = round(float(d.get("s", 0)) + seg_, 1)
        por = d.setdefault("por_pc", {})
        por[pc] = round(float(por.get(pc, 0)) + seg_, 1)
        d.setdefault("desde", time.strftime("%Y-%m-%d %H:%M:%S"))
        d["ultimo"] = time.strftime("%Y-%m-%d %H:%M:%S")
        try:
            f.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        except OSError:
            L.debug("CASO", f"No se pudo anotar el tiempo de revisión de {n}", det=[repr(sys.exc_info()[1])])


def revision_de(n):
    """Segundos de revisión activa acumulados del caso (None si no se midió)."""
    f = DATOS / f"{n}.revision.json"
    try:
        return round(float(json.loads(f.read_text(encoding="utf-8")).get("s", 0))) if f.exists() else None
    except (OSError, ValueError, TypeError):
        return None


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


# ----------------------------------------------------------------- casos
def ruta_audio(nombre):
    f = DATOS / f"{nombre}.audio.txt"
    if f.exists():
        p = Path(f.read_text(encoding="utf-8").strip())
        if p.exists():
            return p
    for p in NUEVOS.iterdir():
        if p.suffix.lower() in EXT_AUDIO and p.stem == nombre:
            return p
    return None


def medico_de(n):
    f = DATOS / f"{n}.medico.txt"
    return f.read_text(encoding="utf-8").strip() if f.exists() else ""


# ------------------------------------------------- transcriptor del caso
# <caso>.usuario.txt = con el estilo de quién se arma (el que estaba usando la página en esa PC al llegar el audio,
# o el que pidió «Volver a generar»). <caso>.estilo.txt = con el estilo de quién lo armó la IA la última vez
# (vacío = estilo general). Si el que lo abre es otro, la página avisa y ofrece regenerarlo con su estilo.
def usuario_de(n):
    f = DATOS / f"{n}.usuario.txt"
    u = f.read_text(encoding="utf-8").strip() if f.exists() else ""
    return u if u and U.existe(u) else ""


def poner_usuario_caso(n, usuario):
    f = DATOS / f"{n}.usuario.txt"
    if usuario:
        escribir_atomico(f, usuario)
    else:
        f.unlink(missing_ok=True)


def estilo_de(n):
    """None si nunca se generó con la información de estilo (casos anteriores a los usuarios)."""
    f = DATOS / f"{n}.estilo.txt"
    return f.read_text(encoding="utf-8").strip() if f.exists() else None


# ------------------------------------------------- médico reconocido por la voz (voces.py)
# <caso>.voz.json = {"h": huella, "seg": segundos de voz, "det": resultado de la detección, "medico_por": quién
# puso el médico del caso ("voz" = se reconoció solo, "usuaria" = se eligió al revisar, "pc" = el médico elegido
# para los audios de esa PC, "" = sin médico), "medico_ia": con qué médico armó el informe la IA}.
# La muestra de voz de un médico se guarda en voces/huellas.json recién cuando se guarda el informe con ese médico
# (o cuando se etiqueta a mano desde «Agrupar voces»).
VOZ_CACHE = {}
VOZ_LOCK = threading.Lock()


def voz_de(n):
    try:
        return json.loads((DATOS / f"{n}.voz.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def guardar_voz(n, v):
    f = DATOS / f"{n}.voz.json"
    tmp = f.with_name(f.name + ".nuevo")
    tmp.write_text(json.dumps(v, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    os.replace(tmp, f)
    VOZ_CACHE.pop(n, None)


def anotar_voz(n, **campos):
    """Cambia campos de <caso>.voz.json (si existe)."""
    with VOZ_LOCK:
        v = voz_de(n)
        if v is not None:
            v.update(campos)
            guardar_voz(n, v)


def pct_voz(p):
    return f"{round((p or 0) * 100)} %"


def resumen_voz(n):
    """Lo que la lista y la barra del caso muestran del reconocimiento de voz (sin la huella)."""
    f = DATOS / f"{n}.voz.json"
    try:
        mt = f.stat().st_mtime_ns
    except OSError:
        return None
    c = VOZ_CACHE.get(n)
    if not c or c[0] != mt:
        v = voz_de(n)
        if not v:
            return None
        d = v.get("det") or {}
        c = (mt, {"estado": d.get("estado"), "medico": d.get("medico"), "puntaje": d.get("puntaje"),
                  "segundo": d.get("segundo"), "puntaje2": d.get("puntaje2"), "motivo": d.get("motivo"),
                  "muestras": d.get("muestras"), "seg": v.get("seg"), "por": v.get("medico_por") or "",
                  "medico_ia": v.get("medico_ia")})
        VOZ_CACHE[n] = c
    r = dict(c[1])
    m = VOZ.muestra(n)
    r["muestra"] = m.get("medico") if m else None       # su voz ya cuenta como muestra de ese médico
    return r


def calcular_voz(n, a, palabras, al_procesar=True):
    """Huella de voz del audio y detección del médico. Si el resultado es «seguro» y el caso no tiene médico
    elegido, lo asigna. Nunca frena el procesamiento: si algo falla, se anota y el caso sigue sin médico."""
    if not VOZ.modelo_listo():
        if L.una_vez("voz_sin_modelo", 3600):
            err = VOZ._DESCARGA.get("error")
            L.aviso("VOZ", "El reconocimiento de voz todavía no está listo (falta el modelo"
                           + (f": {err}" if err else ", se está bajando") + "). Este audio queda sin médico automático.")
        return None
    t0 = time.time()
    try:
        h, seg = VOZ.huella_archivo(a, palabras, CFG)
    except Exception as ex:
        L.aviso("VOZ", f"{visible(n)}: no se pudo calcular la huella de voz ({mensaje_amigable(ex)}).", exc=True)
        return None
    det = VOZ.detectar(h, excluir=n, cfg=CFG)
    with VOZ_LOCK:
        prev = voz_de(n) or {}
        med = medico_de(n)
        por = prev.get("medico_por") or ""
        if med and por == "voz" and al_procesar:         # lo había puesto la voz: se vuelve a decidir
            (DATOS / f"{n}.medico.txt").unlink(missing_ok=True)
            med = ""
        if med:
            por = por or "pc"
        elif det.get("estado") == "seguro":
            (DATOS / f"{n}.medico.txt").write_text(det["medico"], encoding="utf-8")
            por = "voz"
        else:
            por = ""
        guardar_voz(n, {"v": 1, "modelo": VOZ.VERSION_HUELLA, "h": h, "seg": seg, "det": det, "fecha": time.time(),
                        "medico_por": por, "medico_ia": prev.get("medico_ia")})
    e = det.get("estado")
    if det.get("ranking"):
        L.debug("VOZ", f"{visible(n)}: huella en {L.seg(time.time() - t0)} con {seg} s de voz · "
                       + ", ".join(f"{m} {pct_voz(p)}" for m, p in det["ranking"]))
    if med and por != "voz":
        L.info("VOZ", f"{visible(n)}: médico ya elegido «{med}»" + (
            f"; la voz se parece más a «{det['medico']}» ({pct_voz(det['puntaje'])})" if det.get("medico") and det["medico"] != med
            else f"; la voz coincide ({pct_voz(det.get('puntaje'))})" if det.get("medico") == med else "") + ".")
    elif e == "seguro":
        L.ok("VOZ", f"{visible(n)}: médico reconocido por la voz: «{det['medico']}» (parecido {pct_voz(det['puntaje'])}, "
                    f"{L.plural(det['muestras'], 'muestra')}).")
    elif e == "dudoso":
        L.info("VOZ", f"{visible(n)}: voz dudosa, ¿«{det['medico']}»? ({pct_voz(det['puntaje'])}; {det.get('motivo')}). "
                      f"La IA usa la plantilla general; el médico se confirma al revisar.")
    elif e == "corto":
        L.info("VOZ", f"{visible(n)}: muy poca voz ({seg} s) para reconocer al médico.")
    else:
        L.info("VOZ", f"{visible(n)}: voz sin reconocer ({det.get('motivo')}). Elegí el médico al revisar: al "
                      f"guardar, su voz queda registrada.")
    return det


def muestra_al_guardar(n):
    """Al guardar el Word: la voz del caso pasa a ser muestra del médico elegido (o deja de serlo si se quitó)."""
    v = voz_de(n)
    if not v or not v.get("h") or v.get("modelo") != VOZ.VERSION_HUELLA:
        return v
    med = medico_de(n)
    antes = VOZ.muestra(n)
    if not med:
        if antes:
            VOZ.quitar(n)
            L.info("VOZ", f"{visible(n)} se guardó sin médico: su voz ya no cuenta como muestra de «{antes['medico']}».")
        return v
    k = VOZ.agregar(n, med, v["h"], "guardado", v.get("seg"))
    if not antes or antes.get("medico") != med:
        minimo = int(VOZ.parametros(CFG)["min_muestras"])
        L.ok("VOZ", f"Voz de «{med}» registrada con {visible(n)}: tiene {L.plural(k, 'muestra')}"
                    + (" (desde ahora se puede reconocer solo)" if k == minimo else
                       f" (con {minimo} se reconoce solo)" if k < minimo else "") + ".")
    return v


def actualizar_muestra(n, med):
    """El médico de un caso ya guardado se cambió a mano: se corrige su muestra de voz al momento."""
    v = voz_de(n)
    if not v or not v.get("h") or v.get("modelo") != VOZ.VERSION_HUELLA:
        return
    if med:
        VOZ.agregar(n, med, v["h"], "guardado", v.get("seg"))
    else:
        VOZ.quitar(n)


def casos_sin_etiquetar():
    """Casos sin médico cuya huella de voz todavía no es muestra de nadie (para «Agrupar voces»). Los que ya
    tienen médico no aparecen: su voz se registra sola al guardar el informe."""
    out = []
    with LOCK:
        ocupados = {k for k, e in ESTADO.items() if e.get("estado") in EN_PROCESO}
    for f in DATOS.glob("*.voz.json"):
        n = f.name[:-len(".voz.json")]
        if n in ocupados or VOZ.muestra(n) or medico_de(n):
            continue
        v = voz_de(n)
        if v and v.get("h") and v.get("modelo") == VOZ.VERSION_HUELLA:
            out.append((n, v))
    return out


def ficha_caso(n):
    return {"nombre": n, "titulo": titulo_de(n), "paciente": PAC.de(DATOS, n), "medico": medico_de(n),
            "audio": ruta_audio(n) is not None, "origen": origen_de(n), "revisado": (DATOS / f"{n}.final.txt").exists(),
            "fecha": (lambda a: a.stat().st_mtime if a else None)(ruta_audio(n)), "dur": duracion_de(n)}


def grupos_de_voces():
    items = casos_sin_etiquetar()
    hs = {n: v["h"] for n, v in items}
    grupos = []
    for g in VOZ.agrupar(list(hs.items()), CFG):
        det = VOZ.detectar(VOZ.centro([hs[x] for x in g]), cfg=CFG)
        fichas = []
        for x in g:
            try:
                fichas.append(dict(ficha_caso(x), voz=resumen_voz(x)))
            except OSError:
                pass
        fichas.sort(key=lambda c: c.get("fecha") or 0, reverse=True)
        grupos.append({"casos": fichas, "sugerencia": {k: det.get(k) for k in ("estado", "medico", "puntaje",
                                                                               "segundo", "puntaje2")}})
    return {"grupos": grupos, "total": len(items)}


def hilo_voces():
    """Al arrancar: baja el modelo de voz si falta y calcula la huella de los casos que todavía no la tienen
    (sin cambiarles el médico). Los ya guardados con médico suman su voz como muestra."""
    if not VOZ.modelo_listo():
        L.info("VOZ", "Bajando el modelo de reconocimiento de voz (unos 26 MB, una sola vez)…")
        if not VOZ.descargar_modelo():
            L.aviso("VOZ", f"No se pudo bajar el modelo de reconocimiento de voz ({VOZ._DESCARGA['error']}). Se vuelve "
                           f"a intentar al reiniciar el servidor; mientras tanto los audios quedan sin médico automático.")
            return
        L.ok("VOZ", "Modelo de reconocimiento de voz listo.")
    hechos = sumadas = 0
    for f in sorted(DATOS.glob("*.dictado.txt")):
        n = f.name[:-len(".dictado.txt")]
        v = voz_de(n)
        if v and v.get("modelo") == VOZ.VERSION_HUELLA:
            continue
        while TRABAJO.get("ocupado"):          # primero lo que está en la cola
            time.sleep(5)
        with LOCK:
            if ESTADO.get(n, {}).get("estado") in EN_PROCESO:
                continue
        a = ruta_audio(n)
        if a is None:
            continue
        try:
            pal = json.loads((DATOS / f"{n}.json").read_text(encoding="utf-8")).get("palabras")
            h, seg = VOZ.huella_archivo(a, pal, CFG)
        except Exception:
            L.debug("VOZ", f"No se pudo calcular la huella de voz de {visible(n)}.", det=[repr(sys.exc_info()[1])])
            continue
        med = medico_de(n)
        with VOZ_LOCK:
            guardar_voz(n, {"v": 1, "modelo": VOZ.VERSION_HUELLA, "h": h, "seg": seg,
                            "det": VOZ.detectar(h, excluir=n, cfg=CFG), "fecha": time.time(),
                            "medico_por": "pc" if med else "", "medico_ia": med or None})
        hechos += 1
        if h and med and (DATOS / f"{n}.final.txt").exists() and not VOZ.muestra(n):
            VOZ.agregar(n, med, h, "revisado antes", seg)
            sumadas += 1
    if hechos:
        L.ok("VOZ", f"Huella de voz calculada para {L.plural(hechos, 'caso anterior', 'casos anteriores')}"
                    + (f"; {L.plural(sumadas, 'informe ya guardado', 'informes ya guardados')} con médico "
                       f"{'sumó su voz' if sumadas == 1 else 'sumaron su voz'} a las muestras" if sumadas else "") + ".")


COLOR_TIPO = {"numero": "rojo", "completar": "rojo", "dudoso": "amarillo", "bajaconf": "amarillo",
              "verificar": "turq", "plantilla": "gris"}


def resumen_avisos(n, m):
    """Cuántas marcas de cada color quedan y qué datos faltan (para la lista y el modo compacto).
    Si hay borrador se cuentan las marcas que siguen en él (las ya revisadas no cuentan)."""
    r = {"rojo": 0, "amarillo": 0, "turq": 0, "gris": 0, "faltan": [], "huecos": []}
    borrador = BOR.leer(DATOS, n)
    if borrador["html"] is not None:
        h = borrador["html"]
        for tipo in re.findall(r'<mark class="m-(\w+)', h):
            if tipo in COLOR_TIPO:
                r[COLOR_TIPO[tipo]] += 1
        for tipo in re.findall(r'class="ln[^"]*\bl-(plantilla|verificar)\b', h):
            r[COLOR_TIPO[tipo]] += 1
    else:
        for ln in m.get("lineas", []):
            if ln.get("linea"):
                r[COLOR_TIPO[ln["linea"]]] += 1
            for sg in ln.get("segs", []):
                if sg.get("tipo") in COLOR_TIPO:
                    r[COLOR_TIPO[sg["tipo"]]] += 1
    ok = set(borrador["omisiones_ok"])
    for o in m.get("omisiones", []):
        if o["dato"] in ok:
            continue
        if o.get("hueco"):
            r["huecos"].append(mmss(o.get("ini", o.get("seg") or 0)))
        else:
            r["faltan"].append(o["dato"])
    return r


def revisado_en(n):
    """Cuándo se guardó el Word por última vez (para «Revisados hoy» en la pantalla de inicio)."""
    try:
        return (DATOS / f"{n}.final.txt").stat().st_mtime
    except OSError:
        return None


INDICE_CASOS = IndiceCasos()


def fecha_caso(n, audio, defecto):
    try:
        return (audio if audio else DATOS / f'{n}.informe_ia.txt').stat().st_mtime
    except OSError:
        return defecto


def listar_casos(pc=LOCAL, remoto=False):
    nombres = {p.stem: p for p in NUEVOS.iterdir() if p.suffix.lower() in EXT_AUDIO}
    with LOCK:
        for n, e in ESTADO.items():
            if e.get('estado') in EN_PROCESO + ('error',): nombres.setdefault(n, None)
    for f in DATOS.glob("*.informe_ia.txt"):
        nombres.setdefault(f.name[:-len(".informe_ia.txt")], None)
    inventario = INDICE_CASOS.inventario(DATOS)
    INDICE_CASOS.depurar(nombres)
    try:
        voz_st = VOZ.HUELLAS.stat()
        firma_voz = (voz_st.st_size, voz_st.st_mtime_ns)
    except FileNotFoundError:
        firma_voz = None
    casos = []
    esp = esperas()
    for n in nombres:
        firma = (str(DATOS), tuple(inventario.get(n + sufijo) for sufijo in SUFIJOS_CASO), firma_voz)
        def dato(campo, calcular):
            return INDICE_CASOS.obtener((n, campo), firma, calcular)
        with LOCK:
            est = dict(ESTADO.get(n, {}))
        listo = (DATOS / f"{n}.informe_ia.txt").exists()
        revisado = (DATOS / f"{n}.final.txt").exists()
        if not est or est.get("estado") == "listo":
            est = {"estado": "revisado" if revisado else ("listo" if listo else "nuevo"), "msg": ""}
        marcas = avisos = None
        mf = DATOS / f"{n}.marcas.json"
        if listo and mf.exists():
            try:
                m = dato("marcas", lambda: json.loads(mf.read_text(encoding="utf-8")))
                marcas = m.get("total")
                if not revisado:
                    avisos = dato("avisos", lambda: resumen_avisos(n, m))
            except (ValueError, OSError):
                pass
        a = ruta_audio(n)
        casos.append({"nombre": n, "estado": est["estado"], "msg": est.get("msg", ""), "marcas": marcas,
                      "medico": dato("medico_de", lambda: medico_de(n)), "origen": dato("origen_de", lambda: origen_de(n)), "avisos": avisos, "bloqueado_por": R.bloqueado_por(n, pc),
                      "titulo": dato("titulo_de", lambda: titulo_de(n)), "espera": esp.get(n), "paciente": dato("paciente", lambda: PAC.de(DATOS, n)),
                      "usuario": dato("usuario_de", lambda: usuario_de(n)), "estilo": dato("estilo_de", lambda: estilo_de(n)),
                      "voz": dato("resumen_voz", lambda: resumen_voz(n)),
                      "estudios": dato("estudios_de", lambda: estudios_de(n)) if listo else None, "dur": dato("duracion_de", lambda: duracion_de(n)),
                      "revisado_en": revisado_en(n) if revisado else None,
                      "puede_borrar": not (remoto and (dato("origen_de", lambda: origen_de(n)) != pc or pc == LOCAL))
                                      and est["estado"] not in ("transcribiendo", "generando"),
                      "puede_pausar": not remoto and est["estado"] == "transcribiendo" and n not in PAUSAS,
                      "puede_reanudar": not remoto and (est["estado"] == "en pausa" or n in PAUSAS),
                      "pausa_pedida": n in PAUSAS and est["estado"] != "en pausa",
                      "fecha": fecha_caso(n, a, est.get('t', INICIO))})
    casos.sort(key=lambda c: c["fecha"], reverse=True)
    return casos


def lineas_para_web(salida, dictado, palabras):
    marcado = N.marcar(salida, dictado, palabras)
    out = []
    for ln in marcado:
        texto = "".join(t for t, _, _ in ln["segs"])
        segs = []
        for t, tipo, mot in ln["segs"]:
            seg = {"t": t}
            if tipo:
                seg.update(tipo=tipo, motivo=mot, seg=N.buscar_tiempo(t, palabras))
            segs.append(seg)
        out.append({"segs": segs, "linea": ln["linea"],
                    "motivo": (ln.get("motivo") or N.MOTIVO_LINEA.get(ln["linea"])) if ln["linea"] else None,
                    "titulo": ln["titulo"], "seg": N.buscar_tiempo(texto, palabras) if texto.strip() else None})
    total = sum(1 for l in out if l["linea"]) + sum(1 for l in out for s in l["segs"] if s.get("tipo"))
    return out, total


VERSION_MARCAS = 2      # 2: motivos detallados ("Dictado: 12 / Informe: 2") e inicio/fin de los huecos


def guardar_marcas(n, salida, dictado, palabras, huecos=None):
    lineas, total = lineas_para_web(salida, dictado, palabras)
    om = N.omisiones(dictado, salida, palabras)
    om += [{"dato": f"posible parte no transcrita {mmss(h['ini'])}–{mmss(h['fin'])}", "seg": h["ini"] + 0.5,
            "hueco": True, "ini": h["ini"], "fin": h["fin"]} for h in (huecos or [])]
    nuevos = N.estudios_sin_plantilla(salida)
    escribir_atomico(DATOS / f"{n}.marcas.json", json.dumps({"v": VERSION_MARCAS, "lineas": lineas, "omisiones": om, "estudios_nuevos": nuevos,
                                                       "total": total + len(om)}, ensure_ascii=False))
    return lineas, om


def cargar_caso(nombre):
    ia = DATOS / f"{nombre}.informe_ia.txt"
    if not ia.exists():
        return None
    trans = json.loads((DATOS / f"{nombre}.json").read_text(encoding="utf-8"))
    mf = DATOS / f"{nombre}.marcas.json"
    m = json.loads(mf.read_text(encoding="utf-8")) if mf.exists() else {}
    if m.get("v") == VERSION_MARCAS:
        lineas, om = m["lineas"], m["omisiones"]
    else:
        lineas, om = guardar_marcas(nombre, ia.read_text(encoding="utf-8"), trans["texto"], trans["palabras"],
                                    trans.get("huecos"))
    borrador = BOR.leer(DATOS, nombre)
    om_ok = borrador["omisiones_ok"]
    fin = DATOS / f"{nombre}.final.txt"
    # cada palabra con su forma normalizada ("veintitrés" -> "23"), para ubicar cada línea del informe en el dictado
    palabras = [dict(w, n=re.sub(r"[^a-z0-9.]", "", N.normalizar(w["p"])).strip(".")) for w in trans["palabras"]]
    return {"nombre": nombre, "dictado": trans["texto"], "palabras": palabras, "lineas": lineas,
            "omisiones": om, "omisiones_ok": om_ok, "medico": medico_de(nombre), "voz": resumen_voz(nombre),
            "paciente": PAC.de(DATOS, nombre), "titulo": titulo_de(nombre),
            "estudios": estudios_de(nombre), "dur": duracion_de(nombre),
            "estudios_nuevos": N.estudios_sin_plantilla(ia.read_text(encoding="utf-8")),
            "borrador": borrador["html"],
            "borrador_revision": borrador.get("revision", 0),
            "revisado": fin.exists(), "tiene_audio": ruta_audio(nombre) is not None,
            "estilo": _estilo_para_web(nombre)}


def _estilo_para_web(n):
    e = estilo_de(n)
    if e is None:
        return None
    return {"usuario": e, "nombre": U.nombre_de(e) if e else ""}


def forma_de_onda(nombre, n=1600):
    """Picos del audio en n tramos (0-100) para dibujar la forma de onda. Se guarda en .onda.json."""
    a = ruta_audio(nombre)
    if a is None:
        return None
    st = a.stat()
    firma = f"{st.st_size}-{int(st.st_mtime)}-{n}"
    cache = DATOS / f"{nombre}.onda.json"
    if cache.exists():
        try:
            d = json.loads(cache.read_text(encoding="utf-8"))
            if d.get("firma") == firma:
                return d
        except ValueError:
            pass
    import numpy as np
    from fase1_transcribir import cargar_audio
    x = np.abs(cargar_audio(a))
    dur = len(x) / 16000.0
    if not len(x):
        return {"firma": firma, "dur": 0, "picos": []}
    k = max(1, len(x) // n)
    tramos = x[: (len(x) // k) * k].reshape(-1, k)
    picos = tramos.max(axis=1)
    ref = float(np.percentile(picos, 98)) or 1.0
    picos = np.clip(picos / ref, 0, 1) ** 0.7
    d = {"firma": firma, "dur": round(dur, 3), "picos": [int(round(v * 100)) for v in picos]}
    cache.write_text(json.dumps(d), encoding="utf-8")
    return d


# -------------------------------------------------------- procesamiento
ARCHIVOS_RESULTADO = ('.json', '.dictado.txt', '.informe_ia.txt', '.marcas.json')


def firma_audio(ruta):
    s = ruta.stat()
    return [str(ruta.resolve()), s.st_size, s.st_mtime_ns]


def hash_resultado(ruta):
    h = hashlib.sha256()
    with ruta.open('rb') as f:
        for bloque in iter(lambda: f.read(65536), b''): h.update(bloque)
    return h.hexdigest()


def resultado_confirmado(n):
    if COLA_DURADERA is None: return False
    fila = COLA_DURADERA.obtener(n)
    if not fila or fila['estado'] not in CP.ACTIVOS: return False
    try:
        d = json.loads((DATOS / f'{n}.procesamiento.json').read_text(encoding='utf-8'))
        a = ruta_audio(n)
        return (d['v'] == 1 and d['token'] == fila['token'] and a is not None and d['audio'] == firma_audio(a)
                and set(d['archivos']) == set(ARCHIVOS_RESULTADO)
                and all(hash_resultado(DATOS / (n+s)) == d['archivos'][s] for s in ARCHIVOS_RESULTADO))
    except (OSError, ValueError, KeyError, TypeError): return False


def confirmar_resultado(n, firma):
    if COLA_DURADERA is None: return
    fila = COLA_DURADERA.obtener(n)
    if fila is None: raise CP.ErrorCola('No existe la tarea que produjo el resultado.')
    if firma != firma_audio(ruta_audio(n)): raise OSError('El audio cambió durante el procesamiento.')
    d = {'v': 1, 'token': fila['token'], 'audio': firma,
         'archivos': {s: hash_resultado(DATOS / (n+s)) for s in ARCHIVOS_RESULTADO}}
    escribir_atomico(DATOS / f'{n}.procesamiento.json', json.dumps(d, ensure_ascii=False))


def sincronizar_terminal(n):
    """Reconciliar una confirmación de disco cuya respuesta local pudo perderse."""
    if COLA_DURADERA is None: return False
    fila = COLA_DURADERA.obtener(n)
    if fila is None: raise CP.ErrorCola('No existe la tarea duradera.')
    e = fila['estado']
    if e in CP.ACTIVOS: return False
    with LOCK:
        if e in ('borrando', 'cancelado'): BORRADOS.add(n)
        if e == 'cancelado': ESTADO.pop(n, None)
        else: ESTADO[n] = {'estado': 'listo' if e == 'listo' else 'error',
                          'msg': '' if e == 'listo' else 'Revisar la tarea conservada antes de reintentar.', 't': time.time()}
    return True


def trabajador():
    whisper = None
    while True:
        lote = [COLA.get()]
        while REINICIO.get("detener"):      # reinicio en camino: no empieza nada nuevo (queda en la cola)
            time.sleep(0.5)
        lote = LOTES.formar(COLA, lote[0], CFG, duracion_de)
        lote_desde = time.perf_counter()
        TRABAJO.update(ocupado=True, desde=time.time())
        trans, info = {}, {}
        etapa = "WHISPER"
        fallo_persistencia = False
        if len(lote) > 1:
            L.info("WHISPER", f"Procesando {len(lote)} audios juntos: primero se transcriben todos y "
                              f"después la IA arma los informes.")
        try:
            # 1) Whisper para todo el lote
            lote = [n for n in lote if n not in BORRADOS]
            for n in lote:
                try:
                    if n in BORRADOS:
                        continue
                    if sincronizar_terminal(n):
                        continue
                    if resultado_confirmado(n):
                        poner_estado(n, 'listo')
                        continue
                    punto_de_pausa(n)  # una pausa recuperada no necesita cargar modelos
                    a = ruta_audio(n)
                    if a is None:
                        poner_estado(n, "error", "No encuentro el audio")
                        L.error("AUDIO", f"{visible(n)}: no encuentro el archivo de audio (¿se borró o se movió?).")
                        L.actividad("error", **datos_csv(n), detalle="No encuentro el audio")
                        continue
                    if not empezar(n, "transcribiendo", "Transcribiendo el audio…"):
                        continue
                    inicio_caso = time.perf_counter()
                    firma_entrada = firma_audio(a) if COLA_DURADERA is not None else None
                    t0 = inicio_caso
                    recuperadas = 0
                    carga_whisper = 0.0
                    cache_usada = False
                    firma_asr = None
                    PAUSADO_S[n] = 0
                    try:
                        if not SIMULAR and CFG.get("reusar_transcripcion", True) is True:
                            from importlib.metadata import version, PackageNotFoundError
                            try:
                                version_whisper = version('faster-whisper') + '/' + version('ctranslate2')
                            except PackageNotFoundError:
                                version_whisper = 'desconocida'
                            from fase1_transcribir import VOCAB_DEF
                            try:
                                firma_asr = CACHE_ASR.firma(a, {'modelo': CFG['modelo_whisper'],
                                    'dispositivo': CFG.get('dispositivo_whisper','cuda'), 'faster_whisper': version_whisper},
                                    [AQUI/'fase1_transcribir.py', AQUI/'huecos.py', VOCAB_DEF])
                                previa = CACHE_ASR.leer(DATOS/f'{n}.transcripcion_cache.json', firma_asr)
                                if previa is not None:
                                    trans[n] = previa
                                    cache_usada = True
                            except OSError:
                                L.aviso('WHISPER', 'No se pudo leer la caché; se transcribe de nuevo.', exc=True)
                        if cache_usada:
                            L.debug('WHISPER', 'Se reutiliza una transcripción verificada por contenido y parámetros.')
                        elif SIMULAR:
                            of = DATOS / f"{n}.original.txt"
                            fuente = Path(of.read_text(encoding="utf-8").strip()).stem if of.exists() else n
                            trans[n] = json.loads((AQUI / "resultados" / "fase1" / "json" / f"{fuente}.json")
                                                  .read_text(encoding="utf-8"))["con_vocab"]
                            trans[n]["huecos"] = json.loads(os.environ.get("SIMULAR_HUECOS", "[]"))
                            dem, paso = float(os.environ.get("SIMULAR_DEMORA", "0")), 0.25
                            for k in range(int(dem / paso)):      # tramos simulados (para probar la pausa)
                                time.sleep(paso)
                                avance(n, "Transcribiendo el audio")((k + 1) * paso * 10, dem * 10)
                        else:
                            if whisper is None:
                                N.liberar_ia(CFG["modelo_ia"])
                                carga_desde = time.perf_counter()
                                from fase1_transcribir import cargar_modelo
                                poner_estado(n, "transcribiendo", "Cargando Whisper…")
                                L.info("WHISPER", f"Cargando Whisper {CFG['modelo_whisper']} " + ("en la placa de video…" if CFG.get("dispositivo_whisper", "cuda") == "cuda" else "en el procesador (más lento)…"))
                                tc = time.time()
                                with contextlib.redirect_stdout(L.SalidaAlRegistro("WHISPER")):
                                    whisper = cargar_modelo(CFG["modelo_whisper"], CFG.get("dispositivo_whisper", "cuda"))
                                carga_whisper = time.perf_counter() - carga_desde
                                L.ok("WHISPER", f"Whisper cargado en {L.seg(time.time() - tc)}.")
                                poner_estado(n, "transcribiendo", "Transcribiendo el audio…")
                                t0 = time.perf_counter()
                            from fase1_transcribir import transcribir, leer_vocabulario, cargar_audio, VOCAB_DEF
                            import huecos as H
                            prompt = leer_vocabulario(VOCAB_DEF)
                            punto_de_pausa(n)           # se pidió la pausa mientras se cargaba Whisper
                            t = transcribir(whisper, a, prompt, al_avanzar=avance(n, "Transcribiendo el audio"))
                            poner_estado(n, "transcribiendo", "Revisando partes que Whisper pudo saltear…")
                            pal, pend = H.reparar(whisper, cargar_audio(a), t["palabras"], prompt,
                                                  al_avanzar=avance(n, "Revisando partes que Whisper pudo saltear"))
                            recuperadas = max(0, len(pal) - len(t["palabras"]))
                            trans[n] = {"texto": H.texto_de(pal), "palabras": pal, "huecos": pend}
                        punto_de_pausa(n)           # una pausa pedida justo al final se cumple acá
                    except Cancelado:
                        PAUSADO_S.pop(n, None)
                        trans.pop(n, None)
                        L.info("WHISPER", f"Se dejó de transcribir {visible(n)}: se borró mientras estaba en pausa.")
                        continue
                    if firma_asr is not None and not cache_usada:
                        try:
                            CACHE_ASR.guardar(DATOS/f'{n}.transcripcion_cache.json', firma_asr, trans[n])
                        except OSError:
                            L.aviso('WHISPER', 'No se pudo conservar la caché; el informe continúa.', exc=True)
                    escribir_atomico(DATOS / f"{n}.json", json.dumps(trans[n], ensure_ascii=False, indent=1))
                    escribir_atomico(DATOS / f"{n}.dictado.txt", trans[n]["texto"])
                    PAC.calcular(DATOS, n, forzar=True)      # nombre del paciente para la lista (no va al informe)
                    escribir_atomico(DATOS / f"{n}.audio.txt", str(a.resolve()))
                    calcular_voz(n, a, trans[n]["palabras"])     # médico por la voz (antes de la IA)
                    dur = duracion_wav(ruta=a)
                    if dur is None and trans[n]["palabras"]:
                        dur = trans[n]["palabras"][-1].get("fin")
                    info[n] = {"dur": dur, "whisper": time.perf_counter() - t0 - PAUSADO_S.pop(n, 0),
                               "palabras": len(trans[n]["palabras"]), "cache_asr": cache_usada, "carga_whisper_s": carga_whisper, "inicio_caso": inicio_caso, 'firma_audio': firma_entrada}
                    partes = [f"audio {L.mmss(dur)}" if dur else None, L.plural(info[n]["palabras"], "palabra")]
                    if recuperadas:
                        partes.append(f"la segunda pasada recuperó {L.plural(recuperadas, 'palabra')}")
                    L.ok("WHISPER", f"{visible(n)} transcrito en {L.seg(info[n]['whisper'])} · "
                                    + " · ".join(x for x in partes if x))
                    for h in trans[n].get("huecos") or []:
                        L.aviso("WHISPER", f"{visible(n)}: posible parte no transcrita entre {mmss(h['ini'])} y "
                                           f"{mmss(h['fin'])}. Revisarla escuchando.")
                    poner_estado(n, "en cola", "Esperando a la IA…")
                except CP.ErrorCola:
                    raise
                except Exception as ex:
                    trans.pop(n, None)
                    info.pop(n, None)
                    PAUSADO_S.pop(n, None)
                    poner_estado(n, 'error', mensaje_amigable(ex))
                    L.error('WHISPER', 'Falló un audio; se continúa con los demás del lote.', exc=True)
                    L.actividad('error', **datos_csv(n), detalle='WHISPER: ' + mensaje_amigable(ex))
            if whisper is not None:      # liberar la placa para la IA
                del whisper
                whisper = None
                gc.collect()
                L.debug("WHISPER", "Whisper liberado de la placa de video.")
            # 2) IA
            etapa = "IA"
            banco = N.cargar_banco() if trans else []
            for n in trans:
                try:
                    if n in BORRADOS:
                        continue
                    punto_de_pausa(n)
                    esperar_ia(n, list(trans))
                    if not empezar(n, "generando", "La IA está armando el informe…"):
                        continue
                    t0 = time.perf_counter()
                    tokens = ""
                    metricas_ia = {}
                    dic = trans[n]["texto"]
                    usu = usuario_de(n) or None
                    if SIMULAR:
                        of = DATOS / f"{n}.original.txt"
                        fuente = Path(of.read_text(encoding="utf-8").strip()).stem if of.exists() else n
                        salida = (AQUI / "resultados" / "fase2" / "gemma4_12b" / f"{fuente}.json")
                        salida = json.loads(salida.read_text(encoding="utf-8"))["salida"]
                        time.sleep(float(os.environ.get("SIMULAR_DEMORA", "0")))
                    else:
                        med = medico_de(n) or None
                        # sin médico confirmado (voz dudosa o sin reconocer): plantilla general, sin estilos de médico
                        sin_est = not med and resumen_voz(n) is not None
                        ej = N.elegir_ejemplos(dic, banco, k=CFG["ejemplos_por_informe"], excluir=n, medico=med,
                                               usuario=usu)
                        salida, _, t_in, t_out = N.llamar_ia(CFG["modelo_ia"], N.armar_mensajes(dic, ej, med, sin_estilos=sin_est, usuario=usu), metricas=metricas_ia)
                        tokens = f"{t_in or '?'} tokens de entrada, {t_out or '?'} de salida"
                    escribir_atomico(DATOS / f"{n}.informe_ia.txt", salida)
                    escribir_atomico(DATOS / f"{n}.estilo.txt", usu or "")
                    anotar_voz(n, medico_ia=medico_de(n) or "")
                    for viejo in (f"{n}.marcas.json", f"{n}.borrador.html", f"{n}.borrador.json", f"{n}.final.txt", f"{n}.formato.json"):
                        (DATOS / viejo).unlink(missing_ok=True)
                    (DATOS / f"{n}.omisiones_ok.json").unlink(missing_ok=True)
                    lineas, om = guardar_marcas(n, salida, dic, trans[n]["palabras"], trans[n].get("huecos"))
                    confirmar_resultado(n, info[n]['firma_audio'])
                    poner_estado(n, "listo")
                    ia_s = time.perf_counter() - t0
                    try:
                        escribir_atomico(DATOS/f'{n}.rendimiento.json', json.dumps({
                            'v': 1, 'lote_audios': len(lote), 'lote_hasta_listo_s': time.perf_counter()-lote_desde,
                            'cache_asr': info[n]['cache_asr'], 'carga_whisper_s': info[n]['carga_whisper_s'],
                            'desde_inicio_caso_s': time.perf_counter()-info[n]['inicio_caso'],
                            'desde_encolado_s': max(0,time.time()-ENCOLADO[n]) if n in ENCOLADO else None,
                            'whisper_s': info[n]['whisper'], 'ia_s': ia_s, 'ollama': metricas_ia}))
                    except OSError:
                        L.aviso('IA', 'No se pudieron conservar las métricas de rendimiento.', exc=True)
                    if not SIMULAR:
                        anotar_tiempo(info[n]["dur"], None if info[n]["cache_asr"] else info[n]["whisper"], ia_s)
                    r = resumen_avisos(n, {"lineas": lineas, "omisiones": om})
                    nuevos = N.estudios_sin_plantilla(salida)
                    L.contar("generados")
                    med = medico_de(n)
                    vz = resumen_voz(n) or {}
                    det = []
                    if r["faltan"]:
                        det.append("Dictado pero no está en el informe: " + ", ".join(r["faltan"]))
                    if tokens:
                        L.debug("IA", f"{visible(n)}: {tokens}")
                    L.ok("IA", f"{visible(n)} informe listo en {L.seg(ia_s)}"
                               + (f" · {med}" + (" (por la voz)" if vz.get("por") == "voz" else "") if med
                                  else " · sin médico (plantilla general)" if vz else " · sin médico elegido")
                               + f" · {texto_marcas(r)}", det)
                    for e in nuevos:
                        L.aviso("IA", f"{visible(n)}: estudio sin plantilla «{e}». Conviene crearla desde Plantillas.")
                    L.actividad("generado", **datos_csv(n), duracion_audio_s=info.get(n, {}).get("dur"),
                                whisper_s=None if info[n]["cache_asr"] else info[n]["whisper"], ia_s=ia_s,
                                palabras_dictado=info.get(n, {}).get("palabras"),
                                marcas_rojas=r["rojo"], marcas_amarillas=r["amarillo"], marcas_turquesa=r["turq"],
                                marcas_grises=r["gris"], datos_faltantes=" ".join(r["faltan"]),
                                partes_no_transcritas=" ".join(r["huecos"]), estudios_sin_plantilla=" | ".join(nuevos),
                                **campos_voz(vz))
                except CP.ErrorCola:
                    raise
                except Exception as ex:
                    poner_estado(n, 'error', mensaje_amigable(ex))
                    L.error('IA', 'Falló un informe; se continúa con los demás del lote.', exc=True)
                    L.actividad('error', **datos_csv(n), detalle='IA: ' + mensaje_amigable(ex))
        except CP.ErrorCola:
            fallo_persistencia = True
            L.error('COLA', 'No se pudo confirmar la cola. Se conservan las tareas y se reintentará.', exc=True)
            with LOCK:
                pendientes = [n for n in lote if n not in BORRADOS and ESTADO.get(n, {}).get('estado') not in ('listo', 'error')]
                for n in pendientes: ESTADO[n] = {'estado': 'en cola', 'msg': 'Esperando recuperar el almacenamiento', 't': time.time()}
            for n in pendientes: COLA.put(n)
        except Exception as ex:
            msg = mensaje_amigable(ex)
            afectados = [n for n in lote if ESTADO.get(n, {}).get("estado") not in ("listo", "error")
                         and n not in BORRADOS]
            L.error(etapa, f"No se pudo procesar {', '.join(visible(n) for n in afectados) or 'el lote'}: {msg}",
                    exc=True)
            for n in afectados:
                try:
                    poner_estado(n, "error", msg)
                except CP.ErrorCola:
                    fallo_persistencia = True
                    COLA.put(n)
                L.actividad("error", **datos_csv(n), detalle=f"{etapa}: {msg}")
        finally:
            if whisper is not None:
                del whisper
                whisper = None
                gc.collect()
            TRABAJO.update(ocupado=False, esperando_ia=False)
        if fallo_persistencia: time.sleep(5)
        if not en_proceso() and COLA.empty():
            L.debug("SERVIDOR", "Cola vacía.")


def campos_voz(vz):
    """Columnas del reconocimiento de voz para actividad.csv."""
    if not vz:
        return {}
    return {"medico_voz": vz.get("medico") or "", "voz_estado": vz.get("estado") or "",
            "voz_puntaje": round(vz["puntaje"] * 100, 1) if vz.get("puntaje") is not None else None}


def esperar_ia(n, lote):
    """Si Ollama está cerrado (o sin el modelo), el audio ya transcrito espera en la cola en vez de
    terminar con error: se sigue solo cuando la IA vuelve. Revisa cada 5 s."""
    avisado = False
    while True:
        if n in BORRADOS:
            return  # el trabajador lo saltea; no esperar a Ollama por un caso eliminado
        e = estado_ia()
        if e == "ok":
            TRABAJO["esperando_ia"] = False
            if avisado:
                L.ok("IA", f"La IA volvió: sigo con {visible(n)}.")
            return
        TRABAJO["esperando_ia"] = True       # se puede reiniciar el servidor sin esperar (se retoma al volver)
        E_IA["e"] = e
        _IA_CACHE.update(t=time.time(), ok=e != "caida")
        motivo = "Ollama no responde" if e == "caida" else f"falta el modelo {CFG['modelo_ia']}"
        for x in lote:
            if x in BORRADOS:
                continue
            if ESTADO.get(x, {}).get("estado") == "en cola" and not ESTADO[x].get("msg", "").startswith("Esperando a la IA ("):
                poner_estado(x, "en cola", f"Esperando a la IA ({motivo})…")
        if not avisado:
            L.aviso("IA", f"{visible(n)} ya está transcrito, pero {motivo}: queda esperando en la cola y se "
                          f"termina solo cuando la IA esté lista.")
            avisado = True
        time.sleep(5)


def avance(n, texto):
    """Función que Whisper llama después de cada tramo: muestra por dónde va y hace de punto de pausa."""
    def f(pos=None, total=None):
        if pos is not None and total and n not in PAUSAS:
            with LOCK:
                e = ESTADO.get(n)
                if e and e.get("estado") == "transcribiendo":
                    e.update(msg=f"{texto} · {mmss(min(pos, total))} de {mmss(total)}", pos=pos, total=total)
        punto_de_pausa(n, pos, total)
    return f


def punto_de_pausa(n, pos=None, total=None):
    """Si se pidió pausar este caso, el trabajador se queda acá (Whisper conserva lo transcrito) hasta que se
    reanude. Si mientras tanto se borra el caso, corta con Cancelado."""
    with PAUSA_CV:
        p = PAUSAS.get(n)
        if p:
            p["desde"] = time.time()
    if not p:
        return
    t0 = time.time()
    with LOCK:
        prev = dict(ESTADO.get(n, {}))
        pos = pos if pos is not None else prev.get("pos")
        total = total or prev.get("total")
        donde = f"iba por {mmss(min(pos, total))} de {mmss(total)}" if pos is not None and total else ""
        ESTADO[n] = {"estado": "en pausa", "msg": "En pausa" + (f" · {donde}" if donde else ""), "t": t0,
                     "pos": pos, "total": total, "por": p.get("por")}
    TRABAJO["en_pausa"] = n
    L.estado(cola=en_proceso(), pausa=1)
    espera = sum(1 for x in cola_pendiente() if x != n)
    L.info("WHISPER", f"{visible(n)} en pausa" + (f" ({donde})" if donde else "") + ". Whisper queda detenido con lo "
                      f"transcrito hasta ahora" + (f"; {L.plural(espera, 'audio')} de la cola espera" + ("" if espera == 1 else "n")
                                                   if espera else "") + " hasta que se reanude.")
    with PAUSA_CV:
        while n in PAUSAS and n not in BORRADOS:
            PAUSA_CV.wait(1.0)
    seg_ = time.time() - t0
    PAUSADO_S[n] = PAUSADO_S.get(n, 0) + seg_
    TRABAJO["en_pausa"] = None
    L.estado(pausa=0)
    if n in BORRADOS:
        raise Cancelado()
    msg = prev.get("msg") or ""
    with LOCK:
        ESTADO[n] = {"estado": "transcribiendo", "msg": "Transcribiendo el audio…" if msg.startswith("Pausando") else msg,
                     "t": prev.get("t", t0) + seg_, "pos": pos, "total": total}
    L.estado(cola=en_proceso())
    L.ok("WHISPER", f"{visible(n)} reanudado desde {p.get('reanudo') or 'la PC del servidor'} después de "
                    f"{L.seg(seg_)} en pausa: sigue desde donde quedó.")


def pausar(n, desde):
    """Pide la pausa de la transcripción en curso. Devuelve (respuesta, código)."""
    with LOCK:
        e = ESTADO.get(n, {}).get("estado")
    if e == "en pausa" or n in PAUSAS:
        return {"error": "Ya está en pausa."}, 409
    if e == "generando":
        return {"error": "Ya se transcribió y la IA está armando el informe: termina en unos segundos y esa parte "
                         "no se puede pausar."}, 409
    if e == "en cola":
        return {"error": "Todavía no se está transcribiendo: la pausa es para la transcripción en curso."}, 409
    if e != "transcribiendo":
        return {"error": "Ese audio no se está transcribiendo."}, 409
    with PAUSA_CV:
        if COLA_DURADERA is not None and not COLA_DURADERA.pausa(n, True):
            return {'error': 'El caso ya cambió de estado.'}, 409
        PAUSAS[n] = {"pedida": time.time(), "por": desde}
    with LOCK:
        if ESTADO.get(n, {}).get("estado") == "transcribiendo":
            ESTADO[n]["msg"] = "Pausando… (termina el tramo que está transcribiendo)"
    L.info("WHISPER", f"Pausa de {visible(n)} pedida desde {desde}: se detiene al terminar el tramo que está "
                      f"transcribiendo.")
    return {"ok": True, "msg": "Pausando: se detiene en unos segundos, al terminar el tramo que está transcribiendo. "
                               "Lo ya transcrito se conserva."}, 200


def reanudar(n, desde):
    with PAUSA_CV:
        if n in PAUSAS and COLA_DURADERA is not None:
            COLA_DURADERA.pausa(n, False)
        p = PAUSAS.pop(n, None)
        if p:
            p["reanudo"] = desde      # el trabajador lo dice en el registro al seguir
        PAUSA_CV.notify_all()
    if not p:
        return {"error": "Ese audio no está en pausa."}, 409
    if not p.get("desde"):        # todavía no se había detenido: se cancela el pedido
        with LOCK:
            e = ESTADO.get(n)
            if e and e.get("estado") == "transcribiendo" and (e.get("msg") or "").startswith("Pausando"):
                e["msg"] = "Transcribiendo el audio…"
        L.info("WHISPER", f"Pausa de {visible(n)} cancelada desde {desde} antes de que se detuviera.")
        return {"ok": True, "msg": "Pausa cancelada: sigue transcribiendo."}, 200
    return {"ok": True, "msg": "Reanudado: sigue transcribiendo desde donde quedó."}, 200


def origen_local(h):
    """Para los botones solo locales (pausa): que el pedido no venga de una página de otro sitio."""
    o = (h.headers.get("Origin") or "").lower()
    if o and o not in (f"http://127.0.0.1:{PUERTO}", f"http://localhost:{PUERTO}"):
        return False
    return h.headers.get("Sec-Fetch-Site") in (None, "same-origin", "none")


ENCOLAR_LOCK = threading.Lock()


def encolar(nombre, forzar=False):
    with ENCOLAR_LOCK:
        with LOCK:
            if not forzar and ESTADO.get(nombre, {}).get('estado') in EN_PROCESO:
                return False
            if COLA_DURADERA is not None:
                COLA_DURADERA.solicitar(nombre)
            BORRADOS.discard(nombre)
        fila = COLA_DURADERA.obtener(nombre) if COLA_DURADERA is not None else None
        ENCOLADO[nombre] = fila['encolado'] if fila else time.time()
        DURACION.pop(nombre, None)
        poner_estado(nombre, "en cola", "En cola…")
        if fila and fila['pausado']:
            with PAUSA_CV: PAUSAS[nombre] = {'pedida': time.time(), 'desde': time.time(), 'por': 'recuperación'}
        COLA.put(nombre)
        return True


# ------------------------------------------------- cola en vivo y casos abiertos (panel de administración)
def cola_en_vivo():
    """Lo que se está procesando y lo que espera, en orden, con cuánto lleva y cuánto falta (aproximado)."""
    ahora = time.time()
    esp = esperas()
    with LOCK:
        enp = {n: dict(v) for n, v in ESTADO.items() if v.get("estado") in EN_PROCESO}
        errores = sum(1 for v in ESTADO.values() if v.get("estado") == "error")
    items = []
    for n in sorted(enp, key=lambda x: (esp.get(x) or {}).get("adelante", 0)):
        e, s_ = enp[n], esp.get(n) or {}
        msg = e.get("msg") or ""
        items.append({"nombre": n, "titulo": titulo_de(n), "paciente": PAC.de(DATOS, n), "pc": origen_de(n),
                      "medico": medico_de(n), "estado": e.get("estado"), "msg": msg,
                      "etapa_desde": s_.get("desde"), "adelante": s_.get("adelante"), "eta": s_.get("eta"),
                      "en_cola": round(ahora - ENCOLADO[n]) if n in ENCOLADO else None, "dur": duracion_de(n),
                      "espera_ia": e.get("estado") == "en cola" and msg.startswith("Esperando a la IA ("),
                      "puede_pausar": e.get("estado") == "transcribiendo" and n not in PAUSAS,
                      "pausa_pedida": n in PAUSAS and e.get("estado") != "en pausa"})
    return {"items": items, "eta_total": max((i["eta"] or 0 for i in items), default=0), "errores": errores,
            "pausada": bool(REINICIO.get("detener")), "en_pausa": bool(TRABAJO.get("en_pausa")),
            "tiempos": {"whisper_x": round(TIEMPOS["whisper_x"], 3), "ia": round(TIEMPOS["ia"], 1), "n": TIEMPOS["n"]}}


def casos_abiertos():
    """Casos que alguna PC tiene abiertos ahora (bloqueados para las demás)."""
    ahora, out = time.time(), []
    for n, b in sorted(list(R.BLOQUEOS.items()), key=lambda x: x[1].get("desde", x[1]["t"])):
        edad = ahora - b["t"]
        if edad >= R.BLOQUEO_SEG:
            continue
        out.append({"nombre": n, "titulo": titulo_de(n), "paciente": PAC.de(DATOS, n), "pc": b["pc"],
                    "desde": b.get("desde", b["t"]), "senal": round(edad), "libera_en": round(R.BLOQUEO_SEG - edad),
                    "rev": revision_de(n)})
    return out


# ------------------------------------------------- mensajes a las PC y reinicio desde el panel
SRV = {"http": None, "salida": 0}


def abrir_tunel():
    """Abre el túnel elegido (configurar_tunel). Con Microsoft Dev Tunnels, antes abre el puerto propio
    del túnel; si no se puede, no abre el túnel (devtunnel publicaría lo que haya en ese puerto)."""
    if R.URL_TUNEL.get("iniciado"):
        return
    if R.servicio_tunel() == "devtunnel" and not TUNEL["http"]:
        try:
            TUNEL["http"] = Servidor(("127.0.0.1", PUERTO_TUNEL), HTunel)
        except OSError as ex:
            TUNEL["error"] = f"El puerto {PUERTO_TUNEL} está ocupado por otro programa ({ex})."
            L.error("TÚNEL", f"No se pudo abrir el puerto {PUERTO_TUNEL} para el túnel de Microsoft: lo usa otro "
                             f"programa. Cerralo o cambiá PUERTO_TUNEL. Mientras tanto el sistema funciona solo en esta PC.")
            return
        threading.Thread(target=TUNEL["http"].serve_forever, daemon=True, name="puerto-tunel").start()
        L.debug("TÚNEL", f"Puerto propio del túnel abierto: 127.0.0.1:{PUERTO_TUNEL}")
    R.escribir_conexion_cliente()
    R.iniciar_tunel(PUERTO, PUERTO_TUNEL)
TRABAJO = {"ocupado": False, "esperando_ia": False, "desde": None, "en_pausa": None}
REINICIO = {}       # reinicio programado desde el panel: id, cuando, estado (programado|esperando|reiniciando)...
MENSAJE = {}        # cartel en la pantalla de todas las PC: id, texto, tipo, desde, hasta, por, reinicio
COLA_AL_REINICIAR = INFORMES / "revision" / "cola_al_reiniciar.json"
_MSJ_LOCK = threading.Lock()
_REI_LOCK = threading.Lock()
TEXTO_REINICIO = ("Guardá lo que estés haciendo. El informe abierto se guarda solo; en un minuto el sistema "
                  "vuelve y la pantalla se reconecta sola.")


def poner_mensaje(texto, minutos=0, tipo="info", por=None, reinicio=False):
    ahora = time.time()
    with _MSJ_LOCK:
        MENSAJE.clear()
        MENSAJE.update(id=f"{int(ahora * 1000):x}", texto=texto, tipo=tipo, desde=ahora,
                       hasta=ahora + minutos * 60 if minutos else None, por=por or LOCAL, reinicio=reinicio)


def quitar_mensaje(solo_reinicio=False):
    with _MSJ_LOCK:
        if not MENSAJE or (solo_reinicio and not MENSAJE.get("reinicio")):
            return False
        MENSAJE.clear()
        return True


def mensaje_actual():
    with _MSJ_LOCK:
        if MENSAJE.get("hasta") and time.time() > MENSAJE["hasta"]:
            MENSAJE.clear()
        return dict(MENSAJE) if MENSAJE else None


def mensaje_para_pcs():
    """Lo que ven las páginas de informes (va en /api/casos)."""
    m = mensaje_actual()
    if not m:
        return None
    out = {"id": m["id"], "texto": m["texto"], "tipo": m["tipo"], "ahora": time.time(), "reinicio": None}
    if m.get("reinicio"):
        with _REI_LOCK:
            if REINICIO:
                out["reinicio"] = {"cuando": REINICIO.get("cuando"), "estado": REINICIO.get("estado")}
                out["id"] = f"{m['id']}-{REINICIO.get('estado')}"     # cambia de etapa: se vuelve a mostrar
    return out


def cola_pendiente():
    with LOCK:
        nombres = [n for n, v in ESTADO.items() if v.get("estado") in EN_PROCESO and n not in BORRADOS]
    return sorted(nombres, key=lambda n: ENCOLADO.get(n, 0))


def estado_reinicio():
    with _REI_LOCK:
        if not REINICIO:
            return None
        r = {k: REINICIO.get(k) for k in ("cuando", "estado", "por", "avisar", "pedido")}
    r["procesando"] = [titulo_de(n) for n in _en("transcribiendo") + _en("generando")]
    r["en_cola"] = len(cola_pendiente())
    return r


def programar_reinicio(seg, avisar, texto, quien):
    """Programa el reinicio: avisa a las PC (si se pide), espera el tiempo elegido y además que no haya nada
    a medio procesar; antes prueba que el código nuevo arranque. Devuelve (respuesta, código)."""
    quien_txt = quien or LOCAL
    if REINICIO.get("estado") == "reiniciando":
        return {"error": "El servidor ya se está reiniciando."}, 409
    ok, motivo = M.soporta_reinicio(TUNEL["modo"])
    if not ok:
        return {"error": motivo}, 409
    try:
        seg = max(0, min(int(seg or 0), 3600))
    except (TypeError, ValueError):
        seg = 0
    texto = " ".join(str(texto or "").split())[:300] or TEXTO_REINICIO
    t0 = time.time()
    err = M.prueba_de_arranque()
    if err:
        L.aviso("SERVIDOR", f"Reinicio pedido desde el panel ({quien_txt}) cancelado: el código de la carpeta tiene "
                            f"un error y el servidor no volvería a abrir.", det=err.splitlines()[-6:])
        return {"error": "No se reinicia: el código que está en la carpeta tiene un error y el servidor no volvería "
                         "a abrir. Corregilo y probá de nuevo.", "detalle": err}, 409
    with _REI_LOCK:
        if REINICIO.get("estado") == "reiniciando":
            return {"error": "El servidor ya se está reiniciando."}, 409
        rid = f"{int(time.time() * 1000):x}"
        REINICIO.clear()
        REINICIO.update(id=rid, cuando=time.time() + seg, pedido=time.time(), por=quien_txt, estado="programado",
                        detener=False, forzar=False, avisar=bool(avisar))
    if avisar:
        poner_mensaje(texto, tipo="aviso", por=quien, reinicio=True)
    else:
        quitar_mensaje(solo_reinicio=True)
    threading.Thread(target=_hilo_reinicio, args=(rid,), daemon=True, name="reinicio").start()
    cambios = ", ".join(c["archivo"] for c in M.cambios_sin_tomar()) or "sin cambios en el código"
    L.info("SERVIDOR", f"Reinicio del servidor programado desde el panel ({quien_txt}) "
                       + (f"para dentro de {L.seg(seg)}" if seg else "para ahora")
                       + (", con aviso a las PC" if avisar else "") + f". Toma: {cambios}. "
                       f"(el código nuevo se probó en {L.seg(time.time() - t0)})")
    if seg:
        msg = f"Reinicio programado: en {mmss(seg)} (y cuando termine lo que se esté procesando)."
    else:
        msg = "Reiniciando en cuanto termine lo que se esté procesando…"
    return {"ok": True, "msg": msg + (" Se avisó a las PC." if avisar else "")}, 200


def cancelar_reinicio(quien):
    with _REI_LOCK:
        if not REINICIO:
            return {"error": "No hay ningún reinicio programado."}, 409
        if REINICIO.get("estado") == "reiniciando":
            return {"error": "Ya se está reiniciando: no se puede cancelar."}, 409
        REINICIO.clear()
    avisadas = quitar_mensaje(solo_reinicio=True)
    L.info("SERVIDOR", f"Reinicio del servidor cancelado desde el panel ({quien or LOCAL}).")
    return {"ok": True, "msg": "Reinicio cancelado." + (" Se quitó el aviso de las PC." if avisadas else "")}, 200


def reiniciar_ya(quien):
    """Durante la espera: reiniciar sin esperar a que termine lo que se está procesando (se retoma al volver)."""
    with _REI_LOCK:
        if not REINICIO:
            return {"error": "No hay ningún reinicio programado."}, 409
        if REINICIO.get("estado") == "reiniciando":
            return {"error": "Ya se está reiniciando."}, 409
        REINICIO.update(forzar=True, cuando=min(REINICIO["cuando"], time.time()))
    L.aviso("SERVIDOR", f"Reinicio sin esperar pedido desde el panel ({quien or LOCAL}): lo que se estaba procesando "
                        f"se vuelve a procesar al volver.")
    return {"ok": True, "msg": "Reiniciando ahora…"}, 200


def _hilo_reinicio(rid):
    avisado = False
    while True:
        time.sleep(0.5)
        with _REI_LOCK:
            if REINICIO.get("id") != rid:
                return                       # cancelado o vuelto a programar
            if time.time() < REINICIO["cuando"]:
                continue
            REINICIO["detener"] = True       # el trabajador no empieza nada nuevo
            ocupado = TRABAJO["ocupado"] and not TRABAJO["esperando_ia"] and not TRABAJO.get("en_pausa")
            if ocupado and not REINICIO.get("forzar"):
                REINICIO["estado"] = "esperando"
                if not avisado:
                    avisado = True
                    proc = ", ".join(f"«{titulo_de(n)}»" for n in _en("transcribiendo") + _en("generando"))
                    L.info("SERVIDOR", "Reinicio: espero a que termine lo que se está procesando"
                                       + (f" ({proc})" if proc else "") + ".")
                continue
            REINICIO["estado"] = "reiniciando"
        _reiniciar_ahora()
        return


def _reiniciar_ahora():
    por = REINICIO.get("por") or LOCAL
    FIN_LOCK.acquire(timeout=60)             # que no quede un «Guardar Word» a medias (no se suelta: se cierra)
    pend = cola_pendiente()
    pausados = [n for n in pend if ESTADO.get(n, {}).get("estado") == "en pausa"]
    pend = [n for n in pend if n not in pausados]
    for n in pausados:
        L.aviso("SERVIDOR", f"{visible(n)} estaba en pausa: " + ('se conserva la pausa; usá Reanudar al volver.' if COLA_DURADERA is not None
                else 'queda sin procesar (botón Procesar en la lista cuando quieras).'))
    if COLA_DURADERA is None:
        try:
            escribir_atomico(COLA_AL_REINICIAR, json.dumps({"t": time.time(), "nombres": pend}, ensure_ascii=False))
        except OSError:
            L.error("SERVIDOR", "No se pudo anotar la cola antes de reiniciar.", exc=True)
    L.aviso("SERVIDOR", f"Reiniciando el servidor (pedido desde el panel, {por}) para tomar los cambios"
                        + (f"; {L.plural(len(pend), 'audio')} de la cola se retoman al volver." if pend else ".")
                        + " Las PC del trabajo se reconectan solas.")
    time.sleep(1.5)                          # que las páginas alcancen a ver «reiniciando»
    SRV["salida"] = M.CODIGO_REINICIO

    def _vigia():                            # si el cierre se traba, salir igual para que el .bat lo vuelva a abrir
        time.sleep(30)
        L.aviso("SERVIDOR", "El cierre para reiniciar se demoró más de 30 s: salgo igual para volver a abrir.")
        _salir_para_reiniciar()
    threading.Thread(target=_vigia, daemon=True, name="vigia-reinicio").start()
    if SRV["http"]:
        SRV["http"].shutdown()


def _salir_para_reiniciar():
    """Termina el proceso con el código de reinicio sin pasar por el cierre normal de Python.
    Con Whisper (CUDA/ctranslate2) y ONNX cargados, ese cierre en Windows puede colgarse o terminar con
    otro código, y entonces el .bat no lo vuelve a abrir."""
    for f in (sys.stdout, sys.stderr, sys.__stdout__, sys.__stderr__):
        try:
            f.flush()
        except Exception:
            pass
    os._exit(M.CODIGO_REINICIO)


def reanudar_cola():
    """Inicialización exclusiva antes de arrancar trabajadores o atender HTTP."""
    global COLA_DURADERA
    if COLA_DURADERA is not None: raise CP.ErrorCola('La cola ya se inicializó en este proceso.')
    cola = CP.ColaProcesamiento(DATOS.parent / 'cola_procesamiento.sqlite3')
    try:
        cola.importar_legacy(COLA_AL_REINICIAR, ruta_audio)
        COLA_DURADERA = cola
        # Ventana publicación de audio -> alta de tarea, y migración de instalaciones anteriores.
        # Nunca adoptar un caso revisado o con borrador, ni reactivar un registro terminal.
        for a in sorted(NUEVOS.iterdir(), key=lambda p: (p.stat().st_mtime_ns, p.name)):
            n = a.stem
            if a.is_file() and a.suffix.lower() in EXT_AUDIO and cola.obtener(n) is None:
                if not revision_conservada(n) and not (DATOS / f'{n}.informe_ia.txt').exists():
                    cola.solicitar(n)
        for fila in cola.filas():
            n, e = fila['nombre'], fila['estado']
            if e in ('listo', 'cancelado'): continue
            if e == 'borrando':
                BORRADOS.add(n)
                ESTADO[n] = {'estado': 'error', 'msg': 'Borrado interrumpido: revisar recuperación antes de procesar.', 't': time.time()}
                continue
            if e == 'error':
                ESTADO[n] = {'estado': 'error', 'msg': 'El procesamiento falló. Reintentá cuando se haya resuelto el problema.', 't': time.time()}
                continue
            if resultado_confirmado(n):
                poner_estado(n, 'listo')
                continue
            if revision_conservada(n):
                poner_estado(n, 'error', 'Se conservó una revisión. Revisá el caso antes de volver a procesar.')
                continue
            if ruta_audio(n) is None:
                poner_estado(n, 'error', 'No encuentro el audio pendiente. Conservamos su registro para recuperación.')
                continue
            cola.cambiar(n, 'en cola')
            ENCOLADO[n] = fila['encolado']
            if fila['pausado']:
                PAUSAS[n] = {'pedida': time.time(), 'desde': time.time(), 'por': 'recuperación tras caída'}
            ESTADO[n] = {'estado': 'en pausa' if fila['pausado'] else 'en cola',
                         'msg': 'Pausa conservada tras caída' if fila['pausado'] else 'Recuperado tras caída', 't': time.time()}
            COLA.put(n)
        L.info('COLA', 'Cola persistente recuperada; las pausas se conservan.')
    except BaseException:
        COLA_DURADERA = None
        cola.cerrar()
        raise


def revision_conservada(n):
    return (any((DATOS / (n+s)).exists() for s in ('.final.txt', '.borrador.json', '.borrador.html', '.formato.json'))
            or (INFORMES / f'{n}.docx').exists())


def estado_mantenimiento():
    ok, motivo = M.soporta_reinicio(TUNEL["modo"])
    return {"cambios": M.cambios_sin_tomar(), "git": M.info_git(), "git_inicio": M.git_al_arrancar(),
            "reiniciable": ok, "motivo_no": motivo, "bat": M.bat_del_modo(TUNEL["modo"]).name,
            "reinicio": estado_reinicio(), "mensaje": mensaje_actual()}


# ---------------------------------------------------------------- borrar
# Archivos de un caso en la carpeta datos. Lista explícita: un caso «tmp9177» no debe llevarse
# los de otro llamado «tmp9177.tmp».
SUFIJOS_CASO = (".procesamiento.json", ".transcripcion_cache.json", ".rendimiento.json", ".json", ".dictado.txt", ".informe_ia.txt", ".marcas.json", ".borrador.html", ".borrador.json", ".final.txt",
                ".medico.txt", ".audio.txt", ".ejemplo.txt", ".onda.json", ".origen.txt", ".original.txt",
                ".paciente.json", ".formato.json", ".omisiones_ok.json", ".revision.json", ".voz.json",
                ".usuario.txt", ".estilo.txt")


def puede_borrar(n, pc, remoto):
    """None si se puede borrar; si no, el motivo. Las PC del trabajo solo borran lo que enviaron ellas."""
    if remoto and (origen_de(n) != pc or pc == LOCAL):
        return "Solo se pueden borrar los informes que llegaron desde esta PC."
    with LOCK:
        e = ESTADO.get(n, {}).get("estado")
    if e in ("transcribiendo", "generando"):
        return "Se está procesando ahora: esperá a que termine para borrarlo."
    otro = R.bloqueado_por(n, pc)
    if otro:
        return f"Lo está revisando {otro}."
    return None


def _archivos_audio(n):
    """Audios del caso que se pueden borrar: solo los que están en la carpeta de audios nuevos (un audio
    procesado desde el modo consola puede estar en cualquier carpeta de la usuaria: ese no se toca)."""
    base = NUEVOS.resolve()
    out = [NUEVOS / f"{n}{e}" for e in EXT_AUDIO if (NUEVOS / f"{n}{e}").exists()]
    a = ruta_audio(n)
    if a is not None and a.resolve().parent == base and a not in out:
        out.append(a)
    return out


def _apartar(p):
    """Renombra el archivo para borrarlo (falla si está abierto, p. ej. el Word). Reintenta un poco por si
    justo se estaba leyendo el audio."""
    tmp = p.with_name(p.name + ".borrando")
    for i in range(6):
        try:
            p.replace(tmp)
            return tmp
        except FileNotFoundError:
            return None
        except PermissionError:
            if i == 5:
                raise
            time.sleep(0.25)


def borrar_caso(n, quien=LOCAL, remoto=False):
    """Borra el caso: audio, archivos de revisión y Word. Lo aprendido (ejemplos, historial, correcciones)
    se conserva. Devuelve None si salió bien o el motivo por el que no se borró."""
    motivo = puede_borrar(n, quien, remoto)
    if motivo:
        return motivo
    hay = any(n == p.stem for p in NUEVOS.iterdir() if p.suffix.lower() in EXT_AUDIO) \
        or any((DATOS / f"{n}{s}").exists() for s in SUFIJOS_CASO) or (INFORMES / f'{n}.docx').exists()
    if not hay:
        if COLA_DURADERA is not None and COLA_DURADERA.obtener(n) is not None:
            restos = [INFORMES / f'{n}.docx.borrando'] + [NUEVOS / f'{n}{e}.borrando' for e in EXT_AUDIO]
            if any(p.exists() for p in restos):
                return 'Hay archivos apartados de un borrado interrumpido. Conserválos y revisá su recuperación.'
            with LOCK:
                if ESTADO.get(n, {}).get('estado') in ('transcribiendo', 'generando'):
                    return 'Se está procesando ahora: esperá a que termine para borrarlo.'
                COLA_DURADERA.preparar_borrado(n)
                BORRADOS.add(n)
            COLA_DURADERA.cancelar_borrado(n)
            with LOCK: ESTADO.pop(n, None)
            with PAUSA_CV:
                PAUSAS.pop(n, None); PAUSA_CV.notify_all()
            ENCOLADO.pop(n, None)
            return None
        return "Ese informe ya no existe."
    with LOCK:      # que el trabajador no lo empiece justo ahora
        if ESTADO.get(n, {}).get("estado") in ("transcribiendo", "generando"):
            return "Se está procesando ahora: esperá a que termine para borrarlo."
        previo_duradero = COLA_DURADERA.preparar_borrado(n) if COLA_DURADERA is not None else None
        BORRADOS.add(n)
        previo = dict(ESTADO.get(n, {}))
    nombre_vis, estado = visible(n), previo.get("estado")
    if estado in (None, "listo", "nuevo"):
        estado = "revisado" if (DATOS / f"{n}.final.txt").exists() else (
            "para revisar" if (DATOS / f"{n}.informe_ia.txt").exists() else "sin procesar")
    # primero se apartan el Word y el audio: si alguno está abierto no se borra nada
    apartados = []
    try:
        for p in [INFORMES / f"{n}.docx"] + _archivos_audio(n):
            if p.exists():
                t = _apartar(p)
                if t:
                    apartados.append((p, t))
    except PermissionError as ex:
        for p, t in apartados:
            try:
                t.replace(p)
            except OSError:
                pass
        if COLA_DURADERA is not None: COLA_DURADERA.revertir_borrado(n, previo_duradero)
        with LOCK:
            BORRADOS.discard(n)
        if previo.get("estado") in ("en cola", "en pausa"):  # pudo haber sido salteado durante el intento
            encolar(n, forzar=True)
        cual = "el Word" if str(getattr(ex, "filename", "")).lower().endswith(".docx") else "el audio"
        L.aviso("CASO", f"{quien} quiso borrar {nombre_vis}, pero {cual} está abierto en otro programa.")
        return (f"No se pudo borrar: {cual} está abierto en otro programa. "
                f"Cerralo y volvé a intentar.")
    for _, t in apartados:
        t.unlink(missing_ok=True)
    for s in SUFIJOS_CASO:
        (DATOS / f"{n}{s}").unlink(missing_ok=True)
    (INFORMES / "revision" / f"{n}.html").unlink(missing_ok=True)      # revisión del modo consola
    R.quitar_huellas(DATOS, n)
    R.BLOQUEOS.pop(n, None)
    if COLA_DURADERA is not None: COLA_DURADERA.cancelar_borrado(n)
    with LOCK:
        ESTADO.pop(n, None)
    with PAUSA_CV:          # si estaba en pausa, el trabajador se despierta, ve que se borró y sigue con otro
        PAUSAS.pop(n, None)
        PAUSA_CV.notify_all()
    for d in (ENCOLADO, DURACION, _ESTUDIOS):
        d.pop(n, None)
    L.estado(cola=en_proceso())
    L.info("CASO", f"{quien} borró {nombre_vis} ({estado}): audio, informe y Word. "
                   f"Lo que aprendió la IA se conserva.")
    return None


# ------------------------------------------------------------- finalizar
def finalizar(nombre, texto, quien=LOCAL, usuario=None):
    with FIN_LOCK:      # solo publicación Word + final + tarea duradera; aprendizaje fuera de este lock
        return _finalizar(nombre, texto, quien, usuario)


def texto_a_marcado(texto):
    """Texto del editor -> (texto final limpio, líneas como las recibe el Word)."""
    lineas = [l.rstrip() for l in texto.replace("\r", "").split("\n")]
    while lineas and not lineas[0].strip():
        lineas.pop(0)
    final = "\n".join(lineas).strip()
    return final, [{"segs": [(l, None, None)], "linea": None, "titulo": N.es_titulo(l)} for l in final.split("\n")]


FMT_LOCK = threading.Lock()


def formato_de(nombre):
    """Formato elegido a mano en la vista previa (negrita, cursiva, color, alineación), o None."""
    f = DATOS / f"{nombre}.formato.json"
    try:
        return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None
    except (OSError, ValueError):
        return None


def vista_previa(texto, nombre=None, usuario=None):
    """Párrafos exactamente como quedan en el Word (mismo código que escribir_docx) + la hoja.
    b / a0 = negrita y alineación normales; a / r = con el formato elegido a mano (si hay).
    usuario: con el formato del Word propio del transcriptor."""
    _, marcado = texto_a_marcado(texto)
    CFG = U.cfg_de(globals()["CFG"], usuario)
    pars = parrafos_docx(marcado, CFG)
    if nombre:
        aplicar_formato(pars, formato_de(nombre))
    pars = [None if p is None else {"t": texto_parrafo(p), "b": p["negrita"], "a0": p["alin_def"],
                                    "a": p["alin"], "r": p.get("runs")}
            for p in pars]
    return {"parrafos": pars, "pagina": pagina(CFG), "fuente": CFG["fuente"], "tamano": CFG["tamano_fuente"],
            "encabezado": int(CFG["lineas_vacias_para_encabezado"])}


def aplicar_aprendizaje(tarea):
    from aprender import registrar_ejemplo, anotar_procesado
    registrar_ejemplo(tarea["nombre"], tarea["dictado"], tarea["ia"], tarea["final"],
                      tarea["clave"], medico=tarea["medico"], recalcular=False, fecha=tarea["fecha"],
                      usuario=tarea.get("usuario"))
    docx = Path(tarea["docx"])
    if docx.exists() and docx.stat().st_mtime_ns == tarea["mtime_ns"]:
        anotar_procesado(docx, tarea["clave"])
    n = tarea["nombre"]
    fin = DATOS / f"{n}.final.txt"
    if fin.exists() and fin.read_text(encoding="utf-8") == tarea["final"] and medico_de(n) == (tarea["medico"] or ""):
        try:
            muestra_al_guardar(n)
        except Exception:
            L.aviso("VOZ", "No se pudo registrar la muestra de voz del informe guardado.", exc=True)
    EST.invalidar()


def analizar_aprendizaje():
    from aprender import analizar_correcciones
    analizar_correcciones()


APRENDIZAJE = ColaAprendizaje(DATOS / "_aprendizaje", aplicar_aprendizaje, analizar_aprendizaje)


def _finalizar(nombre, texto, quien=LOCAL, usuario=None):
    from aprender import pct_corregido
    final, marcado = texto_a_marcado(texto)
    ia = (DATOS / f"{nombre}.informe_ia.txt").read_text(encoding="utf-8")
    dic = (DATOS / f"{nombre}.dictado.txt").read_text(encoding="utf-8")
    pc = pct_corregido("\n".join(l.rstrip() for l in N.texto_limpio(ia).splitlines()), final)
    fin_f = DATOS / f"{nombre}.final.txt"
    ya_guardado = fin_f.exists()
    reg = DATOS / f"{nombre}.ejemplo.txt"
    clave = reg.read_text(encoding="utf-8").strip() if reg.exists() else time.strftime("%Y%m%d_%H%M%S_") + nombre
    documento = io.BytesIO()
    escribir_docx(marcado, documento, U.cfg_de(CFG, usuario), formato_de(nombre))
    docx = INFORMES / f"{nombre}.docx"
    escribir_atomico(docx, documento.getvalue())
    escribir_atomico(reg, clave)
    escribir_atomico(fin_f, final)
    APRENDIZAJE.agregar({"nombre": nombre, "dictado": dic, "ia": ia, "final": final,
                        "clave": clave, "medico": medico_de(nombre) or None, "docx": str(docx), "usuario": usuario,
                        "mtime_ns": docx.stat().st_mtime_ns, "fecha": time.strftime("%Y-%m-%d %H:%M")})
    L.contar("guardados")
    vz = resumen_voz(nombre)
    rev = revision_de(nombre)
    por = f"{U.nombre_de(usuario)} ({quien})" if usuario else quien
    L.ok("INFORME", f"{visible(nombre)} {'guardado de nuevo' if ya_guardado else 'guardado'} por {por} · "
                    f"{f'{pc * 100:.1f}'.replace('.', ',')}% corregido"
                    + (f" · revisión {mmss(rev)}" if rev else "") + f" · Word {docx.name} · aprendizaje pendiente")
    # el transcriptor que guarda (no necesariamente el del caso): por eso se pisa el «usuario» de datos_csv
    L.actividad("guardado", **{**datos_csv(nombre), "usuario": U.nombre_de(usuario) if usuario else ""},
                porcentaje_corregido=pc * 100, palabras_informe=len(final.split()), revision_s=rev,
                detalle=("guardado de nuevo" if ya_guardado else "guardado") + f" desde {quien}", **campos_voz(vz))
    EST.invalidar()
    return {"docx": str(docx), "pct": round(pc * 100, 1), "aprendizaje": "pendiente"}


# ------------------------------------------------------------------ HTTP
class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def log_error(self, fmt, *args):
        L.debug("SERVIDOR", "HTTP: " + (fmt % args))

    def _json(self, obj, code=200, cookie=None):
        b = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.send_header("Cache-Control", "no-store")
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()
        self.wfile.write(b)

    def end_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        super().end_headers()

    def _body(self, limite=100 * 1024 * 1024):
        if "chunked" in (self.headers.get("Transfer-Encoding") or "").lower():
            partes, total = [], 0
            while True:
                tam = int(self.rfile.readline().split(b";")[0].strip() or b"0", 16)
                if tam == 0:
                    self.rfile.readline()
                    break
                total += tam
                if total > limite:
                    raise ValueError("Archivo demasiado grande")
                partes.append(self.rfile.read(tam))
                self.rfile.readline()
            return b"".join(partes)
        n = int(self.headers.get("Content-Length") or 0)
        if n > limite:
            raise ValueError("Archivo demasiado grande")
        return self.rfile.read(n) if n else b""

    def _nombre_valido(self, n):
        return n and "/" not in n and "\\" not in n and ".." not in n

    # ---------------------------------------------------- acceso remoto
    def _es_remoto(self):
        """Lo que llega por el tunel trae encabezados de Cloudflare; lo local no."""
        return any(self.headers.get(h) for h in ("Cf-Ray", "Cf-Connecting-Ip", "X-Forwarded-For", "Cf-Warp-Tag-Id"))

    def _ip(self):
        return self.headers.get("Cf-Connecting-Ip") or self.client_address[0]

    def _cookie(self, nombre):
        for parte in (self.headers.get("Cookie") or "").split(";"):
            k, _, v = parte.strip().partition("=")
            if k == nombre:
                return v
        return None

    def _llave(self):
        a = self.headers.get("Authorization") or ""
        return a[7:].strip() if a.lower().startswith("bearer ") else None

    # /ingresar: usuario y contraseña cuando la PC ya está identificada. Es otra dirección que /entrar porque la app
    # del trabajo intercepta /entrar (sin código) para volver a entrar sola con la llave de la PC.
    LIBRES = {"/entrar", "/ingresar", "/api/cliente/vincular", "/favicon.ico", "/salir"}
    # lo que la aplicación del trabajo hace sola con la llave de la PC, aunque nadie haya entrado
    SOLO_LLAVE = {"/api/cliente/estado", "/api/cliente/actualizacion", "/api/cliente/archivo", "/api/cliente/aviso",
                  "/api/cliente/audio", "/api/cliente/sesion"}

    def _sin_usuario(self, ruta):
        """Rutas que no necesitan un transcriptor con sesión."""
        if ruta in self.LIBRES or (self.con_llave and ruta in self.SOLO_LLAVE):
            return True
        # el panel de administración tiene su propio permiso (admin.py): así se crean los primeros usuarios
        return ruta in PAGINAS_ADMIN or ruta.startswith("/api/admin/")

    def _autorizar(self, ruta):
        """Pone self.pc, self.remoto y self.usuario (transcriptor con sesión, o None).
        Devuelve False (y responde) si no tiene permiso."""
        self.remoto = self._es_remoto()
        self.usuario = None
        self.con_llave = False
        ses = R.sesion(self._cookie("ts"))
        if not self.remoto:
            self.pc = LOCAL
            # la app de pruebas conectada a http://127.0.0.1 también manda su llave: con ella puede hacer lo suyo
            # (estado, audios, actualización) aunque nadie haya entrado en la página
            self.con_llave = bool(R.pc_de_llave(self._llave()))
            if ses and ses.get("local"):
                self.usuario = ses.get("usuario")
        else:
            llave = R.pc_de_llave(self._llave())
            self.con_llave = bool(llave)
            ses_pc = ses["pc"] if ses and not ses.get("local") else None
            self.pc = llave or ses_pc
            if ses_pc and ses_pc == self.pc:
                self.usuario = ses.get("usuario")
            if self.pc:
                VISTO[self.pc] = time.time()
                R.anotar_visto(self.pc, A.VERSION_PC.get(self.pc))
        if self.usuario and not U.existe(self.usuario):        # lo desactivaron mientras tenía la sesión abierta
            R.cerrar_sesion(self._cookie("ts"))
            self.usuario = None
        if self.remoto and not self.pc and ruta not in self.LIBRES:
            return self._pedir_entrar(ruta, "Pedido sin sesión")
        if self.usuario or not U.hay_usuarios() or self._sin_usuario(ruta):
            return True
        return self._pedir_entrar(ruta, "Pedido sin transcriptor")

    def _pedir_entrar(self, ruta, motivo):
        if ruta not in ("/", "/index.html") and L.una_vez(("sin_sesion", self._ip()), 600):
            L.info("ACCESO", f"{motivo} desde {self.pc or 'la IP ' + self._ip()} ({ruta}): se le pide entrar.")
        if ruta.startswith("/api/") or ruta.startswith("/audio/"):
            self._json({"error": "Sesión vencida: volvé a entrar.", "entrar": True}, 401)
        else:
            self._redirigir("/ingresar" if self.pc and U.hay_usuarios() else "/entrar")
        return False

    @property
    def quien(self):
        """Para el registro: «Ana (info-01)», o solo la PC si no hay transcriptor."""
        return f"{U.nombre_de(self.usuario)} ({self.pc})" if getattr(self, "usuario", None) else self.pc

    def _redirigir(self, a, cookie=None):
        self.send_response(303)
        self.send_header("Location", a)
        self.send_header("Cache-Control", "no-store")
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _html(self, b, code=200):
        b = b.encode("utf-8") if isinstance(b, str) else b
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(b)

    def _pagina_entrar(self, error="", usuario=""):
        """Formulario para entrar. Con transcriptores creados pide usuario y contraseña (y el nombre de la PC si
        se entra desde un navegador común del trabajo); sin ninguno, como antes: PC y contraseña del sistema."""
        import html as _h
        err = f'<p class="err">{_h.escape(error)}</p>' if error else ""
        hay = U.hay_usuarios()
        pc_conocida = not self.remoto or bool(self.pc)
        if not hay:
            txt = "Para usar el sistema desde esta PC escribí su nombre y la contraseña."
        elif pc_conocida:
            txt = (f"Esta PC: <b>{_h.escape(self.pc)}</b>. " if self.remoto else "") + \
                  "Escribí tu usuario y tu contraseña: la IA arma los informes con tu estilo."
        else:
            txt = "Escribí el nombre de esta PC, tu usuario y tu contraseña."
        campos = ""
        if self.remoto and not pc_conocida:
            campos += ('<label>Nombre de esta PC<input name="pc" placeholder="info-01" required '
                       'autocomplete="organization"></label>')
        if hay:
            campos += (f'<label>Usuario<input name="usuario" value="{_h.escape(usuario)}" required autofocus '
                       f'autocomplete="username"></label>')
        campos += ('<label>Contraseña<input name="contrasena" type="password" required '
                   'autocomplete="current-password"></label>')
        accion = "/ingresar" if hay and pc_conocida else "/entrar"
        self._html(PAGINA_ENTRAR.replace("{{texto}}", txt).replace("{{error}}", err).replace("{{campos}}", campos)
                   .replace("{{accion}}", accion), 401 if error else 200)

    def _entrar(self, f):
        """POST /entrar: transcriptor (o, sin transcriptores, la contraseña del sistema desde el trabajo)."""
        ip = self._ip()
        pc = (self.pc or (f.get("pc", [""])[0]).strip()) if self.remoto else LOCAL
        nombre = (f.get("usuario", [""])[0]).strip()
        clave_fallo = ip if self.remoto else f"local:{nombre.casefold()}"
        if R.demasiados_fallos(clave_fallo):
            L.aviso("ACCESO", f"Intento de entrar como «{(nombre or pc)[:24]}» desde la IP {ip} rechazado: "
                              f"está bloqueada 10 minutos por contraseñas incorrectas.")
            return self._pagina_entrar("Demasiados intentos fallidos. Esperá 10 minutos.", nombre)
        if self.remoto and not R.PC_VALIDA.match(pc):
            return self._pagina_entrar("Escribí el nombre de esta PC (ej. info-01).", nombre)
        contrasena = f.get("contrasena", [""])[0]
        if not U.hay_usuarios():
            if not self.remoto:
                return self._redirigir("/")
            if not R.contrasena_ok(contrasena):
                R.anotar_fallo(ip)
                self._avisar_fallo(pc, ip, "desde el navegador")
                return self._pagina_entrar("Contraseña incorrecta.")
            L.ok("ACCESO", f"{pc} entró desde el navegador (IP {ip}).")
            return self._redirigir("/", R.cookie_sesion(R.nueva_sesion(pc, reemplaza=self._cookie("ts"))))
        usuario = U.verificar(nombre, contrasena)
        if not usuario:
            R.anotar_fallo(clave_fallo)
            k = len(R.FALLOS.get(clave_fallo, []))
            L.aviso("ACCESO", f"Usuario o contraseña incorrectos para «{nombre[:24]}» en {pc} (IP {ip})."
                              + (" Queda bloqueado 10 minutos." if k >= 5 else f" Intento {k} de 5."))
            return self._pagina_entrar("Usuario o contraseña incorrectos.", nombre)
        R.FALLOS.pop(clave_fallo, None)
        U.anotar_entrada(usuario)
        sid = R.nueva_sesion(pc, usuario=usuario, local=not self.remoto, reemplaza=self._cookie("ts"))
        L.ok("ACCESO", f"{U.nombre_de(usuario)} entró en {pc}" + (f" (IP {ip})." if self.remoto else "."))
        return self._redirigir("/", R.cookie_sesion(sid, local=not self.remoto))

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(u.query)
        if not self._autorizar(u.path):
            return
        if u.path == "/entrar":
            cod = q.get("codigo", [""])[0]
            sid = R.canjear_codigo(cod, pc_local=None if self.remoto else LOCAL)
            if sid:
                v = R.sesion(sid) or {}
                if v.get("usuario"):
                    U.anotar_entrada(v["usuario"])
                L.info("ACCESO", f"{v.get('pc')} abrió la aplicación"
                                 + (f" con {U.nombre_de(v['usuario'])}" if v.get("usuario") else "") + f" (IP {self._ip()}).")
                return self._redirigir("/", R.cookie_sesion(sid, local=not self.remoto))
            if cod:
                L.aviso("ACCESO", f"Código de entrada vencido o inválido desde la IP {self._ip()}.")
            if self.usuario or (not self.remoto and not U.hay_usuarios()):
                return self._redirigir("/")
            return self._pagina_entrar()
        if u.path == "/ingresar":
            if self.usuario or not U.hay_usuarios():
                return self._redirigir("/")
            if self.remoto and not self.pc:
                return self._redirigir("/entrar")
            return self._pagina_entrar()
        if u.path == "/salir":
            v = R.cerrar_sesion(self._cookie("ts"))
            if v:
                L.info("ACCESO", (f"{U.nombre_de(v['usuario'])} salió en {v['pc']}." if v.get("usuario")
                                  else f"{v['pc']} cerró la sesión."))
            if v and v.get("usuario") and not v.get("local"):
                # en el trabajo la PC sigue identificada: el que sigue solo escribe su usuario y contraseña
                return self._redirigir("/ingresar", R.cookie_sesion(R.nueva_sesion(v["pc"])))
            return self._redirigir("/ingresar" if not self.remoto and U.hay_usuarios() else "/entrar",
                                   R.COOKIE_SESION_BORRAR)
        if u.path in ("/", "/index.html"):
            self._html((WEB / "index.html").read_bytes())
        elif u.path == "/editor_word.js":
            self._enviar_archivo(WEB / "editor_word.js")
        elif u.path in PAGINAS_ADMIN or u.path.startswith("/api/admin/"):
            acc = ADM.acceso(self, PUERTO)
            if acc is None:
                return self._panel_sin_permiso(u.path)
            visor = {"remoto": acc == "remoto", "pc": self.pc if acc == "remoto" else None}
            if u.path in PAGINAS_ADMIN:
                self._html((WEB / PAGINAS_ADMIN[u.path]).read_bytes())
            elif u.path == "/api/admin/estado":
                self._json(dict(estado_admin(), visor=visor))
            elif u.path == "/api/admin/medicos":
                self._json({"medicos": [{"nombre": m, "notas": N.notas_medico(m)}
                                          for m in N.lista_medicos()], "visor": visor})
            elif u.path == "/api/admin/estadisticas":
                q = urllib.parse.parse_qs(u.query)
                try:
                    dias = int((q.get("dias") or ["30"])[0])
                except ValueError:
                    dias = 30
                self._json(dict(EST.calcular(dias, medico_actual=medico_de, estudios_actual=estudios_de), visor=visor))
            elif u.path == "/api/admin/correcciones":
                try:
                    dias = int((q.get("dias") or ["0"])[0])
                except ValueError:
                    dias = 0
                self._json(dict(CORR.calcular(dias, (q.get("medico") or [""])[0], medico_actual=medico_de,
                                              puntuacion=(q.get("puntuacion") or [""])[0] == "1"), visor=visor))
            else:
                self.send_error(404)
        elif u.path == "/api/mi_pc":
            du = U.datos(self.usuario) if self.usuario else None
            self._json({"pc": self.pc, "remoto": self.remoto, "medico": R.medico_pc(self.pc),
                        "admin": (not self.remoto) or R.admin_configurado(),   # si se muestra el engranaje del panel
                        "con_usuarios": U.hay_usuarios(),
                        "usuario": {"clave": du["clave"], "nombre": du["nombre"], "cambiar": du["cambiar"]} if du else None,
                        # None = nunca guardó preferencias: la página sube las de esta PC
                        "preferencias": U.preferencias(self.usuario)
                        if du and U.archivo(self.usuario, "preferencias.json").exists() else None})
        elif u.path == "/api/usuario/estilo":
            if not self.usuario:
                return self._json({"error": "Entrá con tu usuario."}, 403)
            self._json({"formato": U.formato(self.usuario), "general": {k: CFG.get(k) for k in U.FORMATO},
                        "fuentes": list(U.FUENTES), "reglas": U.leer_archivo(self.usuario, "reglas_dictado.md"),
                        "plantillas_propias": [n for n, _ in N.secciones_de_usuario(self.usuario)],
                        "medicos_propios": N.medicos_con_notas_propias(self.usuario)})
        elif u.path == "/api/cliente/estado":
            instantanea = listar_casos(self.pc)
            casos = [{"nombre": c["nombre"], "titulo": c["titulo"], "estado": c["estado"], "marcas": c["marcas"],
                      "paciente": c["paciente"]}
                     for c in instantanea if c["origen"] == self.pc][:40]
            cola = sum(1 for c in instantanea if c["estado"] in ("en cola", "transcribiendo", "generando"))
            A.anotar_version(self.pc, self.headers.get("User-Agent"))
            self._json({"ok": True, "pc": self.pc, "ia": ia_lista(), "cola": cola, "casos": casos,
                        "version": VERSION, "app": A.resumen()})
        elif u.path == "/api/cliente/actualizacion":
            # lista de archivos de la app con sus huellas: la app baja solo los que cambiaron
            self._json(A.manifiesto())
        elif u.path == "/api/cliente/archivo":
            rel = q.get("ruta", [""])[0]
            p = A.archivo(rel)
            if not p or not p.exists():
                self.send_error(404); return
            if rel.lower() == "transcripcion.exe" and L.una_vez(("app_baja", self.pc, A.resumen()["huella"]), 3600):
                L.info("APP", f"{self.pc} está bajando la versión {A.resumen()['version'] or 'nueva'} de la app.")
            self._enviar_archivo(p)
        elif u.path == "/api/word":
            n = q.get("nombre", [""])[0]
            p = INFORMES / f"{n}.docx"
            if not self._nombre_valido(n) or not p.exists():
                self.send_error(404); return
            pac = PAC.de(DATOS, n)
            nom = re.sub(r'[\\/:*?"<>|]+', "", f"{pac} - {titulo_de(n)}" if pac else titulo_de(n)).strip()
            self._enviar_archivo(p, descarga=f"{nom or n}.docx")
        elif u.path == "/api/casos":
            ok = ia_lista()
            self._json({"casos": listar_casos(self.pc, self.remoto), "ollama": ok, "pc": self.pc,
                        "ia_estado": "caida" if not ok else ("sin_modelo" if E_IA["e"] == "sin_modelo" else "ok"),
                        "modelo": CFG["modelo_ia"], "mensaje": mensaje_para_pcs(),
                        "pausa": bool(TRABAJO.get("en_pausa"))})
        elif u.path == "/api/formato":
            cfg = U.cfg_de(CFG, self.usuario)
            self._json({"palabras_titulo": sorted(N.PALABRAS_ESTUDIO),
                        "negrita_titulos": cfg.get("negrita_titulos", True),
                        "fuente": cfg.get("fuente"), "tamano": cfg.get("tamano_fuente"),
                        "prefijos": CFG.get("negrita_si_empieza_con", N.NEGRITA_DEF),
                        "exactas": CFG.get("negrita_lineas_exactas", N.NEGRITA_EXACTAS)})
        elif u.path == "/api/medicos":
            rv = VOZ.resumen()
            out = []
            for m in N.lista_medicos():
                propias = N.notas_propias(m, self.usuario)
                x = {"nombre": m, "notas": N.notas_medico(m, self.usuario), "voz": rv.get(m, {}).get("n", 0),
                     "propias": propias is not None}
                if propias is not None:
                    x["generales"] = N.notas_medico(m)
                out.append(x)
            self._json({"medicos": out})
        elif u.path == "/api/voces":
            rv = VOZ.resumen()
            self._json({"modelo": VOZ.estado_modelo(), "error": VOZ._DESCARGA.get("error") or "",
                        "parametros": VOZ.parametros(CFG), "medicos": rv,
                        "sin_etiquetar": len(casos_sin_etiquetar())})
        elif u.path == "/api/voces/muestras":
            med = q.get("medico", [""])[0]
            out = []
            for c, m in VOZ.muestras(med or None):
                f = {"caso": c, "medico": m.get("medico"), "fecha": m.get("fecha"), "fuente": m.get("fuente"),
                     "seg": m.get("seg"), "titulo": c, "paciente": "", "audio": False}
                try:
                    f.update(titulo=titulo_de(c), paciente=PAC.de(DATOS, c), audio=ruta_audio(c) is not None)
                except OSError:
                    pass
                out.append(f)
            self._json({"muestras": out})
        elif u.path == "/api/voces/agrupar":
            self._json(grupos_de_voces())
        elif u.path == "/api/plantillas":
            self._json({"secciones": N.secciones_con_origen(self.usuario), "con_usuario": bool(self.usuario)})
        elif u.path == "/api/caso":
            n = q.get("nombre", [""])[0]
            try:
                c = cargar_caso(n) if self._nombre_valido(n) else None
            except (BOR.Corrupto, OSError):
                L.error('CASO', 'No se pudo leer el borrador guardado.', exc=True)
                return self._json({'error': 'No se pudo leer el borrador guardado. Conservá sus archivos y solicitá recuperación.'}, 503)
            self._json(c if c else {"error": "no existe"}, 200 if c else 404)
        elif u.path == "/api/onda":
            n = q.get("nombre", [""])[0]
            try:
                d = forma_de_onda(n) if self._nombre_valido(n) else None
            except Exception:
                L.error("CASO", f"No pude dibujar la forma de onda de {visible(n)}.", exc=True)
                d = None
            self._json(d if d else {"error": "sin audio"}, 200 if d else 404)
        elif u.path.startswith("/audio/"):
            n = urllib.parse.unquote(u.path[7:])
            a = ruta_audio(n) if self._nombre_valido(n) else None
            if not a:
                self.send_error(404); return
            self._enviar_archivo(a)
        else:
            self.send_error(404)

    def _enviar_archivo(self, ruta, descarga=None):
        tam = ruta.stat().st_size
        tipo = mimetypes.guess_type(str(ruta))[0] or "application/octet-stream"
        if ruta.suffix.lower() == ".docx":
            tipo = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        rng = self.headers.get("Range")
        ini, fin = 0, tam - 1
        if rng:
            m = re.match(r"bytes=(\d*)-(\d*)", rng)
            if m:
                if m.group(1):
                    ini = int(m.group(1))
                    if m.group(2):
                        fin = min(int(m.group(2)), tam - 1)
                elif m.group(2):
                    ini = max(0, tam - int(m.group(2)))
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {ini}-{fin}/{tam}")
        else:
            self.send_response(200)
        self.send_header("Content-Type", tipo)
        self.send_header("Cache-Control", "no-store")    # que Cloudflare no guarde audios ni Word
        if descarga:
            self.send_header("Content-Disposition",
                             "attachment; filename*=UTF-8''" + urllib.parse.quote(descarga))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(fin - ini + 1))
        self.end_headers()
        try:
            with open(ruta, "rb") as f:
                f.seek(ini)
                falta = fin - ini + 1
                while falta > 0:
                    b = f.read(min(65536, falta))
                    if not b:
                        break
                    self.wfile.write(b)
                    falta -= len(b)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass

    def _guardar_audio_nuevo(self, original, cuerpo, huella=None):
        """Guarda un audio llegado de otra PC con nombre único y lo pone en cola."""
        with RECIBIR_AUDIO_LOCK:
            return self._recibir_audio_serializado(original, cuerpo, huella)

    def _recibir_audio_serializado(self, original, cuerpo, huella=None):
        if len(cuerpo) < 44 or cuerpo[:4] != b"RIFF" or cuerpo[8:12] != b"WAVE":
            if Path(original).suffix.lower() == ".wav":
                L.aviso("AUDIO", f"{self.pc} envió «{original}» ({L.tamano(len(cuerpo))}) pero no es un WAV "
                                 f"válido (¿llegó incompleto?). No se procesa.")
                return None, "El archivo no es un WAV válido (¿llegó incompleto?)"
        h = hashlib.sha256(cuerpo).hexdigest()
        if huella and huella.lower() != h:
            L.aviso("AUDIO", f"«{original}» de {self.pc} llegó dañado en el viaje; la aplicación lo vuelve a enviar.")
            return None, "El audio llegó dañado: se vuelve a enviar."
        previo = R.buscar_huella(DATOS, h)
        if previo and ruta_audio(previo):
            if previo not in ESTADO:
                encolar(previo)  # reintento tras una caída entre recepción duradera y encolado
            L.info("AUDIO", f"{self.pc} envió «{original}», que ya estaba cargado como {visible(previo)}. "
                            f"No se procesa de nuevo.")
            return {"ok": True, "nombre": previo, "duplicado": True}, None
        ext = Path(original).suffix.lower()
        nombre = R.nombre_unico(self.pc, original,
                                lambda n: any((NUEVOS / f"{n}{e}").exists() for e in EXT_AUDIO))
        escribir_atomico(DATOS / f"{nombre}.origen.txt", self.pc)
        escribir_atomico(DATOS / f"{nombre}.original.txt", Path(original).name)
        # «Cargar audio» desde la página: el que lo sube; la app sola: el que está usando la página en esa PC
        poner_usuario_caso(nombre, getattr(self, "usuario", None)
                           or (R.usuario_activo(self.pc) if U.hay_usuarios() else None))
        med = R.medico_pc(self.pc)
        if med:
            escribir_atomico(DATOS / f"{nombre}.medico.txt", med)
        # Publicar al final: el vigilante no debe leer un WAV parcial o sin metadatos.
        escribir_atomico(NUEVOS / f"{nombre}{ext}", cuerpo)
        R.guardar_huella(DATOS, h, nombre)
        encolar(nombre)
        anunciar_audio(nombre, cuerpo, f"de {self.pc}")
        return {"ok": True, "nombre": nombre, "duplicado": False}, None

    def do_POST(self):
        u = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(u.query)
        if not self._autorizar(u.path):
            return
        try:
            if u.path in ("/entrar", "/ingresar"):   # usuario y contraseña (o, sin transcriptores, la del sistema)
                return self._entrar(urllib.parse.parse_qs(self._body(64 * 1024).decode("utf-8", "replace")))
            if u.path == "/api/cliente/vincular":
                d = json.loads(self._body(64 * 1024) or b"{}")
                pc_nueva = str(d.get("pc", "")).strip()
                usu = str(d.get("usuario") or "").strip()
                llave, err = R.vincular(pc_nueva, str(d.get("contrasena", "")), self._ip(), usuario=usu or None)
                if err:
                    if err.startswith(("Contraseña", "Usuario")):
                        self._avisar_fallo(pc_nueva, self._ip(), "al vincular la aplicación"
                                           + (f" (usuario «{usu[:24]}»)" if usu else ""))
                    else:
                        L.aviso("ACCESO", f"No se vinculó «{pc_nueva[:24]}» (IP {self._ip()}): {err}")
                    return self._json({"error": err}, 403)
                L.ok("ACCESO", f"PC vinculada: {pc_nueva} (IP {self._ip()})"
                               + (f" con el usuario «{usu[:40]}»" if usu else "")
                               + ". Ya puede enviar audios.")
                r = {"ok": True, "llave": llave, "pc": d["pc"].strip(), "version": VERSION}
                usu_ok = U.verificar(usu, str(d.get("contrasena", ""))) if usu and U.hay_usuarios() else None
                if usu_ok:     # la página abre ya con este transcriptor: no se le pide el usuario dos veces
                    r["codigo"] = R.nuevo_codigo(pc_nueva, usuario=usu_ok, seg=180)
                return self._json(r)
            if u.path == "/api/cliente/sesion":
                if not self._llave() or not R.pc_de_llave(self._llave()):
                    if L.una_vez(("llave", self._ip()), 600):
                        L.aviso("ACCESO", f"Una aplicación con una llave no autorizada (¿PC anulada?) intentó "
                                          f"entrar desde la IP {self._ip()}.")
                    return self._json({"error": "Esta PC no está autorizada"}, 401)
                return self._json({"ok": True, "codigo": R.nuevo_codigo(self.pc)})
            if u.path == "/api/cliente/aviso":
                # la app avisa algo que conviene ver en el servidor (ej. una actualización que no abrió)
                d = json.loads(self._body(16 * 1024) or b"{}")
                texto = " ".join(str(d.get("texto", "")).split())[:400]
                if texto:
                    (L.ok if d.get("tipo") == "ok" else L.aviso)("APP", f"{self.pc}: {texto}")
                return self._json({"ok": True})
            if u.path == "/api/cliente/audio":
                original = urllib.parse.unquote(self.headers.get("X-Archivo") or "audio.wav")
                if Path(original).suffix.lower() not in EXT_AUDIO:
                    L.aviso("AUDIO", f"{self.pc} envió «{original}»: formato de audio no soportado.")
                    return self._json({"error": "Formato de audio no soportado"}, 400)
                r, err = self._guardar_audio_nuevo(original, self._body(), self.headers.get("X-Huella"))
                return self._json(r) if r else self._json({"error": err}, 422)
            if u.path == "/api/plantilla_word":
                arch = q.get("archivo", [""])[0].lower()
                if not arch.endswith(".docx"):
                    return self._json({"error": "Guardalo como .docx (en Word: Archivo → Guardar como → "
                                                "Documento de Word) y volvé a intentar."}, 400)
                from importar_informes import plantilla_desde_word
                L.info("CONFIG", f"{self.pc} armó una plantilla desde el Word «{Path(arch).name}».")
                return self._json(plantilla_desde_word(self._body()))
            if u.path == "/api/subir":
                nombre_arch = Path(q.get("archivo", [""])[0]).name
                if Path(nombre_arch).suffix.lower() not in EXT_AUDIO:
                    return self._json({"error": "Formato de audio no soportado"}, 400)
                if self.remoto:     # desde otra PC: nombre único y se anota de qué PC vino
                    r, err = self._guardar_audio_nuevo(nombre_arch, self._body())
                    return self._json(r) if r else self._json({"error": err}, 422)
                destino = NUEVOS / nombre_arch
                cuerpo = self._body()
                escribir_atomico(DATOS / f"{destino.stem}.origen.txt", LOCAL)
                poner_usuario_caso(destino.stem, self.usuario)
                med = q.get("medico", [""])[0].strip()
                if med:
                    escribir_atomico(DATOS / f"{destino.stem}.medico.txt", med)
                escribir_atomico(destino, cuerpo)
                encolar(destino.stem)
                anunciar_audio(destino.stem, cuerpo, "en esta PC")
                return self._json({"ok": True, "nombre": destino.stem})
            datos = json.loads(self._body(20 * 1024 * 1024) or b"{}")
            if u.path == "/api/vista_previa":
                nv = datos.get("nombre") or None
                return self._json(vista_previa(str(datos.get("texto", "")),
                                               nv if nv and self._nombre_valido(nv) else None, self.usuario))
            if u.path == "/api/admin/entrar":
                return self._panel_entrar(datos)
            if u.path == "/api/admin/salir":
                if self.remoto and R.cerrar_sesion_admin(self._cookie("ta")):
                    L.info("ACCESO", f"{self.pc} salió del panel de administración.")
                return self._json({"ok": True}, cookie=R.COOKIE_ADMIN_BORRAR if self.remoto else None)
            if u.path.startswith("/api/admin/"):
                acc = ADM.acceso(self, PUERTO)
                if acc is None or not ADM.mismo_origen(self, PUERTO):
                    if acc is None and self.remoto and R.admin_configurado() and ADM.mismo_origen(self, PUERTO):
                        return self._json({"error": "La sesión del panel venció: volvé a escribir su contraseña.",
                                           "entrar_panel": True}, 401)
                    L.aviso("ACCESO", f"Pedido al panel de administración rechazado ({u.path}, {self.pc}, "
                                      f"IP {self._ip()}).")
                    return self._json({"error": "No tenés permiso para usar el panel de administración."}, 403)
                return self._json(*accion_admin(u.path[len("/api/admin/"):], datos,
                                                quien=self.pc if acc == "remoto" else None))
            if u.path.startswith("/api/usuario/"):
                if not self.usuario:
                    return self._json({"error": "Entrá con tu usuario."}, 403)
                return self._json(*accion_usuario(u.path[len("/api/usuario/"):], datos, self.usuario, self.pc))
            if u.path == "/api/mi_medico":
                med = datos.get("medico", "").strip()
                if med != R.medico_pc(self.pc):
                    L.info("CONFIG", f"{self.pc} eligió médico para sus audios: {med or 'ninguno'}.")
                R.poner_medico_pc(self.pc, med)
                return self._json({"ok": True})
            if u.path == "/api/medico":
                # destino: "todos" (notas generales, como siempre), "mio" (solo para este transcriptor) o
                # "general" (dejar de usar las propias). Sin destino = "todos" (compatibilidad).
                destino = datos.get("destino") or "todos"
                try:
                    if destino in ("mio", "general") and not datos.get("crear"):
                        if not self.usuario:
                            return self._json({"error": "Para guardar notas solo para vos tenés que entrar con tu usuario."}, 403)
                        nom = str(datos.get("medico", ""))
                        N.guardar_notas_propias(nom, self.usuario, datos.get("notas", "") if destino == "mio" else None)
                        L.ok("CONFIG", f"Notas propias de {self.quien} sobre {nom} "
                                       + ("guardadas." if destino == "mio" else "quitadas: vuelve a usar las generales."))
                        return self._json({"ok": True, "medico": nom, "destino": destino})
                    nom = N.guardar_medico(datos.get("medico", ""), datos.get("notas", ""),
                                           crear=datos.get("crear") is True)
                    if self.usuario and not datos.get("crear"):
                        N.guardar_notas_propias(nom, self.usuario, None)   # pasan a ser las de todos
                except FileExistsError as ex:
                    return self._json({"error": str(ex)}, 409)
                except FileNotFoundError as ex:
                    return self._json({"error": str(ex)}, 404)
                except ValueError as ex:
                    return self._json({"error": str(ex)}, 400)
                L.ok("CONFIG", f"Notas del médico {nom} guardadas para todos ({self.quien}).")
                return self._json({"ok": True, "medico": nom, "destino": "todos"})
            if u.path == "/api/voces/etiquetar":     # {"nombres": [...], "medico": "..."} desde «Agrupar voces»
                med = str(datos.get("medico") or "").strip()
                nombres = datos.get("nombres") or []
                if not med or not isinstance(nombres, list) or not nombres or len(nombres) > 500:
                    return self._json({"error": "Elegí el médico y al menos un audio."}, 400)
                ok, salteados = [], []
                for x in dict.fromkeys(str(v) for v in nombres):
                    v = voz_de(x) if self._nombre_valido(x) else None
                    otro = R.bloqueado_por(x, self.pc) if v else None
                    if not v or not v.get("h") or otro:
                        salteados.append({"nombre": x, "motivo": f"lo está revisando {otro}" if otro else "sin huella de voz"})
                        continue
                    (DATOS / f"{x}.medico.txt").write_text(med, encoding="utf-8")
                    anotar_voz(x, medico_por="usuaria")
                    VOZ.agregar(x, med, v["h"], "etiquetado", v.get("seg"))
                    ok.append(x)
                k = VOZ.resumen().get(med, {}).get("n", 0)
                L.ok("VOZ", f"{self.pc} etiquetó {L.plural(len(ok), 'audio')} como de «{med}» (ahora tiene "
                            f"{L.plural(k, 'muestra')} de voz)" + (f"; {len(salteados)} salteado(s)" if salteados else "") + ".")
                return self._json({"ok": True, "etiquetados": ok, "salteados": salteados, "muestras": k})
            if u.path == "/api/voces/quitar":       # {"caso": "..."}: sacar una muestra mal etiquetada
                c = str(datos.get("caso") or "")
                viejo = VOZ.quitar(c) if self._nombre_valido(c) else None
                if viejo:
                    if (DATOS / f"{c}.voz.json").exists() and medico_de(c) == viejo and not (DATOS / f"{c}.final.txt").exists():
                        anotar_voz(c, medico_por="")
                    L.info("VOZ", f"{self.pc} quitó la muestra de voz de {visible(c)} de «{viejo}».")
                return self._json({"ok": bool(viejo)})
            if u.path == "/api/importar":
                from importar_informes import importar
                ok, mal = importar()
                L.ok("CONFIG", f"Importados {L.plural(len(ok), 'informe')} Word como referencia ({self.pc}).",
                     [f"No se pudieron leer: {', '.join(mal)}"] if mal else None)
                return self._json({"ok": ok, "mal": mal})
            if u.path == "/api/plantillas":
                secs = [(x.get("nombre", ""), x.get("cuerpo", "")) for x in datos.get("secciones", [])
                        if isinstance(x, dict)]
                if not secs:
                    return self._json({"error": "No hay plantillas para guardar"}, 400)
                destino = datos.get("destino") or ("mio" if self.usuario else "todos")
                try:
                    r = N.aplicar_plantillas(secs, self.usuario, destino)
                except ValueError as ex:
                    return self._json({"error": str(ex)}, 400)
                if r["sin_cambios"]:
                    return self._json({"ok": True, **r})
                if destino == "todos":
                    L.ok("CONFIG", f"Plantillas guardadas para todos por {self.quien} ({L.plural(r['generales'], 'cambio')}); "
                                   f"la versión anterior quedó en conocimiento\\copias.")
                else:
                    L.ok("CONFIG", f"Plantillas propias de {self.quien} guardadas ({L.plural(r['propias'], 'cambio')}).")
                return self._json({"ok": True, **r})
            if u.path == "/api/plantillas/general":     # quitar la versión propia de una plantilla
                if not self.usuario:
                    return self._json({"error": "Entrá con tu usuario."}, 403)
                nom = str(datos.get("nombre") or "")
                ok = N.volver_a_general(self.usuario, nom)
                if ok:
                    L.info("CONFIG", f"{self.quien} volvió a la plantilla general de «{nom}».")
                return self._json({"ok": ok})
            if u.path == "/api/borrar":      # uno o varios casos: {"nombres": [...]}
                nombres = datos.get("nombres") or ([datos["nombre"]] if datos.get("nombre") else [])
                if not isinstance(nombres, list) or not nombres or len(nombres) > 500:
                    return self._json({"error": "No hay informes para borrar"}, 400)
                ok, mal = [], []
                for x in dict.fromkeys(str(v) for v in nombres):
                    if not self._nombre_valido(x):
                        mal.append({"nombre": x, "error": "nombre inválido"})
                        continue
                    err = borrar_caso(x, self.pc, self.remoto)
                    (mal.append({"nombre": x, "error": err}) if err else ok.append(x))
                if len(ok) > 1:
                    L.ok("CASO", f"{self.pc} borró {L.plural(len(ok), 'informe')}"
                                 + (f" ({len(mal)} no se {'pudo' if len(mal) == 1 else 'pudieron'} borrar)" if mal else "") + ".")
                if mal and not ok and len(mal) == 1:
                    code = 403 if mal[0]["error"].startswith("Solo se pueden") else 409
                    return self._json({"error": mal[0]["error"], "borrados": ok, "fallidos": mal}, code)
                return self._json({"ok": True, "borrados": ok, "fallidos": mal})
            n = datos.get("nombre", "")
            if not self._nombre_valido(n):
                return self._json({"error": "nombre inválido"}, 400)
            if u.path in ("/api/caso/pausar", "/api/caso/reanudar"):
                accion = "pausar" if u.path.endswith("/pausar") else "reanudar"
                if self.remoto:
                    if L.una_vez(("pausa_remota", self.pc), 600):
                        L.aviso("ACCESO", f"{self.pc} intentó {accion} la transcripción de {visible(n)}: solo se "
                                          f"puede desde la PC del servidor.")
                    return self._json({"error": "Pausar o reanudar una transcripción solo se puede en la PC del "
                                                "servidor."}, 403)
                if not origen_local(self):
                    return self._json({"error": "Pedido rechazado: no viene de esta página."}, 403)
                r, code = (pausar if accion == "pausar" else reanudar)(n, "la lista de informes")
                return self._json(r, code)
            if u.path == "/api/caso/bloquear":
                previo = R.BLOQUEOS.get(n)
                # la página que ya lo tenía abierto avisa cada 15 s que sigue ahí (manda el tiempo de revisión)
                r = R.bloquear(n, self.pc, renovar="rev" in datos or bool(datos.get("renovar")))
                if r is R.LIBERADO:
                    return self._json({"ok": False, "liberado": True, "por": "el panel de administración"})
                if r is True:
                    sumar_revision(n, datos.get("rev"), self.pc)
                    if not previo or previo["pc"] != self.pc or time.time() - previo["t"] > R.BLOQUEO_SEG:
                        L.info("CASO", f"{self.pc} abrió {visible(n)} para revisar.")
                elif L.una_vez(("ocupado", n, self.pc), 120):
                    L.info("CASO", f"{self.pc} quiso abrir {visible(n)}, pero lo está revisando {r}.")
                return self._json({"ok": True} if r is True else {"ok": False, "por": r})
            if u.path == "/api/caso/soltar":
                if R.bloqueado_por(n, self.pc) is None:
                    sumar_revision(n, datos.get("rev"), self.pc)
                R.soltar(n, self.pc)
                L.debug("CASO", f"{self.pc} cerró {visible(n)}.")
                return self._json({"ok": True})
            otro = R.bloqueado_por(n, self.pc) or (R.liberado_para(n, self.pc) and "el panel de administración")
            if otro and u.path in ("/api/borrador", "/api/finalizar", "/api/procesar", "/api/caso_medico", "/api/paciente",
                                       "/api/formato_caso", "/api/formato_caso/agregar"):
                if L.una_vez(("conflicto", n, self.pc), 120):
                    L.aviso("CASO", f"{self.pc} intentó modificar {visible(n)} " + (
                        "después de que se lo liberaron desde el panel" if otro == "el panel de administración"
                        else f"mientras lo revisa {otro}") + "; no se guardó su cambio.")
                if otro == "el panel de administración":
                    return self._json({"error": "Desde el panel de administración se liberó este caso: cerralo y "
                                                "volvé a abrirlo desde la lista para seguir.", "liberado": True}, 409)
                return self._json({"error": f"Este caso lo está revisando {otro}."}, 409)
            if u.path == "/api/caso_medico":
                med = datos.get("medico", "").strip()
                f = DATOS / f"{n}.medico.txt"
                if med:
                    f.write_text(med, encoding="utf-8")
                else:
                    f.unlink(missing_ok=True)
                anotar_voz(n, medico_por="usuaria" if med else "")
                if (DATOS / f"{n}.final.txt").exists():
                    actualizar_muestra(n, med)       # ya guardado: la muestra de voz se corrige al momento
                L.info("CASO", f"{visible(n)}: médico cambiado a {med or 'ninguno'} ({self.pc}).")
                vz = resumen_voz(n) or {}
                return self._json({"ok": True, "voz": vz,
                                   "regenerar": bool(vz) and (vz.get("medico_ia") or "") != med
                                   and not (DATOS / f"{n}.final.txt").exists()})
            if u.path == "/api/paciente":
                p = PAC.corregir(DATOS, n, datos.get("paciente", ""))
                L.info("CASO", f"{visible(n)}: nombre del paciente " + ("corregido a mano" if datos.get("paciente", "").strip()
                                                                       else "vuelto a sacar del dictado") + f" ({self.pc}).")
                return self._json({"ok": True, "paciente": p})
            if u.path == "/api/procesar":
                if n in PAUSAS or ESTADO.get(n, {}).get("estado") == "en pausa":
                    return self._json({"error": "Está en pausa: reanudalo desde la lista."}, 409)
                L.info("IA", f"{self.quien} pidió volver a generar {visible(n)}"
                             + (" con su estilo." if self.usuario else "."))
                if self.usuario:
                    poner_usuario_caso(n, self.usuario)     # volver a generar = con el estilo de quien lo pide
                encolar(n)
                return self._json({"ok": True})
            if u.path == "/api/borrador":
                try:
                    revision = BOR.guardar(DATOS, n, datos)
                except BOR.Conflicto as ex:
                    return self._json({"error": str(ex)}, 409)
                except BOR.Corrupto as ex:
                    return self._json({'error': str(ex)}, 503)
                except ValueError as ex:
                    return self._json({"error": str(ex)}, 400)
                except OSError:
                    L.error("CASO", "No se pudo guardar el borrador en disco.", exc=True)
                    return self._json({"error": "No se pudo guardar el borrador en el servidor. Conservá el caso abierto y reintentá."}, 503)
                return self._json({"ok": True, "revision": revision})
            if u.path == "/api/formato_caso":     # formato elegido a mano en la vista previa
                f = DATOS / f"{n}.formato.json"
                fm = datos.get("formato")
                if isinstance(fm, dict) and fm.get("parrafos"):
                    escribir_atomico(f, json.dumps(fm, ensure_ascii=False))
                else:
                    f.unlink(missing_ok=True)
                L.debug("CASO", f"{visible(n)}: formato de la vista previa guardado ({self.pc}).")
                return self._json({"ok": True})
            if u.path == "/api/formato_caso/agregar":     # formato de una autocorrección de Word (app del trabajo)
                nuevos = []
                for x in (datos.get("parrafos") or [])[:200]:
                    if not isinstance(x, dict) or not isinstance(x.get("t"), str) or not x["t"].strip():
                        continue
                    r = [y for y in (x.get("r") or []) if isinstance(y, dict) and isinstance(y.get("t"), str)]
                    nuevos.append({"t": x["t"], "a": x.get("a") if isinstance(x.get("a"), str) else "",
                                   "r": r or [{"t": x["t"]}]})
                if nuevos:
                    with FMT_LOCK:
                        fm = formato_de(n)
                        if not isinstance(fm, dict) or not isinstance(fm.get("parrafos"), list):
                            fm = {"v": 1, "parrafos": []}
                        fm["parrafos"].extend(nuevos)
                        (DATOS / f"{n}.formato.json").write_text(json.dumps(fm, ensure_ascii=False), encoding="utf-8")
                    L.debug("CASO", f"{visible(n)}: formato de una autocorrección de Word agregado ({self.pc}).")
                return self._json({"ok": True})
            if u.path == "/api/finalizar":
                sumar_revision(n, datos.get("rev"), self.pc)
                return self._json(finalizar(n, datos.get("texto", ""), self.pc, self.usuario))
            if u.path == "/api/abrir":
                p = INFORMES / f"{n}.docx"
                if p.exists() and not self.remoto:
                    try:
                        P.abrir(p)
                    except OSError:
                        pass
                return self._json({"ok": p.exists()})
            self.send_error(404)
        except CP.ErrorCola:
            L.error('COLA', 'No se confirmó la operación en la cola persistente.', exc=True)
            self._json({'error': 'No se pudo confirmar la cola del servidor. Conservá el audio y reintentá.'}, 503)
        except PermissionError:
            L.aviso("INFORME", f"No se pudo guardar ({u.path}, {self.pc}): el Word está abierto. "
                               f"Hay que cerrarlo y volver a intentar.")
            self._json({"error": "El Word está abierto: cerralo y volvé a intentar."}, 409)
        except Exception as ex:
            L.error("SERVIDOR", f"Falló {u.path} pedido por {getattr(self, 'pc', '?')}: {mensaje_amigable(ex)}",
                    exc=True)
            self._json({"error": str(ex)}, 500)

    # ------------------------------------------- panel de administración desde el trabajo
    def _panel_sin_permiso(self, ruta):
        """Pedido al panel sin permiso. Desde el trabajo: si el panel está habilitado, se pide su contraseña."""
        es_pagina = ruta in PAGINAS_ADMIN
        if self.remoto:
            if R.admin_configurado():
                if es_pagina:
                    return self._html(pagina_panel_entrar(self.pc, ruta))
                return self._json({"error": "La sesión del panel venció: volvé a escribir su contraseña.",
                                   "entrar_panel": True}, 401)
            if L.una_vez(("admin_remoto", self.pc), 600):
                L.aviso("ACCESO", f"{self.pc} intentó abrir el panel de administración, pero no está habilitado para "
                                  f"las PC del trabajo (falta configurar su contraseña en el panel del servidor).")
            if es_pagina:
                return self._html(PAGINA_PANEL_NO_HABILITADO)
            return self._json({"error": "El panel de administración no está habilitado para las PC del trabajo."}, 403)
        if L.una_vez(("admin_host", self.headers.get("Host")), 600):
            L.aviso("ACCESO", f"Pedido al panel de administración con la dirección «{(self.headers.get('Host') or '')[:60]}» "
                              f"rechazado: en esta PC el panel se abre como http://127.0.0.1:{PUERTO}/admin.")
        if es_pagina:
            return self._html(PAGINA_SOLO_LOCAL, 403)
        return self._json({"error": "El panel de administración se abre como http://127.0.0.1:%d/admin." % PUERTO}, 403)

    def _panel_entrar(self, datos):
        if not self.remoto:
            return self._json({"ok": True})          # en la PC del servidor no hace falta contraseña
        ip = self._ip()
        motivo = ADM.motivo_origen(self, PUERTO)
        if motivo:
            L.aviso("ACCESO", f"Pedido para entrar al panel desde {self.pc} rechazado: no vino de la página del panel "
                              f"(IP {ip}; {motivo}).")
            return self._json({"error": "Pedido rechazado."}, 403)
        if not R.admin_configurado():
            return self._json({"error": "El panel de administración no está habilitado para las PC del trabajo."}, 403)
        clave = f"admin:{self.pc}"
        if R.demasiados_fallos(clave):
            if L.una_vez(("admin_bloq", self.pc), 120):
                L.aviso("ACCESO", f"{self.pc} sigue intentando entrar al panel de administración: bloqueado 10 minutos "
                                  f"por contraseñas incorrectas (IP {ip}).")
            return self._json({"error": "Demasiados intentos fallidos. Esperá 10 minutos."}, 429)
        if not R.contrasena_admin_ok(str(datos.get("contrasena", ""))):
            R.anotar_fallo(clave)
            k = len(R.FALLOS.get(clave, []))
            L.aviso("ACCESO", f"Contraseña del panel de administración incorrecta desde {self.pc} (IP {ip}). "
                              + ("Esa PC queda bloqueada 10 minutos para el panel." if k >= 5 else f"Intento {k} de 5."))
            return self._json({"error": "Contraseña incorrecta." + ("" if k >= 5 else
                                         f" Te quedan {5 - k} {'intento' if 5 - k == 1 else 'intentos'}.")}, 401)
        R.FALLOS.pop(clave, None)
        tok = R.nueva_sesion_admin(self.pc, ip)
        L.ok("ACCESO", f"{self.pc} entró al panel de administración desde el trabajo (IP {ip}).")
        return self._json({"ok": True}, cookie=R.cookie_admin(tok))

    def _avisar_fallo(self, pc, ip, donde):
        k = len(R.FALLOS.get(ip, []))
        extra = " La IP queda bloqueada 10 minutos." if k >= 5 else f" Intento {k} de 5."
        L.aviso("ACCESO", f"Contraseña incorrecta para «{pc[:24]}» {donde} (IP {ip}).{extra}")


# ------------------------------------------------------- panel de administración
def estado_tunel():
    t = R.URL_TUNEL
    if not TUNEL["modo"]:
        e = "apagado"
    elif not R.configurado():
        e = "sin_contrasena"
    elif TUNEL["error"]:
        e = "puerto_ocupado"
    elif not t.get("iniciado"):
        e = "detenido"
    else:
        e = {"activo": "activo", "abriendo": "abriendo", "reconectando": "reconectando",
             "sin cloudflared": "sin_cloudflared", "sin devtunnel": "sin_devtunnel",
             "sin sesion": "sin_sesion", "sin configurar": "sin_configurar",
             "error": "reconectando"}.get(t.get("estado") or "", "abriendo")
        if e == "abriendo" and t.get("url") and t.get("servicio") != "devtunnel":
            e = "conectando"           # ya tiene dirección, falta que Cloudflare confirme la conexión
    servicio = t.get("servicio") or R.servicio_tunel()
    return {"modo": TUNEL["modo"], "estado": e, "url": t.get("url"), "desde": t.get("desde"),
            "servicio": servicio, "nombre_servicio": R.nombre_servicio(servicio), "error": TUNEL["error"],
            "puerto_tunel": PUERTO_TUNEL if servicio == "devtunnel" else None,
            "cambio": t.get("cambio"), "publicada": t.get("publicada"), "error_pub": t.get("error_pub"),
            "reinicios": t.get("reinicios", 0), "centro": t.get("centro")}


def estado_admin():
    ahora = time.time()
    try:
        cs = listar_casos()
    except Exception:
        cs = []
    k = {e: sum(1 for c in cs if c["estado"] == e) for e in ("listo", "nuevo", "error", "revisado")}
    if not SIMULAR and ahora - _PANEL["gpu_t"] > 3:
        _PANEL["gpu"], _PANEL["gpu_t"] = placa_de_video(), ahora
    gpu = _PANEL["gpu"]
    man = A.manifiesto()
    oficial = man.get("version") or ""
    vinc = R.pcs_vinculadas()
    nombres = set(vinc) | set(VISTO) | {v["pc"] for v in list(R.SESIONES.values())}
    con_panel = {x["pc"] for x in R.sesiones_admin()}
    pcs = []
    for pc in sorted(nombres, key=str.lower):
        v = vinc.get(pc, {})
        ultima = max(VISTO.get(pc, 0), v.get("ultima") or 0) or None
        version = A.VERSION_PC.get(pc) or v.get("version")
        pcs.append({"pc": pc, "llaves": v.get("llaves", 0), "vinculada": v.get("vinculada"),
                    "ultima_vinculacion": v.get("ultima_vinculacion"), "ultima": ultima,
                    "conectada": bool(ultima and ahora - ultima < 60), "version": version,
                    "desactualizada": bool(version and oficial and version != oficial),
                    "medico": R.medico_pc(pc), "sesiones": R.sesiones_de(pc), "panel": pc in con_panel,
                    "revisando": sorted(visible(c) for c, b in list(R.BLOQUEOS.items())
                                        if b["pc"] == pc and ahora - b["t"] < R.BLOQUEO_SEG)})
    gen, tr = _en("generando"), _en("transcribiendo")
    return {
        "ahora": ahora,
        "servidor": {"version": VERSION, "desde": INICIO, "simulado": SIMULAR, "url": f"http://127.0.0.1:{PUERTO}",
                     "registros": str(L.CARPETA),
                     "sistema": P.NOMBRE, "puede_abrir": P.puede_abrir()},
        "ia": {"estado": E_IA["e"], "modelo": CFG["modelo_ia"],
               "trabajando": f"armando el informe de «{titulo_de(gen[0])}»" if gen else None},
        "whisper": {"modelo": CFG["modelo_whisper"],
                    "trabajando": f"transcribiendo «{titulo_de(tr[0])}»" if tr else None},
        "gpu": gpu[0] if gpu else ("simulada (modo prueba)" if SIMULAR else None), "gpu_tono": gpu[1] if gpu else None,
        "casos": {**k, "en_proceso": en_proceso()},
        "hoy": dict(L.HOY),
        "tunel": estado_tunel(),
        "contrasena": R.configurado(),
        "usuarios": estado_usuarios(),
        "admin_remoto": {"configurada": R.admin_configurado(), "desde": R.admin_desde(), "sesiones": R.sesiones_admin()},
        "app": {"version": oficial, "archivos": len(man.get("archivos", []))},
        "pcs": pcs,
        "registro": ADM.ultimos_eventos(),
        "mantenimiento": estado_mantenimiento(),
        "cola": cola_en_vivo(),
        "abiertos": casos_abiertos(),
    }


def estado_usuarios():
    ses = R.sesiones_de_usuarios()
    out = []
    for u in U.lista():
        prop = {"plantillas": len(N.secciones_de_usuario(u["clave"])),
                "medicos": len(N.medicos_con_notas_propias(u["clave"])),
                "reglas": bool(U.leer_archivo(u["clave"], "reglas_dictado.md").strip()),
                "formato": bool(U.formato(u["clave"]))}
        out.append({**u, "en": sorted(set(ses.get(u["clave"], []))), "propio": prop})
    return out


def accion_usuario(accion, d, usuario, pc):
    """Lo que cada transcriptor cambia de sí mismo. Devuelve (respuesta, código)."""
    nombre = U.nombre_de(usuario)
    if accion == "contrasena":
        err = U.cambiar_propia(usuario, str(d.get("actual") or ""), str(d.get("nueva") or ""))
        if err:
            return {"error": err}, 400
        L.ok("ACCESO", f"{nombre} cambió su contraseña ({pc}).")
        return {"ok": True}, 200
    if accion == "preferencias":
        return {"ok": True, "preferencias": U.guardar_preferencias(usuario, d.get("preferencias"))}, 200
    if accion == "formato":
        try:
            f = U.guardar_formato(usuario, d.get("formato") or {})
        except ValueError as ex:
            return {"error": str(ex)}, 400
        L.info("CONFIG", f"{nombre} cambió el formato de su Word ({pc}): "
                         + (", ".join(f"{k}={v}" for k, v in f.items()) or "vuelve al general") + ".")
        return {"ok": True, "formato": f}, 200
    if accion == "reglas":
        texto = d.get("reglas")
        if not isinstance(texto, str) or len(texto) > 50_000:
            return {"error": "Las reglas tienen que ser texto (como mucho 50.000 caracteres)."}, 400
        U.escribir_archivo(usuario, "reglas_dictado.md", texto.strip() + "\n" if texto.strip() else "")
        L.ok("CONFIG", f"{nombre} guardó sus reglas de dictado propias ({pc}).")
        return {"ok": True}, 200
    return {"error": "Acción desconocida"}, 404


def accion_admin(accion, d, quien=None):
    """Botones del panel. Devuelve (respuesta, código). quien = PC del trabajo que usa el panel (None = esta PC)."""
    desde = f"desde el panel de administración (usado en {quien})" if quien else "desde el panel de administración"
    if accion in ("medicos/agregar", "medicos/modificar", "medicos/eliminar"):
        try:
            if accion == "medicos/eliminar":
                N.eliminar_medico(d.get("original"))
                nombre = d.get("original")
            else:
                if accion == "medicos/modificar" and not isinstance(d.get("original"), str):
                    return {"error": "Elegí el médico que querés modificar."}, 400
                nombre = N.guardar_medico(d.get("nombre", ""), d.get("notas", ""),
                                          crear=accion == "medicos/agregar",
                                          original=d.get("original") if accion == "medicos/modificar" else None)
            L.ok("CONFIG", f"Médicos: {accion.split('/')[-1]} «{nombre}» {desde}.")
            return {"ok": True, "medico": nombre}, 200
        except FileExistsError as ex:
            return {"error": str(ex)}, 409
        except FileNotFoundError as ex:
            return {"error": str(ex)}, 404
        except ValueError as ex:
            return {"error": str(ex)}, 400
    if accion.startswith("usuarios/"):
        clave = str(d.get("usuario") or "")
        try:
            if accion == "usuarios/crear":
                clave = U.crear(d.get("nombre", ""), str(d.get("contrasena") or ""))
                L.ok("ACCESO", f"Transcriptor creado: {U.nombre_de(clave)} {desde}. Entra con la contraseña inicial "
                               f"y la cambia la primera vez.")
                return {"ok": True, "usuario": clave, "msg": f"Listo: {U.nombre_de(clave)} ya puede entrar."}, 200
            if accion == "usuarios/contrasena":
                U.poner_contrasena(clave, str(d.get("contrasena") or ""), cambiar=True)
                n = R.cerrar_sesiones_usuario(clave)
                L.ok("ACCESO", f"Contraseña de {U.nombre_de(clave)} restablecida {desde}"
                               + (f"; se cerraron {L.plural(n, 'sesión abierta', 'sesiones abiertas')}." if n else "."))
                return {"ok": True, "msg": "Contraseña restablecida: la cambia la próxima vez que entre."}, 200
            if accion == "usuarios/activo":
                activo = d.get("activo") is True
                U.activar(clave, activo)
                if not activo:
                    R.cerrar_sesiones_usuario(clave)
                L.ok("ACCESO", f"Transcriptor {U.nombre_de(clave)} {'reactivado' if activo else 'desactivado'} {desde}.")
                return {"ok": True}, 200
            if accion == "usuarios/nombre":
                U.renombrar(clave, d.get("nombre", ""))
                L.ok("ACCESO", f"Transcriptor renombrado a {U.nombre_de(clave)} {desde}.")
                return {"ok": True}, 200
        except FileExistsError as ex:
            return {"error": str(ex)}, 409
        except FileNotFoundError as ex:
            return {"error": str(ex)}, 404
        except ValueError as ex:
            return {"error": str(ex)}, 400
        return {"error": "Acción desconocida"}, 404
    if quien and accion in SOLO_EN_EL_SERVIDOR:
        L.aviso("ACCESO", f"{quien} intentó «{accion}» en el panel de administración: solo se puede en la PC del servidor.")
        return {"error": "Eso solo se puede hacer en la PC del servidor."}, 403
    if accion == "tunel/reiniciar":
        err = R.reiniciar_tunel()
        if err:
            return {"error": err}, 409
        L.info("TÚNEL", f"Reinicio del túnel pedido {desde}.")
        if R.URL_TUNEL.get("servicio") == "devtunnel":
            return {"ok": True, "msg": "Túnel reiniciándose: en unos segundos vuelve, con la misma dirección."}, 200
        return {"ok": True, "msg": "Túnel reiniciándose: en unos segundos tiene dirección nueva y se publica sola."}, 200
    if accion == "tunel/publicar":
        url = R.URL_TUNEL.get("url")
        if not url:
            return {"error": "Todavía no hay dirección para publicar."}, 409
        if not R.publicar_url(url, forzar=True):
            return {"error": "No se pudo publicar en ntfy.sh: " + (R.URL_TUNEL.get("error_pub") or "sin detalle")}, 502
        L.ok("TÚNEL", f"Dirección publicada de nuevo {desde}.")
        return {"ok": True, "msg": "Dirección publicada: las aplicaciones del trabajo la encuentran solas."}, 200
    if accion == "pc/anular":
        pc = str(d.get("pc", "")).strip()
        if not pc:
            return {"error": "Falta el nombre de la PC."}, 400
        tenia_sesion = R.sesiones_de(pc)
        n = R.anular_pc(pc)
        if not n and not tenia_sesion:
            return {"error": f"No encontré llaves ni sesiones de {pc}."}, 404
        VISTO.pop(pc, None)
        L.aviso("ACCESO", f"PC anulada {desde}: {pc} ({L.plural(n, 'llave')}, "
                          f"{L.plural(tenia_sesion, 'sesión abierta', 'sesiones abiertas')}). "
                          f"Para volver a usarla hay que vincularla de nuevo con la contraseña.")
        return {"ok": True, "msg": f"{pc} anulada. Para volver a usarla hay que vincularla con la contraseña."}, 200
    if accion == "contrasena":
        c = str(d.get("contrasena", ""))
        if len(c) < 8:
            return {"error": "Usá al menos 8 caracteres."}, 400
        if R.contrasena_admin_ok(c):
            return {"error": "Usá una contraseña distinta de la del panel de administración."}, 400
        ya = R.configurado()
        R.poner_contrasena(c)
        L.ok("ACCESO", "Contraseña del acceso remoto " + ("cambiada" if ya else "configurada")
             + f" {desde}. Las PC ya vinculadas siguen funcionando.")
        msg = "Contraseña " + ("cambiada" if ya else "guardada") + ". Las PC ya vinculadas siguen funcionando."
        if TUNEL["modo"] and not R.URL_TUNEL.get("iniciado"):
            abrir_tunel()
            msg += " Abriendo el túnel para las PC del trabajo…"
        return {"ok": True, "msg": msg}, 200
    if accion == "contrasena_admin":
        c = str(d.get("contrasena", ""))
        if len(c) < 10:
            return {"error": "Usá al menos 10 caracteres: con esta contraseña se maneja todo el servidor."}, 400
        if R.contrasena_ok(c):
            return {"error": "Usá una contraseña distinta de la del acceso remoto (esa la conocen todas las PC del trabajo)."}, 400
        ya = R.admin_configurado()
        n = R.poner_contrasena_admin(c)
        L.ok("ACCESO", "Contraseña del panel de administración desde el trabajo " + ("cambiada" if ya else "configurada")
             + ": desde ahora se puede abrir el panel en las PC del trabajo con esa contraseña."
             + (f" Se cerraron {L.plural(n, 'sesión abierta', 'sesiones abiertas')} del panel." if n else ""))
        return {"ok": True, "msg": ("Contraseña cambiada." if ya else "Listo: el panel ya se puede abrir desde las PC del trabajo.")
                + (f" {_cerradas(n)} del panel abiertas con la anterior." if n else "")}, 200
    if accion == "contrasena_admin/quitar":
        if not R.admin_configurado():
            return {"error": "El panel ya no se puede abrir desde el trabajo."}, 409
        n = R.quitar_contrasena_admin()
        L.aviso("ACCESO", "Acceso al panel de administración desde el trabajo desactivado"
                + (f"; se cerraron {L.plural(n, 'sesión abierta', 'sesiones abiertas')}." if n else "."))
        return {"ok": True, "msg": "Listo: el panel ya no se puede abrir desde las PC del trabajo."
                + (f" {_cerradas(n)}." if n else "")}, 200
    if accion == "sesiones_admin/cerrar":
        n = R.cerrar_sesiones_admin()
        L.info("ACCESO", f"Sesiones del panel de administración cerradas desde esta PC: {n}.")
        return {"ok": True, "msg": f"{_cerradas(n)} del panel." if n else "No había sesiones abiertas."}, 200
    if accion == "reinicio":
        return programar_reinicio(d.get("en"), d.get("avisar", True), d.get("texto"), quien)
    if accion == "reinicio/cancelar":
        return cancelar_reinicio(quien)
    if accion == "reinicio/ya":
        return reiniciar_ya(quien)
    if accion == "mensaje":
        texto = " ".join(str(d.get("texto", "")).split())
        if not texto:
            return {"error": "Escribí el mensaje."}, 400
        if len(texto) > 300:
            return {"error": "El mensaje es muy largo: usá menos de 300 letras."}, 400
        try:
            minutos = max(0, min(int(d.get("minutos") or 0), 24 * 60))
        except (TypeError, ValueError):
            minutos = 0
        tipo = "aviso" if d.get("tipo") == "aviso" else "info"
        if REINICIO and REINICIO.get("avisar"):
            return {"error": "Hay un reinicio programado con su aviso en pantalla: cancelalo o esperá a que termine."}, 409
        poner_mensaje(texto, minutos, tipo, por=quien)
        L.info("SERVIDOR", f"Mensaje para las PC {desde}" + (f" (por {minutos} min)" if minutos else "") + f": «{texto}»")
        return {"ok": True, "msg": "Mensaje publicado: aparece en todas las PC en unos segundos."}, 200
    if accion == "mensaje/quitar":
        if REINICIO and MENSAJE.get("reinicio"):
            return {"error": "Ese aviso es del reinicio programado: para quitarlo, cancelá el reinicio."}, 409
        if not quitar_mensaje():
            return {"error": "No hay ningún mensaje en pantalla."}, 409
        L.info("SERVIDOR", f"Mensaje para las PC quitado {desde}.")
        return {"ok": True, "msg": "Mensaje quitado."}, 200
    if accion in ("caso/pausar", "caso/reanudar"):
        n = str(d.get("nombre", ""))
        if not n or "/" in n or "\\" in n or ".." in n:
            return {"error": "Caso inválido."}, 400
        return (pausar if accion == "caso/pausar" else reanudar)(n, "el panel de administración")
    if accion == "caso/liberar":
        n = str(d.get("nombre", ""))
        if not n or "/" in n or "\\" in n or ".." in n:
            return {"error": "Caso inválido."}, 400
        pc = R.liberar(n)
        if not pc:
            return {"error": "Ese caso ya no está abierto en ninguna PC."}, 409
        L.aviso("CASO", f"{visible(n)} liberado {desde}: lo tenía abierto {pc}. Lo que escribió hasta su último "
                        f"guardado automático quedó como borrador; ya se puede abrir desde otra PC.")
        return {"ok": True, "msg": f"Caso liberado. {pc} deja de poder guardar cambios en él; ya se puede abrir desde otra PC."}, 200
    if accion == "correcciones/regla":
        r = CORR.agregar_regla(str(d.get("texto", "")))
        if r.get("error"):
            return r, 400
        L.ok("CONFIG", f"Regla agregada a reglas_dictado.md {desde}: «{r['linea']}» (copia anterior en conocimiento\\copias).")
        return {"ok": True, "msg": "Regla agregada: la IA la usa desde el próximo informe.", "linea": r["linea"]}, 200
    if accion == "abrir":
        que = d.get("que")
        rutas = {"registros": L.CARPETA, "registro_hoy": L.archivo_del_dia(), "cliente": AQUI / "cliente"}
        if que not in rutas:
            return {"error": "No sé qué abrir."}, 400
        try:
            if not ADM.abrir_en_windows(rutas[que]):
                return {"error": f"Abrilo a mano: {rutas[que]}"}, 501
        except OSError as ex:
            return {"error": f"No se pudo abrir {rutas[que]}: {ex}"}, 500
        return {"ok": True}, 200
    return {"error": "Acción desconocida."}, 404


def _cerradas(n):
    return "Se cerró 1 sesión" if n == 1 else f"Se cerraron {n} sesiones"


# Lo que desde una PC del trabajo no se puede hacer aunque se tenga la contraseña del panel: abrir carpetas o
# archivos (se abrirían en la pantalla del servidor) y tocar la contraseña del propio panel o sus sesiones.
SOLO_EN_EL_SERVIDOR = {"abrir", "contrasena_admin", "contrasena_admin/quitar", "sesiones_admin/cerrar",
                       "correcciones/regla", "caso/pausar", "caso/reanudar"}

PAGINA_PANEL_NO_HABILITADO = """<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Administración · Transcripción</title>
<style>:root{color-scheme:light dark}body{margin:0;min-height:100vh;display:grid;place-items:center;
font:15px/1.5 "Segoe UI",system-ui,sans-serif;background:Canvas;color:CanvasText}
div{max-width:440px;padding:24px}h1{font-size:19px;margin:0 0 8px}a.volver{display:inline-block;margin-top:6px;font-weight:600;text-decoration:none;color:CanvasText;border:1px solid GrayText;border-radius:7px;padding:7px 14px}a.volver:hover{border-color:#1f5fbf}a.volver:focus-visible{outline:2px solid #1f5fbf;outline-offset:2px}</style></head>
<body><div><h1>Panel no habilitado en el trabajo</h1><p>El panel de administración todavía no se puede abrir desde
las PC del trabajo. Para habilitarlo, en la PC del servidor abrí <b>http://127.0.0.1:8765/admin</b> y configurá
la <b>contraseña del panel desde el trabajo</b>.</p>
<p><a class="volver" href="/">Volver a los informes</a></p></div></body></html>"""


def pagina_panel_entrar(pc, volver):
    import html as _h
    return (PAGINA_PANEL_ENTRAR.replace("{{pc}}", _h.escape(pc or ""))
            .replace("{{volver}}", json.dumps(volver if volver in PAGINAS_ADMIN else "/admin")))


PAGINA_PANEL_ENTRAR = """<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Panel de administración · Transcripción</title>
<style>:root{color-scheme:light;--bg:#f3f2ef;--p:#fbfbfa;--tx:#1d1d1b;--mu:#5c5b55;--bd:#cfcdc6;--ac:#1f5fbf;--err:#b3261e}
@media (prefers-color-scheme:dark){:root{color-scheme:dark;--bg:#141413;--p:#1b1b1a;--tx:#ebeae5;--mu:#a19f98;--bd:#45443f;--ac:#7aa7f0;--err:#ff8a80}}
body{margin:0;min-height:100vh;display:grid;place-items:center;background:var(--bg);color:var(--tx);font:15px/1.45 "Segoe UI",system-ui,sans-serif}
form{background:var(--p);border:1px solid var(--bd);border-radius:12px;padding:28px;width:min(380px,calc(100vw - 32px));box-sizing:border-box;display:flex;flex-direction:column;gap:14px}
h1{font-size:20px;margin:0}p{margin:0;color:var(--mu);font-size:13.5px}label{display:flex;flex-direction:column;gap:4px;font-weight:600}
input{font:inherit;font-weight:400;color:var(--tx);background:var(--bg);border:1px solid var(--bd);border-radius:7px;padding:8px 10px}
input:focus-visible,button:focus-visible,a:focus-visible{outline:2px solid var(--ac);outline-offset:2px}
button{font:inherit;font-weight:600;background:var(--ac);color:#fff;border:0;border-radius:7px;padding:9px;cursor:pointer}
button:disabled{opacity:.6;cursor:default}.err{color:var(--err);font-weight:600;font-size:13.5px;min-height:1em}
a.volver{display:block;text-align:center;font-weight:600;text-decoration:none;color:var(--tx);background:var(--p);
border:1px solid var(--bd);border-radius:7px;padding:8px}
a.volver:hover{border-color:var(--ac)}</style>
</head><body><form id="f" autocomplete="off"><h1>Panel de administración</h1>
<p>Estás en <b>{{pc}}</b>. Escribí la contraseña del panel: es distinta de la del acceso remoto y la configura
quien administra el servidor.</p>
<label>Contraseña del panel<input id="c" type="password" required autocomplete="off" autofocus></label>
<div class="err" id="err" role="alert"></div>
<button id="b">Entrar al panel</button><a class="volver" href="/">Volver a los informes</a></form>
<script>
const VOLVER = {{volver}};
document.getElementById('f').onsubmit = async ev => {
  ev.preventDefault();
  const b = document.getElementById('b'), c = document.getElementById('c'), err = document.getElementById('err');
  b.disabled = true; err.textContent = '';
  try {
    const r = await fetch('/api/admin/entrar', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Panel': '1'},
                                                 body: JSON.stringify({contrasena: c.value})});
    const j = await r.json().catch(() => ({}));
    if(r.ok){ location.replace(VOLVER); return; }
    if(j.entrar){ location.replace('/'); return; }
    err.textContent = j.error || ('No se pudo entrar (error ' + r.status + ').');
  } catch(e){ err.textContent = 'No hay conexión con el servidor. Probá de nuevo en unos segundos.'; }
  b.disabled = false; c.value = ''; c.focus();
};
</script></body></html>"""


PAGINA_SOLO_LOCAL = """<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Administración · Transcripción</title>
<style>:root{color-scheme:light dark}body{margin:0;min-height:100vh;display:grid;place-items:center;
font:15px/1.5 "Segoe UI",system-ui,sans-serif;background:Canvas;color:CanvasText}
div{max-width:420px;padding:24px}h1{font-size:19px;margin:0 0 8px}a.volver{display:inline-block;margin-top:6px;font-weight:600;text-decoration:none;color:CanvasText;border:1px solid GrayText;border-radius:7px;padding:7px 14px}a.volver:hover{border-color:#1f5fbf}a.volver:focus-visible{outline:2px solid #1f5fbf;outline-offset:2px}</style></head>
<body><div><h1>Solo en la PC del servidor</h1><p>El panel de administración se abre únicamente en la PC donde
corre el servidor, en <b>http://127.0.0.1:8765/admin</b> (escribí exactamente esa dirección). Desde las PC del
trabajo se abre con el engranaje de la lista, si se habilitó con su contraseña.</p>
<p><a class="volver" href="/">Volver a los informes</a></p></div></body></html>"""


def anunciar_audio(nombre, cuerpo, desde):
    """Línea de «audio recibido» con duración, tamaño, médico y lugar en la cola."""
    L.contar("recibidos")
    dur = duracion_wav(datos=cuerpo)
    med = medico_de(nombre)
    partes = [f"«{titulo_de(nombre)}»", L.mmss(dur) if dur else None, L.tamano(len(cuerpo)),
              f"médico {med}" if med else "sin médico elegido"]
    pos = en_proceso()
    L.ok("AUDIO", f"Audio recibido {desde}: " + " · ".join(x for x in partes if x)
         + (f" · en cola ({pos} en proceso)" if pos > 1 else ""))


PAGINA_ENTRAR = """<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Entrar · Transcripción</title>
<style>:root{color-scheme:light;--bg:#f3f2ef;--p:#fbfbfa;--tx:#1d1d1b;--mu:#5c5b55;--bd:#cfcdc6;--ac:#1f5fbf;--err:#b3261e}
@media (prefers-color-scheme:dark){:root{color-scheme:dark;--bg:#141413;--p:#1b1b1a;--tx:#ebeae5;--mu:#a19f98;--bd:#45443f;--ac:#7aa7f0;--err:#ff8a80}}
body{margin:0;min-height:100vh;display:grid;place-items:center;background:var(--bg);color:var(--tx);font:15px/1.45 "Segoe UI",system-ui,sans-serif}
form{background:var(--p);border:1px solid var(--bd);border-radius:12px;padding:28px;width:min(360px,calc(100vw - 32px));box-sizing:border-box;display:flex;flex-direction:column;gap:14px}
h1{font-size:20px;margin:0}p{margin:0;color:var(--mu);font-size:13.5px}label{display:flex;flex-direction:column;gap:4px;font-weight:600}
input{font:inherit;font-weight:400;color:var(--tx);background:var(--bg);border:1px solid var(--bd);border-radius:7px;padding:8px 10px}
button{font:inherit;font-weight:600;background:var(--ac);color:#fff;border:0;border-radius:7px;padding:9px}.err{color:var(--err);font-weight:600}</style>
</head><body><form method="post" action="{{accion}}"><h1>Transcripción</h1>
<p>{{texto}}</p>{{error}}
{{campos}}
<button>Entrar</button></form></body></html>"""


class HTunel(H):
    """Pedidos que entran por el puerto propio del túnel de Microsoft: siempre de las PC del trabajo."""
    es_puerto_tunel = True

    def _es_remoto(self):
        return True

    def _ip(self):
        xff = (self.headers.get("X-Forwarded-For") or "").split(",")[0].strip()
        return xff or self.headers.get("Cf-Connecting-Ip") or self.client_address[0]


class Servidor(ThreadingHTTPServer):
    daemon_threads = True

    def handle_error(self, request, client_address):
        """Una PC que corta la conexión a mitad de camino es normal: no ensuciar la ventana."""
        ex = sys.exc_info()[1]
        if isinstance(ex, (ConnectionError, TimeoutError, BrokenPipeError)):
            L.debug("SERVIDOR", f"Conexión cortada por el otro lado: {ex!r}")
        else:
            L.error("SERVIDOR", "Error atendiendo un pedido.", exc=True)


def placa_de_video():
    """(texto, tono) con memoria en uso, carga y temperatura de la placa, o None."""
    try:
        import subprocess
        r = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.used,memory.total,utilization.gpu,temperature.gpu",
                            "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=4,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        nombre, usada, total, uso, temp = [x.strip() for x in r.stdout.strip().splitlines()[0].split(",")]
        gb = lambda m: f"{int(m) / 1024:.1f}".replace(".", ",")
        nombre = nombre.replace("NVIDIA ", "").replace("GeForce ", "")
        # Algunos drivers informan la temperatura con decimales (p. ej. 51.12).
        tono = "aviso" if float(temp) >= 85 or int(usada) >= 0.97 * int(total) else None
        return f"{nombre} · memoria {gb(usada)} de {gb(total)} GB · uso {uso}% · {temp} °C", tono
    except Exception:
        return None


_PANEL = {"casos_t": 0, "casos": None, "gpu_t": 0, "gpu": None}


def _en(estado):
    with LOCK:
        return [n for n, v in ESTADO.items() if v.get("estado") == estado]


def filas_encabezado(url, tunel):
    """Lo que muestra el encabezado fijo; se llama cada segundo (lo pesado se refresca cada 3 s)."""
    ahora = time.time()
    if ahora - _PANEL["casos_t"] > 3:
        try:
            cs = listar_casos()
            _PANEL["casos"] = {k: sum(1 for x in cs if x["estado"] == k) for k in ("listo", "nuevo", "error")}
        except Exception:
            pass
        _PANEL["casos_t"] = ahora
    if ahora - _PANEL["gpu_t"] > 3 and not SIMULAR:
        _PANEL["gpu"], _PANEL["gpu_t"] = placa_de_video(), ahora
    filas = [("Interfaz", url, None), ("Administración", f"{url}/admin (PC vinculadas, túnel, errores)", None)]
    if SIMULAR:
        filas.append(("Modo", "PRUEBA: Whisper y la IA están simulados", "aviso"))
    # acceso remoto
    if not tunel:
        filas.append(("Acceso remoto", f"apagado: solo esta PC (para el trabajo usá {P.script('iniciar_servidor')})", None))
    elif not R.configurado():
        filas.append(("Acceso remoto", f"falta la contraseña: ejecutá {P.script('configurar_acceso')}", "aviso"))
    elif R.URL_TUNEL.get("url") and R.URL_TUNEL.get("estado") == "activo":
        desde = R.URL_TUNEL.get("desde")
        filas.append(("Acceso remoto", f"túnel de {R.nombre_servicio(R.URL_TUNEL.get('servicio'))} activo"
                      + (f" desde hace {L.hace(ahora - desde)}" if desde else ""), "ok"))
    elif R.URL_TUNEL.get("estado") in ("sin sesion", "sin configurar", "sin devtunnel") or TUNEL["error"]:
        filas.append(("Acceso remoto", TUNEL["error"] or f"Microsoft Dev Tunnels no está listo: ejecutá "
                                                         f"{P.script('configurar_tunel')}", "error"))
    else:
        filas.append(("Acceso remoto", "túnel abriéndose o reconectando…", "aviso"))
    if tunel and R.configurado():      # en su propio renglón, para que la dirección entre entera
        filas.append(("Dirección", R.URL_TUNEL.get("url") or f"esperando a {R.nombre_servicio()}…", None))
    if tunel:
        activas = sorted((p, t) for p, t in VISTO.items() if ahora - t < 60)
        filas.append(("PC conectadas", ", ".join(p if ahora - t < 10 else f"{p} (hace {L.hace(ahora - t)})"
                                                 for p, t in activas) or "ninguna en este momento",
                      "ok" if activas else None))
    if tunel:
        try:
            t = A.texto_panel()
        except Exception:
            t = None
        if t:
            filas.append(("App del trabajo", t, None))
    # IA y Whisper
    gen = _en("generando")
    e = E_IA["e"]
    if e == "caida":
        filas.append(("IA", "Ollama no responde: abrilo para poder generar informes", "error"))
    elif e == "sin_modelo":
        filas.append(("IA", f"Ollama no tiene el modelo {CFG['modelo_ia']}", "error"))
    else:
        filas.append(("IA", f"{CFG['modelo_ia']} · " + (f"armando el informe de «{titulo_de(gen[0])}»" if gen
                                                       else "lista, esperando"), "ok"))
    tr = _en("transcribiendo")
    filas.append(("Whisper", f"{CFG['modelo_whisper']} · " + (f"transcribiendo «{titulo_de(tr[0])}»" if tr
                                                              else "en espera (se carga cuando llega un audio)"),
                  "ok" if tr else None))
    g = _PANEL["gpu"]
    filas.append(("Placa de video", g[0] if g else ("simulada" if SIMULAR else "sin datos (nvidia-smi no responde)"),
                  g[1] if g else None))
    # casos
    k = _PANEL["casos"] or {}
    proc = en_proceso()
    partes = [f"{k.get('listo', 0)} para revisar", f"{k.get('nuevo', 0)} sin procesar", f"{proc} en proceso"]
    if k.get("error"):
        partes.append(f"{k['error']} con error")
    filas.append(("Casos", " · ".join(partes), "error" if k.get("error") else ("aviso" if k.get("nuevo") else None)))
    h = L.HOY
    filas.append(("Hoy", f"{L.plural(h['recibidos'], 'audio recibido', 'audios recibidos')} · "
                         f"{L.plural(h['generados'], 'informe', 'informes')} · "
                         f"{L.plural(h['guardados'], 'guardado')} · {L.plural(h['errores'], 'error', 'errores')}",
                  "aviso" if h["errores"] else None))
    filas.append(("Registro", f"{L.ruta_corta(L.CARPETA)}{os.sep} (un archivo por día + actividad.csv)", None))
    return filas


def main():
    titulo = M.titulo_consola()          # antes de que el servidor cambie el título de la ventana
    L.configurar()
    srv = None
    for intento in range(6):             # al reiniciar desde el panel, Windows puede tardar un instante en soltar el puerto
        try:
            srv = Servidor(("127.0.0.1", PUERTO), H)
            break
        except OSError:
            if intento == 5:
                L.error("SERVIDOR", f"No se pudo abrir el puerto {PUERTO}: seguramente el servidor ya está abierto en "
                                    f"otra ventana. Usá esa ventana o cerrala y volvé a abrir esta.", exc=True)
                sys.exit(1)
            time.sleep(1)
    SRV["http"] = srv
    R.cargar_sesiones()
    try:
        reanudar_cola()
    except Exception:
        L.error('COLA', 'No se pudo recuperar la cola. No se inicia procesamiento ni se aceptan audios; conservá la base y los archivos.', exc=True)
        srv.server_close()
        return 1
    M.empezar(titulo)
    url = f"http://127.0.0.1:{PUERTO}"
    tunel = "--tunel" in sys.argv
    TUNEL["modo"] = tunel
    e_ia = estado_ia()
    E_IA["e"] = e_ia
    _IA_CACHE.update(t=time.time(), ok=e_ia != "caida")
    L.encabezado("TRANSCRIPCIÓN DE INFORMES  ·  SERVIDOR", f"versión {VERSION}",
                 lambda: filas_encabezado(url, tunel),
                 "Eventos · no cierres esta ventana · Ctrl+C apaga · historial completo en registros")
    L.estado(ia=e_ia == "ok", cola=0)
    cargar_tiempos()
    APRENDIZAJE.iniciar()
    threading.Thread(target=trabajador, daemon=True, name="procesamiento").start()
    threading.Thread(target=vigilar_ia, args=(e_ia,), daemon=True, name="vigilancia-ia").start()
    threading.Thread(target=hilo_voces, daemon=True, name="voces").start()
    g = M.git_al_arrancar() or {}
    L.ok("SERVIDOR", f"Servidor iniciado en {url}" + ("" if e_ia == "ok" else " (sin IA hasta que se abra Ollama)")
         + (f" · código {g['commit']}" + (f" + {L.plural(len(g['sucios']), 'cambio')} sin commitear" if g.get("sucios") else "")
            if g.get("commit") else ""))
    if tunel:
        if not R.configurado():
            L.aviso("TÚNEL", f"Todavía no hay contraseña para el acceso remoto: ejecutá {P.script('configurar_acceso')}. "
                             "Por ahora el sistema funciona solo en esta PC.")
        else:
            abrir_tunel()
    if "--sin-navegador" not in sys.argv:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    if not P.ES_WINDOWS:     # Linux: "kill" o "systemctl stop" apagan en orden, igual que Ctrl+C
        import signal

        def _apagar(*_):
            raise KeyboardInterrupt
        signal.signal(signal.SIGTERM, _apagar)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    L.cerrar_encabezado()
    R.cerrar_tunel()
    if TUNEL["http"]:
        try:
            TUNEL["http"].shutdown()         # primero que deje de atender; si no, server_close tira WinError 10038
            TUNEL["http"].server_close()
        except Exception:
            pass
    try:
        srv.server_close()
    except Exception:
        pass
    h = L.HOY
    if SRV["salida"] == M.CODIGO_REINICIO:
        L.info("SERVIDOR", "Servidor cerrado para reiniciarse: se vuelve a abrir solo en esta misma ventana.")
        _salir_para_reiniciar()
    L.info("SERVIDOR", f"Servidor apagado. Hoy: {L.plural(h['recibidos'], 'audio recibido', 'audios recibidos')}, "
                       f"{L.plural(h['generados'], 'informe generado', 'informes generados')}, "
                       f"{L.plural(h['guardados'], 'guardado')}, {L.plural(h['errores'], 'error', 'errores')}.")


if __name__ == "__main__":
    sys.exit(main() or 0)
