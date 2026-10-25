# -*- coding: utf-8 -*-
"""
NOMBRE DEL PACIENTE: el médico lo dice al principio del dictado
("Gómez Laura es una mamografía...", "Paciente Pérez Sánchez, en la ecografía...").
Se usa SOLO para mostrar en la lista de casos y en el título del caso: nunca va al informe ni a la IA.

Si Whisper lo entendió mal se puede corregir desde la interfaz; la corrección se guarda en
<caso>.paciente.json con "manual": true y ya no se vuelve a calcular.
"""
import json
import re
import unicodedata

# palabras con las que el médico arranca antes del nombre
_INICIO = re.compile(
    r"^(?:(?:bueno|bien|ok|okey|y|este|eh|em|mm|ahora|ah[ií]|aqu[ií]|ac[aá]|listo|sigo|seguimos|vamos|otro|otra|siguiente)[\s,.:;]+)*"
    r"(?:(?:en\s+)?(?:el|la|los|las)?\s*(?:paciente|pacientes|pte)s?\b[\s,.:;]*(?:de(?:l)?\s+|es\s+|se\s+llama\s+)?)?",
    re.I)
_TRAS_PACIENTE = re.compile(r"\b(?:paciente|pacientes|pte)\b", re.I)

# donde termina el nombre: verbos, artículos o el estudio
_CORTE = set("""
tiene tienen tenemos tenia tenía es son era emite presenta presentan realiza realizo realizó se le les
con una un uno en el la los las al del para por que y-no informe informamos colocamos ponemos iniciamos
rx rq rayos radiografia radiografía eco ecografia ecografía ecografía ecocardiograma mamografia mamografía mama mamas
mammo mamo espinograma tomografia tomografía tac tc resonancia rm transvaginal trasvaginal doppler
protocolo estudio estudios control placa placas centellograma densitometria densitometría pet
""".split())
_ESTUDIO = re.compile(r"(?:gra?f[ií]|cr[oa]f[ií]|^eco$|^mam(?:aria|as?|o|mo)$|^tomograf|^radiograf|^resonanc|^tra[n]?s?vag)")
_CONECTOR = {"de", "del", "la", "las", "los", "y", "san", "santa", "da", "di", "van", "von"}
_RELLENO = {"ella", "el", "él", "es", "a", "ver", "aca", "acá"}


def _sin_acentos(t):
    return "".join(c for c in unicodedata.normalize("NFD", t) if unicodedata.category(c) != "Mn")


def _capitalizar(p):
    if p.lower() in _CONECTOR:
        return p.lower()
    return "-".join(x[:1].upper() + x[1:].lower() for x in p.split("-"))


def extraer(texto):
    """Nombre del paciente al principio del dictado, o None si no se encuentra uno creíble."""
    if not texto:
        return None
    t = " ".join(texto.split()[:25])
    m = _INICIO.match(t)
    dijo_paciente = bool(_TRAS_PACIENTE.search(m.group(0))) if m else False
    resto = t[m.end():] if m else t
    toks = re.findall(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ'\-]+|[,.;:]", resto)
    nombre, coma = [], False
    for tk in toks:
        b = _sin_acentos(tk.lower())
        if tk in ",;:":
            coma = coma or bool(nombre)                # "Castiñeira, Anoelias"
            continue
        if tk == ".":
            break
        if _ESTUDIO.search(b) and nombre:               # "enocografía", "anecrofía" (Whisper)
            break
        if not nombre and b in _RELLENO:               # "Y ella es Ana María" (antes del corte: "es" corta)
            continue
        if b in _CORTE and not (b in ("la", "y", "del") and nombre):    # "De la Fuente", "Blanco y Mediano"
            break
        nombre.append(tk)
        if len(nombre) > 5:
            return None
    while nombre and nombre[-1].lower() in _CONECTOR:   # "Ruiz de" -> "Ruiz"
        nombre.pop()
    if not nombre:
        return None
    mayus = sum(1 for p in nombre if p[:1].isupper())
    reales = [p for p in nombre if p.lower() not in _CONECTOR]
    if not dijo_paciente:
        # sin la palabra "paciente" se exige que parezca un nombre: dos palabras con mayúscula,
        # o "Apellido, nombre" con coma
        if len(reales) < 2 or mayus < (1 if coma and nombre[0][:1].isupper() else 2):
            return None
    if any(len(p) < 2 for p in reales) or any(_sin_acentos(p.lower()) in _CORTE for p in reales):
        return None
    out = [_capitalizar(p) for p in nombre]
    out[0] = out[0][:1].upper() + out[0][1:]
    return " ".join(out)


# ---------------------------------------------------------------- archivo por caso
def leer(datos, n):
    """{"p": nombre o None, "manual": bool} o None si todavía no se calculó."""
    f = datos / f"{n}.paciente.json"
    if not f.exists():
        return None
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None


def calcular(datos, n, forzar=False):
    """Calcula (o recalcula) el nombre desde el dictado, salvo que haya sido corregido a mano."""
    previo = leer(datos, n)
    if previo and (previo.get("manual") or not forzar):
        return previo.get("p")
    d = datos / f"{n}.dictado.txt"
    if not d.exists():
        return None
    p = extraer(d.read_text(encoding="utf-8"))
    (datos / f"{n}.paciente.json").write_text(json.dumps({"p": p, "manual": False}, ensure_ascii=False),
                                              encoding="utf-8")
    return p


def corregir(datos, n, nombre):
    """Nombre escrito a mano. Vacío = volver a sacarlo del dictado."""
    nombre = " ".join(str(nombre or "").split())[:80]
    if not nombre:
        (datos / f"{n}.paciente.json").unlink(missing_ok=True)
        return calcular(datos, n)
    (datos / f"{n}.paciente.json").write_text(json.dumps({"p": nombre, "manual": True}, ensure_ascii=False),
                                              encoding="utf-8")
    return nombre


def de(datos, n):
    """Para mostrar: lo guardado, o se calcula la primera vez (casos anteriores a esta función)."""
    v = leer(datos, n)
    if v is not None:
        return v.get("p")
    return calcular(datos, n)
