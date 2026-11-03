# -*- coding: utf-8 -*-
"""
LO MÁS CORREGIDO (panel de administración, página "Correcciones").

Compara lo que escribió la IA con el informe final de cada ejemplo aprendido (ejemplos\\*.ia.txt contra
ejemplos\\*.informe.txt) y junta los cambios que más se repiten: palabras o frases reemplazadas, agregadas o
borradas. Se puede ver en general o por médico, y convertir un cambio en una regla de reglas_dictado.md
(la IA lee ese archivo en cada informe).

Igual que correcciones_aprendidas.md (aprendizaje/aprender.py), no cuenta los cambios con números (salen del dictado,
no se generalizan) ni los muy largos (reescrituras de un párrafo). Los cambios solo de puntuación o
mayúsculas se muestran si se pide.
"""
import difflib
import re
import threading
import time
from datetime import date, datetime

from transcripcion import RAIZ
from transcripcion.conocimiento import archivos as CON
from transcripcion.controles import marcas as MAR

AQUI = RAIZ          # carpeta del sistema (no la del paquete)
EJ = AQUI / "ejemplos"
REGLAS = CON.CONOC / "reglas_dictado.md"
APRENDIDAS = CON.CONOC / "correcciones_aprendidas.md"
SIN_MEDICO = "Sin especificar"
TITULO_SECCION = "# REGLAS AGREGADAS DESDE EL PANEL (lo más corregido)"
MAX_TOKENS = 12
FIN = "\n"
_CLAVE = re.compile(r"^(\d{8})_(\d{6})_(.+)\.informe\.txt$")
_lock = threading.Lock()
_CACHE = {"firma": None, "pares": []}


def _norm(s):
    return " ".join(w.strip(".,;:()«»…\"'").lower() for w in s.split() if w.strip(".,;:()«»…\"'"))


def _solo_forma(a, b):
    """Mismas palabras: solo cambia la puntuación o las mayúsculas."""
    return _norm(" ".join(a)) == _norm(" ".join(b))


def _tokens(texto):
    """Palabras del texto con el número de renglón de cada una (para mostrar el contexto)."""
    toks, lineas = [], texto.splitlines()
    for i, ln in enumerate(lineas):
        if i:
            toks.append((FIN, i))         # el cambio de renglón también es una "palabra": separa los cambios
        for w in ln.split():
            toks.append((w, i))
    return toks, lineas


def _leer(p):
    try:
        return p.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _ejemplos():
    """[(clave, fecha, nombre del caso, médico guardado)] de los ejemplos que tienen la salida de la IA."""
    out = []
    try:
        nombres = sorted(p.name for p in EJ.iterdir())
    except OSError:
        return out
    hay = set(nombres)
    for nm in nombres:
        m = _CLAVE.match(nm)
        if not m:
            continue
        clave = nm[:-len(".informe.txt")]
        if f"{clave}.ia.txt" not in hay:
            continue
        try:
            t = datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S").timestamp()
        except ValueError:
            continue
        med = (_leer(EJ / f"{clave}.medico.txt") or "").strip() if f"{clave}.medico.txt" in hay else ""
        out.append((clave, t, m.group(3), med))
    return out


def _firma():
    try:
        st = EJ.stat()
        return (st.st_mtime_ns, len(list(EJ.glob("*.informe.txt"))),
                max((p.stat().st_mtime_ns for p in EJ.glob("*.informe.txt")), default=0))
    except OSError:
        return None


def _contexto(toks, lineas, palabras, i1, i2):
    """Renglón donde está el cambio (si no hay palabras en el tramo: donde se insertó)."""
    if not toks:
        return ""
    k = next((k for k in range(i1, i2) if palabras[k] != FIN), min(i1, len(toks) - 1))
    return lineas[toks[min(k, len(toks) - 1)][1]].strip()


def _cambios_de(ia, final):
    """Cambios de un informe: [(tipo, de, a, contexto_ia, contexto_final)]."""
    ta, la = _tokens(ia)
    tb, lb = _tokens(final)
    a, b = [w for w, _ in ta], [w for w, _ in tb]
    sm = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
    out = []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            continue
        pa, pb = [w for w in a[i1:i2] if w != FIN], [w for w in b[j1:j2] if w != FIN]
        if not pa and not pb:
            continue                       # solo se agregó o sacó un renglón vacío
        if pa and pb and pa[0].startswith("-") and pb[0].startswith("-"):     # la viñeta "-" pegada a la frase
            pa, pb = [pa[0][1:]] + pa[1:], [pb[0][1:]] + pb[1:]
            pa, pb = [w for w in pa if w], [w for w in pb if w]
        op = "replace" if pa and pb else ("insert" if pb else "delete")
        larga = max(len(pa), len(pb)) > MAX_TOKENS
        de, a_ = " ".join(pa), " ".join(pb)
        numeros = bool(re.search(r"\d", de + a_))
        forma = op == "replace" and _solo_forma(pa, pb)
        ctx_a = _contexto(ta, la, a, i1, i2)
        ctx_b = _contexto(tb, lb, b, j1, j2)
        out.append({"tipo": op, "de": de, "a": a_, "ctx_ia": ctx_a, "ctx_final": ctx_b,
                    "larga": larga, "numeros": numeros, "forma": forma})
    return out


def _pares():
    """Todos los cambios de todos los ejemplos (cacheado mientras ejemplos\\ no cambie)."""
    firma = _firma()
    with _lock:
        if firma is not None and _CACHE["firma"] == firma:
            return _CACHE["pares"]
    pares = []
    for clave, t, nombre, med in _ejemplos():
        ia, fin = _leer(EJ / f"{clave}.ia.txt"), _leer(EJ / f"{clave}.informe.txt")
        if ia is None or fin is None:
            continue
        ia = "\n".join(l.rstrip() for l in MAR.texto_limpio(ia).splitlines())
        pares.append({"clave": clave, "t": t, "caso": nombre, "medico": med, "cambios": _cambios_de(ia, fin),
                      "palabras": len(fin.split())})
    with _lock:
        _CACHE.update(firma=firma, pares=pares)
    return pares


def _lineas_reglas():
    return [" ".join(ln.lower().split()) for ln in (_leer(REGLAS) or "").splitlines() if ln.strip()]


def _esta(frase, linea):
    return bool(re.search(r"(?<![\wáéíóúñü])" + re.escape(frase.lower()) + r"(?![\wáéíóúñü])", linea))


def en_reglas(tipo, de, a, lineas):
    """¿Ya hay una regla que lo menciona? (las dos formas en el mismo renglón; frases cortas no cuentan)."""
    if tipo == "replace":
        if len(a) < 3 or len(de) < 3:
            return False
        return any(_esta(de, ln) and _esta(a, ln) for ln in lineas)
    frase = a if tipo == "insert" else de
    return len(frase) >= 5 and any(_esta(frase, ln) for ln in lineas)


def _aprendidas():
    return " ".join((_leer(APRENDIDAS) or "").lower().split())


def sugerir_regla(tipo, de, a):
    if tipo == "replace":
        return f"- Escribir «{a}», no «{de}»."
    if tipo == "insert":
        return f"- Cuando el médico lo dicte, no olvidar «{a}»."
    return f"- No agregar «{de}» si el médico no lo dictó."


def calcular(dias=0, medico="", medico_actual=None, puntuacion=False, limite=80):
    """Cambios más repetidos en los informes guardados de los últimos `dias` días (0 = todos), en general o de
    un médico. Cuenta en cuántos informes aparece cada cambio (no cuántas veces)."""
    pares = _pares()
    medico_actual = medico_actual or (lambda n: "")
    try:
        dias = max(0, min(int(dias or 0), 3650))
    except (TypeError, ValueError):
        dias = 0
    hoy0 = datetime.combine(date.today(), datetime.min.time()).timestamp()
    desde = hoy0 - (dias - 1) * 86400 if dias else None
    medicos = {}
    for p in pares:
        p["med"] = p["medico"] or medico_actual(p["caso"]) or SIN_MEDICO
    en_periodo = [p for p in pares if desde is None or p["t"] >= desde]
    for p in en_periodo:
        medicos[p["med"]] = medicos.get(p["med"], 0) + 1
    lista = [p for p in en_periodo if not medico or p["med"] == medico]

    grupos, largas, con_numeros, forma = {}, 0, 0, 0
    for p in lista:
        for c in p["cambios"]:
            if c["larga"]:
                largas += 1
                continue
            if c["numeros"]:
                con_numeros += 1
                continue
            if c["forma"]:
                forma += 1
                if not puntuacion:
                    continue
            de_n, a_n = _norm(c["de"]), _norm(c["a"])
            if c["tipo"] == "replace" and not c["forma"] and de_n == a_n:
                continue
            k = (c["tipo"], c["de"].strip(".,;:") if c["forma"] else de_n, c["a"].strip(".,;:") if c["forma"] else a_n)
            g = grupos.setdefault(k, {"tipo": c["tipo"], "formas": {}, "informes": set(), "veces": 0,
                                      "medicos": {}, "ultimo": 0, "ejemplos": []})
            g["veces"] += 1
            forma_txt = (c["de"].strip(".,;:"), c["a"].strip(".,;:"))
            g["formas"][forma_txt] = g["formas"].get(forma_txt, 0) + 1
            if p["clave"] not in g["informes"]:
                g["informes"].add(p["clave"])
                g["medicos"][p["med"]] = g["medicos"].get(p["med"], 0) + 1
                g["ultimo"] = max(g["ultimo"], p["t"])
                if len(g["ejemplos"]) < 3:
                    g["ejemplos"].append({"t": p["t"], "medico": p["med"], "ia": c["ctx_ia"][:240],
                                          "final": c["ctx_final"][:240]})
    reglas, aprendidas = _lineas_reglas(), _aprendidas()
    items = []
    for k, g in grupos.items():
        de, a = max(g["formas"].items(), key=lambda x: x[1])[0]
        tipo = g["tipo"]
        items.append({"id": "|".join(k), "tipo": tipo, "de": de, "a": a, "informes": len(g["informes"]),
                      "veces": g["veces"], "medicos": sorted(g["medicos"].items(), key=lambda x: -x[1]),
                      "ultimo": g["ultimo"], "ejemplos": sorted(g["ejemplos"], key=lambda e: -e["t"]),
                      "en_reglas": en_reglas(tipo, de, a, reglas),
                      "aprendida": bool(de and a and f"«{de.lower()}»" in aprendidas and f"«{a.lower()}»" in aprendidas)
                                   or bool(tipo != "replace" and f"«{(a or de).lower()}»" in aprendidas),
                      "forma": tipo == "replace" and _norm(de) == _norm(a),
                      "regla": sugerir_regla(tipo, de, a)})
    items.sort(key=lambda x: (-x["informes"], -x["veces"], -x["ultimo"], x["de"].lower()))
    return {"ahora": time.time(), "dias": dias, "medico": medico, "puntuacion": puntuacion,
            "total_ejemplos": len(pares), "informes": len(lista),
            "palabras": sum(p["palabras"] for p in lista),
            "medicos": sorted(medicos.items(), key=lambda x: (-x[1], x[0].lower())),
            "items": items[:limite], "total_items": len(items),
            "repetidos": sum(1 for i in items if i["informes"] >= 2),
            "excluidos": {"largos": largas, "numeros": con_numeros, "forma": 0 if puntuacion else forma},
            "primero": min((p["t"] for p in pares), default=None)}


def agregar_regla(texto):
    """Agrega un renglón a conocimiento\\reglas_dictado.md, en su propia sección al final, con copia de la
    versión anterior en conocimiento\\copias. Devuelve {"linea"} o {"error"}."""
    t = " ".join(str(texto or "").split())
    if not t:
        return {"error": "Escribí la regla."}
    if len(t) > 400:
        return {"error": "La regla es muy larga: usá menos de 400 letras."}
    if not t.startswith("-"):
        t = "- " + t
    actual = _leer(REGLAS)
    if actual is None:
        actual = ""
    if any(ln.strip() == t for ln in actual.splitlines()):
        return {"error": "Esa regla ya está en reglas_dictado.md."}
    bk = CON.CONOC / "copias"
    bk.mkdir(parents=True, exist_ok=True)
    if actual:
        (bk / time.strftime("reglas_dictado_%Y%m%d_%H%M%S.md")).write_text(actual, encoding="utf-8")
    nuevo = actual.rstrip("\n")
    if TITULO_SECCION not in actual:
        nuevo += ("\n\n" if nuevo else "") + TITULO_SECCION
    nuevo += "\n" + t + "\n"
    tmp = REGLAS.with_name(REGLAS.name + ".nuevo")
    tmp.write_text(nuevo, encoding="utf-8")
    tmp.replace(REGLAS)
    return {"linea": t}
