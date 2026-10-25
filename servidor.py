# -*- coding: utf-8 -*-
"""
INTERFAZ WEB. Se abre con interfaz.bat (solo esta PC) o con iniciar_servidor.bat
(esta PC + las PC del trabajo por el tunel rapido de Cloudflare).
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
import estadisticas as EST
import app_cliente as A
import nucleo as N
import paciente as PAC
import registro as L
import remoto as R
from informe import config, escribir_docx, parrafos_docx, pagina, aplicar_formato, texto_parrafo, EXT_AUDIO

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

AQUI = Path(__file__).resolve().parent
WEB = AQUI / "web"
PUERTO = int(os.environ.get("PUERTO_INTERFAZ", "8765"))
CFG = config()
NUEVOS = CFG["carpeta_audios_nuevos"]
INFORMES = CFG["carpeta_informes"]
DATOS = INFORMES / "revision" / "datos"
for d in (NUEVOS, DATOS):
    d.mkdir(parents=True, exist_ok=True)

SIMULAR = os.environ.get("SIMULAR_IA") == "1"   # solo para pruebas
VERSION = "2026.10.24"
LOCAL = "Servidor"    # nombre con el que aparecen los casos subidos en esta misma PC
# páginas del panel de administración (solo en esta PC); cada una se abre en su pestaña del navegador
PAGINAS_ADMIN = {"/admin": "admin.html", "/admin/estadisticas": "estadisticas.html"}
FIN_LOCK = threading.Lock()
INICIO = time.time()
TUNEL = {"modo": False, "exe": AQUI / "cloudflared.exe"}     # "modo": se abrió con iniciar_servidor.bat (--tunel)
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


def mmss(t):
    return f"{int(t // 60)}:{int(t % 60):02d}"


def poner_estado(nombre, estado, msg=""):
    with LOCK:
        ESTADO[nombre] = {"estado": estado, "msg": msg, "t": time.time()}
    L.estado(cola=en_proceso())


EN_PROCESO = ("en cola", "transcribiendo", "generando")
ENCOLADO = {}         # nombre -> cuándo entró a la cola (para el orden y la espera estimada)
DURACION = {}         # nombre -> duración del audio en segundos (cache)
BORRADOS = set()      # casos borrados mientras esperaban en la cola: el trabajador los saltea
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
            "estudios": estudios_de(n)}


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


COLOR_TIPO = {"numero": "rojo", "completar": "rojo", "dudoso": "amarillo", "bajaconf": "amarillo",
              "verificar": "turq", "plantilla": "gris"}


def resumen_avisos(n, m):
    """Cuántas marcas de cada color quedan y qué datos faltan (para la lista y el modo compacto).
    Si hay borrador se cuentan las marcas que siguen en él (las ya revisadas no cuentan)."""
    r = {"rojo": 0, "amarillo": 0, "turq": 0, "gris": 0, "faltan": [], "huecos": []}
    bor = DATOS / f"{n}.borrador.html"
    if bor.exists():
        h = bor.read_text(encoding="utf-8")
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
    okf = DATOS / f"{n}.omisiones_ok.json"
    ok = set(json.loads(okf.read_text(encoding="utf-8"))) if okf.exists() else set()
    for o in m.get("omisiones", []):
        if o["dato"] in ok:
            continue
        if o.get("hueco"):
            r["huecos"].append(mmss(o.get("ini", o.get("seg") or 0)))
        else:
            r["faltan"].append(o["dato"])
    return r


def listar_casos(pc=LOCAL, remoto=False):
    nombres = {p.stem: p for p in NUEVOS.iterdir() if p.suffix.lower() in EXT_AUDIO}
    for f in DATOS.glob("*.informe_ia.txt"):
        nombres.setdefault(f.name[:-len(".informe_ia.txt")], None)
    casos = []
    esp = esperas()
    for n in nombres:
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
                m = json.loads(mf.read_text(encoding="utf-8"))
                marcas = m.get("total")
                if not revisado:
                    avisos = resumen_avisos(n, m)
            except (ValueError, OSError):
                pass
        a = ruta_audio(n)
        casos.append({"nombre": n, "estado": est["estado"], "msg": est.get("msg", ""), "marcas": marcas,
                      "medico": medico_de(n), "origen": origen_de(n), "avisos": avisos, "bloqueado_por": R.bloqueado_por(n, pc),
                      "titulo": titulo_de(n), "espera": esp.get(n), "paciente": PAC.de(DATOS, n),
                      "estudios": estudios_de(n) if listo else None, "dur": duracion_de(n),
                      "puede_borrar": not (remoto and (origen_de(n) != pc or pc == LOCAL))
                                      and est["estado"] not in ("transcribiendo", "generando"),
                      "fecha": (a.stat().st_mtime if a else (DATOS / f"{n}.informe_ia.txt").stat().st_mtime)})
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
    (DATOS / f"{n}.marcas.json").write_text(json.dumps({"v": VERSION_MARCAS, "lineas": lineas, "omisiones": om, "estudios_nuevos": nuevos,
                                                       "total": total + len(om)}, ensure_ascii=False), encoding="utf-8")
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
    okf = DATOS / f"{nombre}.omisiones_ok.json"
    om_ok = json.loads(okf.read_text(encoding="utf-8")) if okf.exists() else []
    bor = DATOS / f"{nombre}.borrador.html"
    fin = DATOS / f"{nombre}.final.txt"
    # cada palabra con su forma normalizada ("veintitrés" -> "23"), para ubicar cada línea del informe en el dictado
    palabras = [dict(w, n=re.sub(r"[^a-z0-9.]", "", N.normalizar(w["p"])).strip(".")) for w in trans["palabras"]]
    return {"nombre": nombre, "dictado": trans["texto"], "palabras": palabras, "lineas": lineas,
            "omisiones": om, "omisiones_ok": om_ok, "medico": medico_de(nombre),
            "paciente": PAC.de(DATOS, nombre), "titulo": titulo_de(nombre),
            "estudios": estudios_de(nombre), "dur": duracion_de(nombre),
            "estudios_nuevos": N.estudios_sin_plantilla(ia.read_text(encoding="utf-8")),
            "borrador": bor.read_text(encoding="utf-8") if bor.exists() else None,
            "revisado": fin.exists(), "tiene_audio": ruta_audio(nombre) is not None}


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
def trabajador():
    whisper = None
    while True:
        lote = [COLA.get()]
        time.sleep(0.5)
        while not COLA.empty():
            lote.append(COLA.get())
        lote = list(dict.fromkeys(lote))
        trans, info = {}, {}
        etapa = "WHISPER"
        if len(lote) > 1:
            L.info("WHISPER", f"Procesando {len(lote)} audios juntos: primero se transcriben todos y "
                              f"después la IA arma los informes.")
        try:
            # 1) Whisper para todo el lote
            if not SIMULAR:
                N.liberar_ia(CFG["modelo_ia"])
            lote = [n for n in lote if n not in BORRADOS]
            for n in lote:
                if n in BORRADOS:
                    continue
                a = ruta_audio(n)
                if a is None:
                    poner_estado(n, "error", "No encuentro el audio")
                    L.error("AUDIO", f"{visible(n)}: no encuentro el archivo de audio (¿se borró o se movió?).")
                    L.actividad("error", **datos_csv(n), detalle="No encuentro el audio")
                    continue
                if not empezar(n, "transcribiendo", "Transcribiendo el audio…"):
                    continue
                t0 = time.time()
                recuperadas = 0
                if SIMULAR:
                    of = DATOS / f"{n}.original.txt"
                    fuente = Path(of.read_text(encoding="utf-8").strip()).stem if of.exists() else n
                    trans[n] = json.loads((AQUI / "resultados" / "fase1" / "json" / f"{fuente}.json")
                                          .read_text(encoding="utf-8"))["con_vocab"]
                    trans[n]["huecos"] = json.loads(os.environ.get("SIMULAR_HUECOS", "[]"))
                    time.sleep(float(os.environ.get("SIMULAR_DEMORA", "0")))
                else:
                    if whisper is None:
                        from fase1_transcribir import cargar_modelo
                        poner_estado(n, "transcribiendo", "Cargando Whisper…")
                        L.info("WHISPER", f"Cargando Whisper {CFG['modelo_whisper']} en la placa de video…")
                        tc = time.time()
                        with contextlib.redirect_stdout(L.SalidaAlRegistro("WHISPER")):
                            whisper = cargar_modelo(CFG["modelo_whisper"], "cuda")
                        L.ok("WHISPER", f"Whisper cargado en {L.seg(time.time() - tc)}.")
                        poner_estado(n, "transcribiendo", "Transcribiendo el audio…")
                        t0 = time.time()
                    from fase1_transcribir import transcribir, leer_vocabulario, cargar_audio, VOCAB_DEF
                    import huecos as H
                    prompt = leer_vocabulario(VOCAB_DEF)
                    t = transcribir(whisper, a, prompt)
                    poner_estado(n, "transcribiendo", "Revisando partes que Whisper pudo saltear…")
                    pal, pend = H.reparar(whisper, cargar_audio(a), t["palabras"], prompt)
                    recuperadas = max(0, len(pal) - len(t["palabras"]))
                    trans[n] = {"texto": H.texto_de(pal), "palabras": pal, "huecos": pend}
                (DATOS / f"{n}.json").write_text(json.dumps(trans[n], ensure_ascii=False, indent=1), encoding="utf-8")
                (DATOS / f"{n}.dictado.txt").write_text(trans[n]["texto"], encoding="utf-8")
                PAC.calcular(DATOS, n, forzar=True)      # nombre del paciente para la lista (no va al informe)
                (DATOS / f"{n}.audio.txt").write_text(str(a.resolve()), encoding="utf-8")
                dur = duracion_wav(ruta=a)
                if dur is None and trans[n]["palabras"]:
                    dur = trans[n]["palabras"][-1].get("fin")
                info[n] = {"dur": dur, "whisper": time.time() - t0, "palabras": len(trans[n]["palabras"])}
                partes = [f"audio {L.mmss(dur)}" if dur else None, L.plural(info[n]["palabras"], "palabra")]
                if recuperadas:
                    partes.append(f"la segunda pasada recuperó {L.plural(recuperadas, 'palabra')}")
                L.ok("WHISPER", f"{visible(n)} transcrito en {L.seg(info[n]['whisper'])} · "
                                + " · ".join(x for x in partes if x))
                for h in trans[n].get("huecos") or []:
                    L.aviso("WHISPER", f"{visible(n)}: posible parte no transcrita entre {mmss(h['ini'])} y "
                                       f"{mmss(h['fin'])}. Revisarla escuchando.")
                poner_estado(n, "en cola", "Esperando a la IA…")
            if whisper is not None:      # liberar la placa para la IA
                del whisper
                whisper = None
                gc.collect()
                L.debug("WHISPER", "Whisper liberado de la placa de video.")
            # 2) IA
            etapa = "IA"
            banco = N.cargar_banco()
            for n in trans:
                if n in BORRADOS:
                    continue
                esperar_ia(n, list(trans))
                if not empezar(n, "generando", "La IA está armando el informe…"):
                    continue
                t0 = time.time()
                tokens = ""
                dic = trans[n]["texto"]
                if SIMULAR:
                    of = DATOS / f"{n}.original.txt"
                    fuente = Path(of.read_text(encoding="utf-8").strip()).stem if of.exists() else n
                    salida = (AQUI / "resultados" / "fase2" / "gemma4_12b" / f"{fuente}.json")
                    salida = json.loads(salida.read_text(encoding="utf-8"))["salida"]
                    time.sleep(float(os.environ.get("SIMULAR_DEMORA", "0")))
                else:
                    med = medico_de(n) or None
                    ej = N.elegir_ejemplos(dic, banco, k=CFG["ejemplos_por_informe"], excluir=n, medico=med)
                    salida, _, t_in, t_out = N.llamar_ia(CFG["modelo_ia"], N.armar_mensajes(dic, ej, med))
                    tokens = f"{t_in or '?'} tokens de entrada, {t_out or '?'} de salida"
                (DATOS / f"{n}.informe_ia.txt").write_text(salida, encoding="utf-8")
                for viejo in (f"{n}.marcas.json", f"{n}.borrador.html", f"{n}.final.txt", f"{n}.formato.json"):
                    (DATOS / viejo).unlink(missing_ok=True)
                (DATOS / f"{n}.omisiones_ok.json").unlink(missing_ok=True)
                lineas, om = guardar_marcas(n, salida, dic, trans[n]["palabras"], trans[n].get("huecos"))
                poner_estado(n, "listo")
                ia_s = time.time() - t0
                if not SIMULAR:
                    anotar_tiempo(info.get(n, {}).get("dur"), info.get(n, {}).get("whisper"), ia_s)
                r = resumen_avisos(n, {"lineas": lineas, "omisiones": om})
                nuevos = N.estudios_sin_plantilla(salida)
                L.contar("generados")
                med = medico_de(n)
                det = []
                if r["faltan"]:
                    det.append("Dictado pero no está en el informe: " + ", ".join(r["faltan"]))
                if tokens:
                    L.debug("IA", f"{visible(n)}: {tokens}")
                L.ok("IA", f"{visible(n)} informe listo en {L.seg(ia_s)}"
                           + (f" · {med}" if med else " · sin médico elegido") + f" · {texto_marcas(r)}", det)
                for e in nuevos:
                    L.aviso("IA", f"{visible(n)}: estudio sin plantilla «{e}». Conviene crearla desde Plantillas.")
                L.actividad("generado", **datos_csv(n), duracion_audio_s=info.get(n, {}).get("dur"),
                            whisper_s=info.get(n, {}).get("whisper"), ia_s=ia_s,
                            palabras_dictado=info.get(n, {}).get("palabras"),
                            marcas_rojas=r["rojo"], marcas_amarillas=r["amarillo"], marcas_turquesa=r["turq"],
                            marcas_grises=r["gris"], datos_faltantes=" ".join(r["faltan"]),
                            partes_no_transcritas=" ".join(r["huecos"]), estudios_sin_plantilla=" | ".join(nuevos))
        except Exception as ex:
            msg = mensaje_amigable(ex)
            afectados = [n for n in lote if ESTADO.get(n, {}).get("estado") not in ("listo", "error")
                         and n not in BORRADOS]
            L.error(etapa, f"No se pudo procesar {', '.join(visible(n) for n in afectados) or 'el lote'}: {msg}",
                    exc=True)
            for n in afectados:
                poner_estado(n, "error", msg)
                L.actividad("error", **datos_csv(n), detalle=f"{etapa}: {msg}")
        if not en_proceso() and COLA.empty():
            L.debug("SERVIDOR", "Cola vacía.")


def esperar_ia(n, lote):
    """Si Ollama está cerrado (o sin el modelo), el audio ya transcrito espera en la cola en vez de
    terminar con error: se sigue solo cuando la IA vuelve. Revisa cada 5 s."""
    avisado = False
    while True:
        e = estado_ia()
        if e == "ok":
            if avisado:
                L.ok("IA", f"La IA volvió: sigo con {visible(n)}.")
            return
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


def encolar(nombre):
    with LOCK:
        BORRADOS.discard(nombre)
    ENCOLADO[nombre] = time.time()
    DURACION.pop(nombre, None)
    poner_estado(nombre, "en cola", "En cola…")
    COLA.put(nombre)


# ---------------------------------------------------------------- borrar
# Archivos de un caso en la carpeta datos. Lista explícita: un caso «tmp9177» no debe llevarse
# los de otro llamado «tmp9177.tmp».
SUFIJOS_CASO = (".json", ".dictado.txt", ".informe_ia.txt", ".marcas.json", ".borrador.html", ".final.txt",
                ".medico.txt", ".audio.txt", ".ejemplo.txt", ".onda.json", ".origen.txt", ".original.txt",
                ".paciente.json", ".formato.json", ".omisiones_ok.json", ".revision.json")


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
        or any((DATOS / f"{n}{s}").exists() for s in SUFIJOS_CASO)
    if not hay:
        return "Ese informe ya no existe."
    with LOCK:      # que el trabajador no lo empiece justo ahora
        if ESTADO.get(n, {}).get("estado") in ("transcribiendo", "generando"):
            return "Se está procesando ahora: esperá a que termine para borrarlo."
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
        with LOCK:
            BORRADOS.discard(n)
        if previo.get("estado") == "en cola":      # el trabajador pudo haberlo salteado: vuelve a la cola
            encolar(n)
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
    with LOCK:
        ESTADO.pop(n, None)
    for d in (ENCOLADO, DURACION, _ESTUDIOS):
        d.pop(n, None)
    L.estado(cola=en_proceso())
    L.info("CASO", f"{quien} borró {nombre_vis} ({estado}): audio, informe y Word. "
                   f"Lo que aprendió la IA se conserva.")
    return None


# ------------------------------------------------------------- finalizar
def finalizar(nombre, texto, quien=LOCAL):
    with FIN_LOCK:      # varias PC pueden guardar a la vez: ejemplos e historial de a uno
        return _finalizar(nombre, texto, quien)


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


def vista_previa(texto, nombre=None):
    """Párrafos exactamente como quedan en el Word (mismo código que escribir_docx) + la hoja.
    b / a0 = negrita y alineación normales; a / r = con el formato elegido a mano (si hay)."""
    _, marcado = texto_a_marcado(texto)
    pars = parrafos_docx(marcado, CFG)
    if nombre:
        aplicar_formato(pars, formato_de(nombre))
    pars = [None if p is None else {"t": texto_parrafo(p), "b": p["negrita"], "a0": p["alin_def"],
                                    "a": p["alin"], "r": p.get("runs")}
            for p in pars]
    return {"parrafos": pars, "pagina": pagina(CFG), "fuente": CFG["fuente"], "tamano": CFG["tamano_fuente"],
            "encabezado": int(CFG["lineas_vacias_para_encabezado"])}


def _finalizar(nombre, texto, quien=LOCAL):
    from aprender import registrar_ejemplo, anotar_procesado
    final, marcado = texto_a_marcado(texto)
    docx = escribir_docx(marcado, INFORMES / f"{nombre}.docx", CFG, formato_de(nombre))
    ia = (DATOS / f"{nombre}.informe_ia.txt").read_text(encoding="utf-8")
    dic = (DATOS / f"{nombre}.dictado.txt").read_text(encoding="utf-8")
    fin_f = DATOS / f"{nombre}.final.txt"
    ya_guardado = fin_f.exists()
    clave = None
    reg = DATOS / f"{nombre}.ejemplo.txt"
    if reg.exists():
        clave = reg.read_text(encoding="utf-8").strip()
    clave, pc = registrar_ejemplo(nombre, dic, ia, final, clave, medico=medico_de(nombre) or None)
    reg.write_text(clave, encoding="utf-8")
    fin_f.write_text(final, encoding="utf-8")
    try:
        anotar_procesado(docx, clave)
    except Exception:
        L.debug("INFORME", f"No se pudo anotar {docx.name} como procesado", det=[repr(sys.exc_info()[1])])
    L.contar("guardados")
    rev = revision_de(nombre)
    L.ok("INFORME", f"{visible(nombre)} {'guardado de nuevo' if ya_guardado else 'guardado'} por {quien} · "
                    f"{f'{pc * 100:.1f}'.replace('.', ',')}% corregido"
                    + (f" · revisión {mmss(rev)}" if rev else "") + f" · Word {docx.name} · ejemplo aprendido")
    L.actividad("guardado", **datos_csv(nombre), porcentaje_corregido=pc * 100, palabras_informe=len(final.split()),
                revision_s=rev, detalle=("guardado de nuevo" if ya_guardado else "guardado") + f" desde {quien}")
    EST.invalidar()
    return {"docx": str(docx), "pct": round(pc * 100, 1)}


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

    LIBRES = {"/entrar", "/api/cliente/vincular", "/favicon.ico", "/salir"}

    def _autorizar(self, ruta):
        """Pone self.pc y self.remoto. Devuelve False (y responde) si no tiene permiso."""
        self.remoto = self._es_remoto()
        if not self.remoto:
            self.pc = LOCAL
            return True
        self.pc = R.pc_de_llave(self._llave()) or R.pc_de_sesion(self._cookie("ts"))
        if self.pc:
            VISTO[self.pc] = time.time()
            R.anotar_visto(self.pc, A.VERSION_PC.get(self.pc))
        if self.pc or ruta in self.LIBRES:
            return True
        if ruta not in ("/", "/index.html") and L.una_vez(("sin_sesion", self._ip()), 600):
            L.info("ACCESO", f"Pedido sin sesión desde la IP {self._ip()} ({ruta}): se le pide entrar.")
        if ruta.startswith("/api/") or ruta.startswith("/audio/"):
            self._json({"error": "Sesión vencida: volvé a entrar.", "entrar": True}, 401)
        else:
            self._redirigir("/entrar")
        return False

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

    def _pagina_entrar(self, error=""):
        err = f'<p class="err">{error}</p>' if error else ""
        self._html(PAGINA_ENTRAR.replace("{{error}}", err), 401 if error else 200)

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(u.query)
        if not self._autorizar(u.path):
            return
        if u.path == "/entrar":
            cod = q.get("codigo", [""])[0]
            sid = R.canjear_codigo(cod)
            if sid:
                L.info("ACCESO", f"{R.pc_de_sesion(sid)} abrió la aplicación (IP {self._ip()}).")
                return self._redirigir("/", R.cookie_sesion(sid))
            if cod:
                L.aviso("ACCESO", f"Código de entrada vencido o inválido desde la IP {self._ip()}.")
            return self._pagina_entrar()
        if u.path == "/salir":
            quien = R.pc_de_sesion(self._cookie("ts"))
            if quien:
                L.info("ACCESO", f"{quien} cerró la sesión.")
            R.cerrar_sesion(self._cookie("ts"))
            return self._redirigir("/entrar", "ts=; Path=/; Max-Age=0; HttpOnly; Secure; SameSite=Lax")
        if u.path in ("/", "/index.html"):
            self._html((WEB / "index.html").read_bytes())
        elif u.path in PAGINAS_ADMIN or u.path.startswith("/api/admin/"):
            acc = ADM.acceso(self, PUERTO)
            if acc is None:
                return self._panel_sin_permiso(u.path)
            visor = {"remoto": acc == "remoto", "pc": self.pc if acc == "remoto" else None}
            if u.path in PAGINAS_ADMIN:
                self._html((WEB / PAGINAS_ADMIN[u.path]).read_bytes())
            elif u.path == "/api/admin/estado":
                self._json(dict(estado_admin(), visor=visor))
            elif u.path == "/api/admin/estadisticas":
                q = urllib.parse.parse_qs(u.query)
                try:
                    dias = int((q.get("dias") or ["30"])[0])
                except ValueError:
                    dias = 30
                self._json(dict(EST.calcular(dias, medico_actual=medico_de, estudios_actual=estudios_de), visor=visor))
            else:
                self.send_error(404)
        elif u.path == "/api/mi_pc":
            self._json({"pc": self.pc, "remoto": self.remoto, "medico": R.medico_pc(self.pc),
                        "admin": (not self.remoto) or R.admin_configurado()})   # si se muestra el engranaje del panel
        elif u.path == "/api/cliente/estado":
            casos = [{"nombre": c["nombre"], "titulo": c["titulo"], "estado": c["estado"], "marcas": c["marcas"],
                      "paciente": c["paciente"]}
                     for c in listar_casos(self.pc) if c["origen"] == self.pc][:40]
            cola = sum(1 for c in listar_casos(self.pc) if c["estado"] in ("en cola", "transcribiendo", "generando"))
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
                        "modelo": CFG["modelo_ia"]})
        elif u.path == "/api/formato":
            self._json({"palabras_titulo": sorted(N.PALABRAS_ESTUDIO),
                        "negrita_titulos": CFG.get("negrita_titulos", True),
                        "prefijos": CFG.get("negrita_si_empieza_con", N.NEGRITA_DEF),
                        "exactas": CFG.get("negrita_lineas_exactas", N.NEGRITA_EXACTAS)})
        elif u.path == "/api/medicos":
            self._json({"medicos": [{"nombre": m, "notas": N.notas_medico(m)} for m in N.lista_medicos()]})
        elif u.path == "/api/plantillas":
            self._json({"secciones": [{"nombre": a, "cuerpo": b} for a, b in N.secciones_plantillas()[1]]})
        elif u.path == "/api/caso":
            n = q.get("nombre", [""])[0]
            c = cargar_caso(n) if self._nombre_valido(n) else None
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
            L.info("AUDIO", f"{self.pc} envió «{original}», que ya estaba cargado como {visible(previo)}. "
                            f"No se procesa de nuevo.")
            return {"ok": True, "nombre": previo, "duplicado": True}, None
        ext = Path(original).suffix.lower()
        nombre = R.nombre_unico(self.pc, original,
                                lambda n: any((NUEVOS / f"{n}{e}").exists() for e in EXT_AUDIO))
        (NUEVOS / f"{nombre}{ext}").write_bytes(cuerpo)
        (DATOS / f"{nombre}.origen.txt").write_text(self.pc, encoding="utf-8")
        (DATOS / f"{nombre}.original.txt").write_text(Path(original).name, encoding="utf-8")
        med = R.medico_pc(self.pc)
        if med:
            (DATOS / f"{nombre}.medico.txt").write_text(med, encoding="utf-8")
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
            if u.path == "/entrar":      # entrar desde un navegador común (sin la aplicación)
                f = urllib.parse.parse_qs(self._body(64 * 1024).decode("utf-8", "replace"))
                ip = self._ip()
                pc = (f.get("pc", [""])[0]).strip()
                if R.demasiados_fallos(ip):
                    L.aviso("ACCESO", f"Intento de entrar como «{pc[:24]}» desde la IP {ip} rechazado: "
                                      f"está bloqueada 10 minutos por contraseñas incorrectas.")
                    return self._pagina_entrar("Demasiados intentos fallidos. Esperá 10 minutos.")
                if not R.PC_VALIDA.match(pc):
                    return self._pagina_entrar("Escribí el nombre de esta PC (ej. info-01).")
                if not R.contrasena_ok(f.get("contrasena", [""])[0]):
                    R.anotar_fallo(ip)
                    self._avisar_fallo(pc, ip, "desde el navegador")
                    return self._pagina_entrar("Contraseña incorrecta.")
                L.ok("ACCESO", f"{pc} entró desde el navegador (IP {ip}).")
                return self._redirigir("/", R.cookie_sesion(R.nueva_sesion(pc)))
            if u.path == "/api/cliente/vincular":
                d = json.loads(self._body(64 * 1024) or b"{}")
                pc_nueva = str(d.get("pc", "")).strip()
                llave, err = R.vincular(pc_nueva, d.get("contrasena", ""), self._ip())
                if err:
                    if err.startswith("Contraseña"):
                        self._avisar_fallo(pc_nueva, self._ip(), "al vincular la aplicación")
                    else:
                        L.aviso("ACCESO", f"No se vinculó «{pc_nueva[:24]}» (IP {self._ip()}): {err}")
                    return self._json({"error": err}, 403)
                L.ok("ACCESO", f"PC vinculada: {pc_nueva} (IP {self._ip()}). Ya puede enviar audios.")
                return self._json({"ok": True, "llave": llave, "pc": d["pc"].strip(), "version": VERSION})
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
                destino.write_bytes(cuerpo)
                (DATOS / f"{destino.stem}.origen.txt").write_text(LOCAL, encoding="utf-8")
                med = q.get("medico", [""])[0].strip()
                if med:
                    (DATOS / f"{destino.stem}.medico.txt").write_text(med, encoding="utf-8")
                encolar(destino.stem)
                anunciar_audio(destino.stem, cuerpo, "en esta PC")
                return self._json({"ok": True, "nombre": destino.stem})
            datos = json.loads(self._body(20 * 1024 * 1024) or b"{}")
            if u.path == "/api/vista_previa":
                nv = datos.get("nombre") or None
                return self._json(vista_previa(str(datos.get("texto", "")),
                                               nv if nv and self._nombre_valido(nv) else None))
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
            if u.path == "/api/mi_medico":
                med = datos.get("medico", "").strip()
                if med != R.medico_pc(self.pc):
                    L.info("CONFIG", f"{self.pc} eligió médico para sus audios: {med or 'ninguno'}.")
                R.poner_medico_pc(self.pc, med)
                return self._json({"ok": True})
            if u.path == "/api/medico":
                nom = N.guardar_medico(datos.get("medico", ""), datos.get("notas", ""))
                L.ok("CONFIG", f"Notas del médico {nom} guardadas ({self.pc}).")
                return self._json({"ok": True, "medico": nom})
            if u.path == "/api/importar":
                from importar_informes import importar
                ok, mal = importar()
                L.ok("CONFIG", f"Importados {L.plural(len(ok), 'informe')} Word como referencia ({self.pc}).",
                     [f"No se pudieron leer: {', '.join(mal)}"] if mal else None)
                return self._json({"ok": ok, "mal": mal})
            if u.path == "/api/plantillas":
                secs = [(x.get("nombre", ""), x.get("cuerpo", "")) for x in datos.get("secciones", [])]
                if not secs:
                    return self._json({"error": "No hay plantillas para guardar"}, 400)
                N.guardar_secciones(secs)
                L.ok("CONFIG", f"Plantillas guardadas por {self.pc} ({L.plural(len(secs), 'estudio')}); "
                               f"la versión anterior quedó en conocimiento\\copias.")
                return self._json({"ok": True})
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
            if u.path == "/api/caso/bloquear":
                previo = R.BLOQUEOS.get(n)
                r = R.bloquear(n, self.pc)
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
            otro = R.bloqueado_por(n, self.pc)
            if otro and u.path in ("/api/borrador", "/api/finalizar", "/api/procesar", "/api/caso_medico", "/api/paciente",
                                       "/api/formato_caso", "/api/formato_caso/agregar"):
                if L.una_vez(("conflicto", n, self.pc), 120):
                    L.aviso("CASO", f"{self.pc} intentó modificar {visible(n)} mientras lo revisa {otro}; "
                                    f"no se guardó su cambio.")
                return self._json({"error": f"Este caso lo está revisando {otro}."}, 409)
            if u.path == "/api/caso_medico":
                med = datos.get("medico", "").strip()
                f = DATOS / f"{n}.medico.txt"
                if med:
                    f.write_text(med, encoding="utf-8")
                else:
                    f.unlink(missing_ok=True)
                L.info("CASO", f"{visible(n)}: médico cambiado a {med or 'ninguno'} ({self.pc}).")
                return self._json({"ok": True})
            if u.path == "/api/paciente":
                p = PAC.corregir(DATOS, n, datos.get("paciente", ""))
                L.info("CASO", f"{visible(n)}: nombre del paciente " + ("corregido a mano" if datos.get("paciente", "").strip()
                                                                       else "vuelto a sacar del dictado") + f" ({self.pc}).")
                return self._json({"ok": True, "paciente": p})
            if u.path == "/api/procesar":
                L.info("IA", f"{self.pc} pidió volver a generar {visible(n)}.")
                encolar(n)
                return self._json({"ok": True})
            if u.path == "/api/borrador":
                (DATOS / f"{n}.borrador.html").write_text(datos.get("html", ""), encoding="utf-8")
                if "omisiones_ok" in datos:
                    (DATOS / f"{n}.omisiones_ok.json").write_text(json.dumps(datos["omisiones_ok"]), encoding="utf-8")
                return self._json({"ok": True})
            if u.path == "/api/formato_caso":     # formato elegido a mano en la vista previa
                f = DATOS / f"{n}.formato.json"
                fm = datos.get("formato")
                if isinstance(fm, dict) and fm.get("parrafos"):
                    f.write_text(json.dumps(fm, ensure_ascii=False), encoding="utf-8")
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
                return self._json(finalizar(n, datos.get("texto", ""), self.pc))
            if u.path == "/api/abrir":
                p = INFORMES / f"{n}.docx"
                if p.exists() and os.name == "nt" and not self.remoto:
                    os.startfile(p)
                return self._json({"ok": p.exists()})
            self.send_error(404)
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
        if not ADM.mismo_origen(self, PUERTO):
            L.aviso("ACCESO", f"Pedido para entrar al panel desde {self.pc} rechazado: no vino de la página del panel (IP {ip}).")
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
    elif not t.get("iniciado"):
        e = "detenido"
    else:
        e = {"activo": "activo", "abriendo": "abriendo", "reconectando": "reconectando",
             "sin cloudflared": "sin_cloudflared"}.get(t.get("estado") or "", "abriendo")
        if e == "abriendo" and t.get("url"):
            e = "conectando"           # ya tiene dirección, falta que Cloudflare confirme la conexión
    return {"modo": TUNEL["modo"], "estado": e, "url": t.get("url"), "desde": t.get("desde"),
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
                     "registros": str(L.CARPETA)},
        "ia": {"estado": E_IA["e"], "modelo": CFG["modelo_ia"],
               "trabajando": f"armando el informe de «{titulo_de(gen[0])}»" if gen else None},
        "whisper": {"modelo": CFG["modelo_whisper"],
                    "trabajando": f"transcribiendo «{titulo_de(tr[0])}»" if tr else None},
        "gpu": gpu[0] if gpu else ("simulada (modo prueba)" if SIMULAR else None), "gpu_tono": gpu[1] if gpu else None,
        "casos": {**k, "en_proceso": en_proceso()},
        "hoy": dict(L.HOY),
        "tunel": estado_tunel(),
        "contrasena": R.configurado(),
        "admin_remoto": {"configurada": R.admin_configurado(), "desde": R.admin_desde(), "sesiones": R.sesiones_admin()},
        "app": {"version": oficial, "archivos": len(man.get("archivos", []))},
        "pcs": pcs,
        "registro": ADM.ultimos_eventos(),
    }


def accion_admin(accion, d, quien=None):
    """Botones del panel. Devuelve (respuesta, código). quien = PC del trabajo que usa el panel (None = esta PC)."""
    desde = f"desde el panel de administración (usado en {quien})" if quien else "desde el panel de administración"
    if quien and accion in SOLO_EN_EL_SERVIDOR:
        L.aviso("ACCESO", f"{quien} intentó «{accion}» en el panel de administración: solo se puede en la PC del servidor.")
        return {"error": "Eso solo se puede hacer en la PC del servidor."}, 403
    if accion == "tunel/reiniciar":
        err = R.reiniciar_tunel()
        if err:
            return {"error": err}, 409
        L.info("TÚNEL", f"Reinicio del túnel pedido {desde}.")
        return {"ok": True, "msg": "Túnel reiniciándose: en unos segundos tiene dirección nueva y se publica sola."}, 200
    if accion == "tunel/publicar":
        url = R.URL_TUNEL.get("url")
        if not url:
            return {"error": "Todavía no hay dirección para publicar."}, 409
        if not R.publicar_url(url):
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
            R.escribir_conexion_cliente()
            R.iniciar_tunel(PUERTO, TUNEL["exe"])
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
SOLO_EN_EL_SERVIDOR = {"abrir", "contrasena_admin", "contrasena_admin/quitar", "sesiones_admin/cerrar"}

PAGINA_PANEL_NO_HABILITADO = """<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Administración · Transcripción</title>
<style>:root{color-scheme:light dark}body{margin:0;min-height:100vh;display:grid;place-items:center;
font:15px/1.5 "Segoe UI",system-ui,sans-serif;background:Canvas;color:CanvasText}
div{max-width:440px;padding:24px}h1{font-size:19px;margin:0 0 8px}a{color:#1f5fbf}</style></head>
<body><div><h1>Panel no habilitado en el trabajo</h1><p>El panel de administración todavía no se puede abrir desde
las PC del trabajo. Para habilitarlo, en la PC del servidor abrí <b>http://127.0.0.1:8765/admin</b> y configurá
la <b>contraseña del panel desde el trabajo</b>.</p>
<p><a href="/">Volver a los informes</a></p></div></body></html>"""


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
a{color:var(--ac);font-size:13.5px;text-align:center}</style>
</head><body><form id="f" autocomplete="off"><h1>Panel de administración</h1>
<p>Estás en <b>{{pc}}</b>. Escribí la contraseña del panel: es distinta de la del acceso remoto y la configura
quien administra el servidor.</p>
<label>Contraseña del panel<input id="c" type="password" required autocomplete="off" autofocus></label>
<div class="err" id="err" role="alert"></div>
<button id="b">Entrar al panel</button><a href="/">Volver a los informes</a></form>
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
div{max-width:420px;padding:24px}h1{font-size:19px;margin:0 0 8px}a{color:#1f5fbf}</style></head>
<body><div><h1>Solo en la PC del servidor</h1><p>El panel de administración se abre únicamente en la PC donde
corre el servidor, en <b>http://127.0.0.1:8765/admin</b> (escribí exactamente esa dirección). Desde las PC del
trabajo se abre con el engranaje de la lista, si se habilitó con su contraseña.</p>
<p><a href="/">Volver a los informes</a></p></div></body></html>"""


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
</head><body><form method="post" action="/entrar"><h1>Transcripción</h1>
<p>Para usar el sistema desde esta PC escribí su nombre y la contraseña.</p>{{error}}
<label>Nombre de esta PC<input name="pc" placeholder="info-01" required autocomplete="username"></label>
<label>Contraseña<input name="contrasena" type="password" required autocomplete="current-password"></label>
<button>Entrar</button></form></body></html>"""


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
        tono = "aviso" if int(temp) >= 85 or int(usada) >= 0.97 * int(total) else None
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
        filas.append(("Acceso remoto", "apagado: solo esta PC (para el trabajo usá iniciar_servidor.bat)", None))
    elif not R.configurado():
        filas.append(("Acceso remoto", "falta la contraseña: ejecutá configurar_acceso.bat", "aviso"))
    elif R.URL_TUNEL.get("url"):
        desde = R.URL_TUNEL.get("desde")
        filas.append(("Acceso remoto", "túnel de Cloudflare activo" + (f" desde hace {L.hace(ahora - desde)}" if desde else ""), "ok"))
    else:
        filas.append(("Acceso remoto", "túnel abriéndose o reconectando…", "aviso"))
    if tunel and R.configurado():      # en su propio renglón, para que la dirección entre entera
        filas.append(("Dirección", R.URL_TUNEL.get("url") or "esperando a Cloudflare…", None))
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
    L.configurar()
    try:
        srv = Servidor(("127.0.0.1", PUERTO), H)
    except OSError:
        L.error("SERVIDOR", f"No se pudo abrir el puerto {PUERTO}: seguramente el servidor ya está abierto en "
                            f"otra ventana. Usá esa ventana o cerrala y volvé a abrir esta.", exc=True)
        sys.exit(1)
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
    threading.Thread(target=trabajador, daemon=True, name="procesamiento").start()
    threading.Thread(target=vigilar_ia, args=(e_ia,), daemon=True, name="vigilancia-ia").start()
    L.ok("SERVIDOR", f"Servidor iniciado en {url}" + ("" if e_ia == "ok" else " (sin IA hasta que se abra Ollama)"))
    if tunel:
        if not R.configurado():
            L.aviso("TÚNEL", "Todavía no hay contraseña para el acceso remoto: ejecutá configurar_acceso.bat. "
                             "Por ahora el sistema funciona solo en esta PC.")
        else:
            R.escribir_conexion_cliente()
            R.iniciar_tunel(PUERTO, TUNEL["exe"])
    if "--sin-navegador" not in sys.argv:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    L.cerrar_encabezado()
    R.cerrar_tunel()
    h = L.HOY
    L.info("SERVIDOR", f"Servidor apagado. Hoy: {L.plural(h['recibidos'], 'audio recibido', 'audios recibidos')}, "
                       f"{L.plural(h['generados'], 'informe generado', 'informes generados')}, "
                       f"{L.plural(h['guardados'], 'guardado')}, {L.plural(h['errores'], 'error', 'errores')}.")


if __name__ == "__main__":
    main()
