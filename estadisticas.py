# -*- coding: utf-8 -*-
"""
ESTADÍSTICAS para el panel de administración (pestaña "Estadísticas").

Une lo que ya se guarda:
- resultados\\historial.sqlite3: historial indexado; usa historial.csv cuando aún no se migró;
- registros\\actividad.csv    filas "generado" (marcas, duración del audio) y "guardado" (PC, médico, estudios,
                              tiempo de revisión); está desde el 24/10 a la noche;
- ejemplos\\                  el informe final y el médico de cada informe aprendido (para los informes viejos
                              que no tienen médico ni estudio en actividad.csv).
Un informe guardado varias veces cuenta una sola vez (vale el último guardado).
No escribe nada: solo lee.
"""
import csv
import io
import re
import statistics
import threading
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import nucleo as N
from transcripcion.aprendizaje import almacen as AL
from transcripcion.base import registro as L

AQUI = Path(__file__).resolve().parent
HIST = AQUI / "resultados" / "historial.csv"
EJ = AQUI / "ejemplos"
SIN_MEDICO = "Sin especificar"
SIN_ESTUDIO = "Sin estudio reconocido"
LOCAL = "Servidor"
_CACHE = {"firma": None, "t": 0, "informes": [], "generados": []}
_lock = threading.Lock()
_CLAVE_EJ = re.compile(r"^(\d{8}_\d{6})_(.+)\.informe\.txt$")
_PC_EN_NOMBRE = re.compile(r"^(.+?)_\d{8}-\d{6}_")


def invalidar():
    with _lock:
        _CACHE["firma"] = None


# --------------------------------------------------------------- lectura
def _num(v):
    if v is None:
        return None
    v = str(v).strip().replace(",", ".")
    if not v:
        return None
    try:
        return float(v)
    except ValueError:
        return None


def _leer_csv(f):
    try:
        return list(csv.DictReader(io.StringIO(f.read_text(encoding="utf-8-sig")), delimiter=";"))
    except (OSError, UnicodeDecodeError, csv.Error):
        return []


def _firma():
    def st(p):
        try:
            s = p.stat()
            return (s.st_size, s.st_mtime_ns)
        except OSError:
            return None
    return (st(L.CARPETA / "actividad.csv"), st(HIST), st(AL.ruta_base(HIST)), st(EJ))


def _indice_ejemplos():
    """nombre del caso -> clave del ejemplo más nuevo (20261024_191523_nombre)."""
    idx = {}
    try:
        nombres = sorted(p.name for p in EJ.iterdir())
    except OSError:
        return idx
    for nm in nombres:
        m = _CLAVE_EJ.match(nm)
        if m:
            idx[m.group(2)] = nm[:-len(".informe.txt")]      # ordenados: queda el último
    return idx


def _leer_txt(p):
    try:
        return p.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError):
        return ""


def _fecha(s):
    """'2026-10-24 17:36' o '2026-10-24 17:36:12' -> timestamp."""
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(s.strip(), fmt).timestamp()
        except (ValueError, AttributeError):
            pass
    return None


def _informes(actual):
    """Lista de informes guardados (uno por caso), del más viejo al más nuevo."""
    firma = _firma()
    with _lock:
        if _CACHE["firma"] == firma and time.time() - _CACHE["t"] < 60:
            return _CACHE["informes"]

    hist = {}
    for r in AL.leer_historial(HIST):
        n = (r.get("informe") or "").strip()
        t = _fecha(r.get("fecha") or "")
        if n and t:
            hist[n] = {"t": t, "palabras": _num(r.get("palabras")), "pct": _num(r.get("porcentaje_corregido"))}

    guard, gen = {}, {}
    for r in _leer_csv(L.CARPETA / "actividad.csv"):
        n = (r.get("caso") or "").strip()
        if not n:
            continue
        if r.get("evento") == "guardado":
            guard[n] = r
        elif r.get("evento") == "generado":
            gen[n] = r

    idx = _indice_ejemplos()
    salida = []
    for n in set(hist) | set(guard):
        h, g, ge = hist.get(n, {}), guard.get(n) or {}, gen.get(n)
        t = _fecha(f"{g.get('fecha', '')} {g.get('hora', '')}") if g else None
        t = t or h.get("t")
        if not t:
            continue
        clave = idx.get(n)
        medico = (g.get("medico") or "").strip()
        if not medico and clave:
            medico = _leer_txt(EJ / f"{clave}.medico.txt")
        if not medico:
            medico = actual["medico"](n) or ""
        estudios = (g.get("estudios") or "").strip()
        if not estudios and clave:
            estudios = N.estudios_del_informe(_leer_txt(EJ / f"{clave}.informe.txt")) or ""
        if not estudios:
            estudios = actual["estudios"](n) or ""
        m = _PC_EN_NOMBRE.match(n)
        pc = (g.get("pc") or "").strip() or (m.group(1) if m else LOCAL)
        titulo = (g.get("audio_original") or "").strip() or \
            (n[m.end():].replace("-", " ") if m else re.sub(r"\.tmp$", "", n))
        pct = _num(g.get("porcentaje_corregido"))
        if pct is None:
            pct = h.get("pct")
        palabras = _num(g.get("palabras_informe"))
        if palabras is None:
            palabras = h.get("palabras")
        marcas = None
        if ge:
            vals = [_num(ge.get(k)) for k in ("marcas_rojas", "marcas_amarillas", "marcas_turquesa", "marcas_grises")]
            if any(v is not None for v in vals):
                marcas = sum(v or 0 for v in vals)
        rev = _num(g.get("revision_s"))
        salida.append({
            "caso": n, "t": t, "titulo": titulo, "pc": pc, "medico": medico or SIN_MEDICO,
            "estudios": estudios or SIN_ESTUDIO, "pct": pct, "palabras": palabras,
            "rev": rev if rev and rev > 0 else None, "marcas": marcas,
            "dur": _num(ge.get("duracion_audio_s")) if ge else None,
            "voz_estado": (g.get("voz_estado") or "").strip(), "voz_medico": (g.get("medico_voz") or "").strip(),
            "voz_puntaje": _num(g.get("voz_puntaje")),
        })
    salida.sort(key=lambda x: x["t"])
    generados = []
    for r in _leer_csv(L.CARPETA / "actividad.csv"):
        if r.get("evento") not in ("generado", "error"):
            continue
        t = _fecha(f"{r.get('fecha', '')} {r.get('hora', '')}")
        if not t:
            continue
        n = (r.get("caso") or "").strip()
        m = _PC_EN_NOMBRE.match(n)
        generados.append({"t": t, "evento": r.get("evento"), "caso": n,
                          "titulo": (r.get("audio_original") or "").strip() or (n[m.end():].replace("-", " ") if m else n),
                          "pc": (r.get("pc") or "").strip() or (m.group(1) if m else LOCAL),
                          "medico": (r.get("medico") or "").strip(), "dur": _num(r.get("duracion_audio_s")),
                          "whisper": _num(r.get("whisper_s")), "ia": _num(r.get("ia_s")),
                          "detalle": (r.get("detalle") or "").strip()[:200]})
    generados.sort(key=lambda x: x["t"])
    with _lock:
        _CACHE.update(firma=firma, t=time.time(), informes=salida, generados=generados)
    return salida


# --------------------------------------------------------------- cálculo
def _prom(xs):
    xs = [x for x in xs if x is not None]
    return round(sum(xs) / len(xs), 1) if xs else None


def _mediana(xs):
    xs = [x for x in xs if x is not None]
    return round(statistics.median(xs), 1) if xs else None


def _resumen(lista):
    pcts = [i["pct"] for i in lista]
    revs = [i["rev"] for i in lista if i["rev"]]
    corr = sum((i["pct"] or 0) / 100 * (i["palabras"] or 0) for i in lista)
    return {
        "n": len(lista),
        "pct": _prom(pcts), "pct_mediana": _mediana(pcts),
        "palabras": int(sum(i["palabras"] or 0 for i in lista)),
        "corregidas": int(round(corr)),
        "rev_n": len(revs), "rev_prom": _prom(revs), "rev_mediana": _mediana(revs),
        "rev_total": int(round(sum(revs))),
        "marcas": _prom([i["marcas"] for i in lista]),
        "audio_prom": _prom([i["dur"] for i in lista]),
    }


def medida_trabajo(lista):
    """Con qué se mide "cuánto trabajo da": el tiempo de revisión si está medido en casi todos los informes
    del período (80 %); si no (informes de antes de que se midiera), las palabras que hubo que corregir."""
    n = len(lista)
    return "tiempo" if n and sum(1 for i in lista if i["rev"]) >= 0.8 * n else "corregidas"


def _por(lista, clave, medida):
    grupos = {}
    for i in lista:
        grupos.setdefault(i[clave], []).append(i)
    filas = [dict(_resumen(g), nombre=k) for k, g in grupos.items()]
    campo = "rev_total" if medida == "tiempo" else "corregidas"
    tot = sum(f[campo] for f in filas)
    for f in filas:
        f["parte"] = round(100 * f[campo] / tot, 1) if tot else None
    # más trabajo primero
    filas.sort(key=lambda f: (-f[campo], -f["rev_total"], -f["corregidas"], -f["n"], f["nombre"].lower()))
    return filas


def _lunes(t):
    d = date.fromtimestamp(t)
    return d - timedelta(days=d.weekday())


def _semanas(lista, desde, hasta):
    if not lista:
        return []
    grupos = {}
    for i in lista:
        grupos.setdefault(_lunes(i["t"]), []).append(i)
    ini = _lunes(desde) if desde else min(grupos)
    fin = _lunes(hasta)
    ini = max(ini, fin - timedelta(weeks=25))         # como mucho 26 semanas en el gráfico
    filas, d = [], ini
    while d <= fin:
        g = grupos.get(d, [])
        filas.append(dict(_resumen(g), desde=d.isoformat(), hasta=(d + timedelta(days=6)).isoformat()))
        d += timedelta(weeks=1)
    return filas


# ------------------------------------------------- tiempos de procesamiento
def _pctl(xs, q):
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return None
    k = (len(xs) - 1) * q
    i = int(k)
    return round(xs[i] + (xs[min(i + 1, len(xs) - 1)] - xs[i]) * (k - i), 1)


def _resumen_tiempos(lista):
    ok = [g for g in lista if g["evento"] == "generado"]
    w = [g["whisper"] for g in ok if g["whisper"]]
    ia = [g["ia"] for g in ok if g["ia"]]
    fx = [g["whisper"] / g["dur"] for g in ok if g["whisper"] and g["dur"] and g["dur"] > 1]
    tot = [(g["whisper"] or 0) + (g["ia"] or 0) for g in ok if g["whisper"] or g["ia"]]
    return {"n": len(ok), "errores": sum(1 for g in lista if g["evento"] == "error"),
            "whisper_prom": _prom(w), "whisper_mediana": _mediana(w),
            "whisper_x": round(statistics.median(fx), 3) if fx else None,          # segundos por segundo de audio
            "ia_prom": _prom(ia), "ia_mediana": _mediana(ia), "ia_p90": _pctl(ia, 0.9),
            "total_prom": _prom(tot), "total_mediana": _mediana(tot),
            "audio_prom": _prom([g["dur"] for g in ok])}


def tiempos(desde, dias, ahora):
    """Cuánto tardan Whisper y la IA en los informes generados del período (de actividad.csv)."""
    with _lock:
        todos = list(_CACHE["generados"])
    lista = [g for g in todos if desde is None or g["t"] >= desde]
    previo = None
    if dias:
        ant = [g for g in todos if desde - dias * 86400 <= g["t"] < desde]
        if any(g["evento"] == "generado" for g in ant):
            previo = _resumen_tiempos(ant)
    ok = [g for g in lista if g["evento"] == "generado" and (g["whisper"] or g["ia"])]
    res = _resumen_tiempos(lista)
    med_ia, med_x = res["ia_mediana"], res["whisper_x"]
    lentos = []
    for g in sorted(ok, key=lambda g: -((g["whisper"] or 0) + (g["ia"] or 0)))[:10]:
        x = g["whisper"] / g["dur"] if g["whisper"] and g["dur"] and g["dur"] > 1 else None
        lentos.append({"t": g["t"], "titulo": g["titulo"], "pc": g["pc"], "dur": g["dur"], "whisper": g["whisper"],
                       "ia": g["ia"], "whisper_x": round(x, 3) if x else None,
                       "ia_lenta": bool(g["ia"] and med_ia and g["ia"] >= 2 * med_ia and g["ia"] - med_ia >= 10),
                       "whisper_lento": bool(x and med_x and x >= 2 * med_x and (g["whisper"] or 0) >= 5)})
    semanas = []
    if ok:
        grupos = {}
        for g in lista:
            grupos.setdefault(_lunes(g["t"]), []).append(g)
        ini = _lunes(desde) if desde else min(grupos)
        fin = _lunes(ahora)
        ini = max(ini, fin - timedelta(weeks=25))
        d = ini
        while d <= fin:
            semanas.append(dict(_resumen_tiempos(grupos.get(d, [])), desde=d.isoformat(),
                                hasta=(d + timedelta(days=6)).isoformat()))
            d += timedelta(weeks=1)
    errores = [{"t": g["t"], "titulo": g["titulo"], "pc": g["pc"], "detalle": g["detalle"]}
               for g in reversed(lista) if g["evento"] == "error"][:8]
    return {"resumen": res, "previo": previo, "lentos": lentos, "semanas": semanas, "errores": errores,
            "desde_registro": todos[0]["t"] if todos else None}


def _voz(lista):
    """Acierto del reconocimiento del médico por la voz: lo que se detectó al llegar el audio contra el médico con
    el que se guardó el informe. Solo cuentan los informes con huella de voz y médico elegido."""
    con = [i for i in lista if i.get("voz_estado") and i["medico"] != SIN_MEDICO]
    if not con:
        return None

    def grupo(estados):
        g = [i for i in con if i["voz_estado"] in estados]
        return {"n": len(g), "bien": sum(1 for i in g if i["voz_medico"] == i["medico"])}
    por_med = {}
    for i in con:
        x = por_med.setdefault(i["medico"], {"medico": i["medico"], "n": 0, "seguro": 0, "bien": 0, "mal": 0})
        x["n"] += 1
        if i["voz_estado"] == "seguro":
            x["seguro"] += 1
            x["bien" if i["voz_medico"] == i["medico"] else "mal"] += 1
    mal = [{"t": i["t"], "titulo": i["titulo"], "medico": i["medico"], "voz_medico": i["voz_medico"],
            "puntaje": i["voz_puntaje"]}
           for i in reversed(con) if i["voz_estado"] == "seguro" and i["voz_medico"] != i["medico"]][:10]
    return {"n": len(con), "seguro": grupo(("seguro",)), "dudoso": grupo(("dudoso",)),
            "sin": grupo(("desconocido", "corto")),
            "medicos": sorted(por_med.values(), key=lambda x: (-x["n"], x["medico"])), "errores": mal}


def calcular(dias=30, medico_actual=None, estudios_actual=None):
    """Estadísticas de los informes guardados en los últimos `dias` días (0 = todos)."""
    actual = {"medico": medico_actual or (lambda n: ""), "estudios": estudios_actual or (lambda n: None)}
    todos = _informes(actual)
    ahora = time.time()
    hoy0 = datetime.combine(date.today(), datetime.min.time()).timestamp()
    try:
        dias = max(0, min(int(dias or 0), 3650))
    except (TypeError, ValueError):
        dias = 30
    desde = hoy0 - (dias - 1) * 86400 if dias else None
    lista = [i for i in todos if desde is None or i["t"] >= desde]
    previo = None
    if dias:
        ant = [i for i in todos if desde - dias * 86400 <= i["t"] < desde]
        if ant:
            previo = _resumen(ant)
    medida = medida_trabajo(lista)
    ultimos = [{k: i[k] for k in ("t", "titulo", "pc", "medico", "estudios", "pct", "palabras", "rev", "marcas")}
               for i in reversed(lista[-40:])]
    return {
        "ahora": ahora, "dias": dias, "desde": desde,
        "primero": todos[0]["t"] if todos else None,
        "total_historico": len(todos),
        "rev_desde": next((i["t"] for i in todos if i["rev"]), None),
        "resumen": _resumen(lista), "previo": previo,
        "semanas": _semanas(lista, desde, ahora),
        "medida": medida,
        "medicos": _por(lista, "medico", medida),
        "estudios": _por(lista, "estudios", medida),
        "ultimos": ultimos,
        "tiempos": tiempos(desde, dias, ahora),
        "voz": _voz(lista),
    }
