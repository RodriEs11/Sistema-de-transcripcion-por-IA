"""Nucleo de la fase 2: arma el prompt, llama a la IA local (Ollama), y marca
en el informe resultante los lugares que hay que revisar a mano.

Marcas que produce (en el texto: [[tipo|texto|motivo]]):
  dudoso     -> la IA no entendio bien el dictado y propone un texto
  completar  -> falta un dato que la plantilla necesita
  numero     -> numero / nivel / hora que NO aparece en el dictado
  bajaconf   -> numero que aparece en el dictado pero Whisper lo oyo con poca seguridad
  plantilla  -> frase de plantilla que el medico no dicto explicitamente (verificar que corresponda)
  verificar  -> texto que la IA escribio y no se encuentra en el dictado

Cada marca lleva su motivo concreto ("Dictado: 12 / Informe: 2").

Viene de nucleo.py (docs/refactor.md, etapa 3).
"""

import difflib
import html
import re
from transcripcion.texto.normalizacion import normalizar, sin_acentos, datos_criticos
from transcripcion.conocimiento import plantillas as PL
from transcripcion.controles import clinicos as CLI
from transcripcion.ia import ejemplos as EJEM
from transcripcion.texto import palabras as PAL


# ----------------------------------------------------------- marcas
NUM_RE = re.compile(r"(?<![A-Za-z0-9.,])(\d+(?:[.,]\d+)?)")
COD_RE = re.compile(r"\b([HCDLST]\d{1,2}(?:-[CDLS]\d{1,2})?)\b")


LINEAS_FIJAS = ("hemos obtenido", "lo saluda")
IGNORAR_TITULO = {
    "digital",
    "bilateral",
    "prolongaciones",
    "axilares",
    "ginecologica",
    "ambas",
    "ambos",
    "frente",
    "perfil",
    "oblicuo",
    "tecnica",
    "derecha",
    "derecho",
    "izquierda",
    "izquierdo",
}


ESTRUCTURALES = {
    "dimensiones",
    "uterinas",
    "longitudinal",
    "anteroposterior",
    "transverso",
    "transversal",
    "endometrio",
    "espesor",
    "ovario",
    "derecho",
    "izquierdo",
    "mide",
    "lobulo",
    "istmo",
    "categorizacion",
    "conjunta",
    "central",
    "ecogenico",
}


def palabras_estructurales():
    """Rotulos de las plantillas que el medico no dicta ('Dimensiones uterinas: Longitudinal...')."""
    return ESTRUCTURALES


def soporte(linea, vocab_dictado):
    """Fraccion de palabras de contenido de la linea que aparecen (aprox.) en el dictado."""
    ignorar = palabras_estructurales() | {"como", "para", "sobre", "ambas", "ambos", "nivel"}
    ps = [p for p in PAL.palabras_norm(linea) if p not in ignorar]
    if not ps:
        return 1.0
    ok = 0
    for p in ps:
        if p in vocab_dictado or difflib.get_close_matches(p, vocab_dictado, n=1, cutoff=0.7):
            ok += 1
    return ok / len(ps)


# ------------------------------------------- explicacion de cada marca
# Cada marca lleva un motivo concreto ("Dictado: 12 / Informe: 2") en vez de uno generico.
STOP_ALINEAR = {
    "como",
    "para",
    "sobre",
    "entre",
    "desde",
    "hasta",
    "este",
    "esta",
    "estos",
    "estas",
    "tiene",
    "presenta",
    "pero",
    "porque",
    "cual",
    "cuales",
    "donde",
    "cuando",
    "nivel",
    "ambas",
    "ambos",
}


RE_COD = r"[hcdlst]\d{1,2}(?:[cdls]\d{1,2})?"
RE_NUM = r"\d+(?:\.\d+)?"


def toks_dictado(norm_dict):
    """Dictado normalizado partido en palabras limpias (para buscar el tramo de cada linea)."""
    return [re.sub(r"[^a-z0-9.]", "", w).strip(".") for w in norm_dict.split()]


def _claves_linea(linea):
    nl = normalizar(re.sub(r"\[\[(?:COMPLETAR:?|\?)", " ", linea).replace("]]", " "))
    nums = re.findall(rf"(?<![a-z0-9.]){RE_NUM}|\b{RE_COD}\b", nl)
    pals = [p for p in re.findall(r"[a-z]{4,}", nl) if p not in ESTRUCTURALES and p not in STOP_ALINEAR]
    return [(x, 2.0) for x in dict.fromkeys(nums)] + [(p, 1.0) for p in dict.fromkeys(pals)]


def _igual(c, t):
    if not t:
        return False
    if c[0].isdigit() or re.fullmatch(RE_COD, c):
        return c == t
    if len(t) < 4 or not t.isalpha():
        return False
    if len(c) >= 5 and len(t) >= 5:
        if c[:5] == t[:5]:
            return True
    elif c == t:
        return True
    return c[:2] == t[:2] and abs(len(c) - len(t)) <= 3 and difflib.SequenceMatcher(a=c, b=t).ratio() >= 0.82


def ventana_dictado(linea, toks):
    """(a, b): indices de toks del tramo del dictado que mejor corresponde a la linea, o None."""
    claves = _claves_linea(linea)
    if not claves:
        return None
    pos = {}
    for i, t in enumerate(toks):
        for k, (c, _) in enumerate(claves):
            if _igual(c, t):
                pos.setdefault(i, set()).add(k)
    if not pos:
        return None
    ancho = max(10, 3 * len(claves))
    idx = sorted(pos)
    mejor = None
    for s, a in enumerate(idx):
        vistos = set()
        for j in idx[s:]:
            if j - a > ancho:
                break
            vistos |= pos[j]
            cand = (sum(claves[k][1] for k in vistos), -(j - a), -a, j)
            if mejor is None or cand > mejor:
                mejor = cand
    puntaje, _, a, b = mejor
    if puntaje < min(2.0, sum(w for _, w in claves)):
        return None
    return -a, b


def etiqueta_dato(x):
    """'l5s1' -> 'L5-S1', 'h12' -> 'H12', '3.5' -> '3,5'"""
    if re.fullmatch(RE_COD, x):
        return re.sub(r"^([CDLS]\d+)([CDLS]\d+)$", r"\1-\2", x.upper())
    return x.replace(".", ",")


def datos_cerca(linea, toks, codigo=False):
    """Numeros (o codigos H12/L5-S1) dictados cerca del tramo de la linea que no estan en la linea."""
    v = ventana_dictado(linea, toks)
    if not v:
        return []
    a, b = v
    pat = RE_COD if codigo else RE_NUM
    en_linea = datos_criticos(linea, True)
    out = []
    for t in toks[max(0, a - 6) : b + 7]:
        if re.fullmatch(pat, t) and t not in en_linea and t not in out:
            out.append(t)
    return out


def motivo_numero(tok, linea, toks):
    key = tok.lower().replace("-", "").replace(",", ".")
    codigo = key[0].isalpha()
    cerca = datos_cerca(linea, toks, codigo)
    if not cerca and not codigo and len(key) >= 2:
        # Whisper a veces junta las medidas: "mide 98, 49, 51" -> "984951"
        pegados = [t for t in dict.fromkeys(toks) if re.fullmatch(r"\d+", t) and len(t) > len(key) + 1 and key in t]
        if pegados:
            return f"Dictado: {pegados[0]} (Whisper juntó los números) / Informe: {tok}"
    if not cerca:
        return f"Informe: {tok} · este {'dato' if codigo else 'número'} no aparece en el dictado"
    if len(cerca) == 1:
        return f"Dictado: {etiqueta_dato(cerca[0])} / Informe: {tok}"
    cerca.sort(key=lambda x: -difflib.SequenceMatcher(a=key, b=x).ratio())
    return f"Informe: {tok} · no está en el dictado. Cerca se dictó: " + ", ".join(etiqueta_dato(x) for x in cerca[:4])


def formas_originales(dictado):
    """palabra sin acentos -> como esta escrita en el dictado (para mostrarla con tildes)."""
    out = {}
    for w in re.findall(r"[a-záéíóúñü]+", dictado.lower()):
        out.setdefault(sin_acentos(w), w)
    return out


def palabras_no_dictadas(linea, vocab):
    """Palabras de la linea que no se encuentran en el dictado (como estan escritas en el informe)."""
    ignorar = palabras_estructurales() | {"como", "para", "sobre", "ambas", "ambos", "nivel"}
    out = []
    for w in re.findall(r"[A-Za-zÁÉÍÓÚáéíóúñÑüÜ]{4,}", re.sub(r"\[\[.*?\]\]", "", linea)):
        p = sin_acentos(w.lower())
        if p in ignorar or p in vocab or difflib.get_close_matches(p, vocab, n=1, cutoff=0.7):
            continue
        if w.lower() not in (x.lower() for x in out):
            out.append(w)
    return out


def motivo_linea(tipo, l, vocab, norm_dict, es_tit=False):
    if es_tit:
        return f"No reconozco «{l.strip()}» en el dictado: confirmá que es el estudio que se dictó"
    if tipo == "plantilla":
        if re.search(r"protocol", norm_dict):
            return "Frase de plantilla, no dictada (el médico dijo «protocolo…»): confirmá que corresponde"
        return "Frase de plantilla que el médico no dictó: confirmá que corresponde"
    faltan = palabras_no_dictadas(l, vocab)
    if faltan:
        return "No encontré en el dictado: " + ", ".join(faltan[:5]) + ". Verificá que esta línea corresponda"
    return MOTIVO_LINEA["verificar"]


def marcar(informe, dictado, palabras_whisper=None):
    """Devuelve lista de lineas; cada linea = lista de (texto, tipo, motivo)."""
    plantilla = PL.frases_de_plantilla()
    norm_dict = normalizar(dictado)
    nums_dict = set(re.findall(r"(?<![a-z0-9.])\d+(?:\.\d+)?", norm_dict))
    cods_dict = set(re.findall(r"\b[hcdlst]\d{1,2}(?:[cdls]\d{1,2})?\b", norm_dict))
    vocab = set(PAL.palabras_norm(dictado))
    toks = toks_dictado(norm_dict)
    bajos = {}
    for w in palabras_whisper or []:
        if w["conf"] < 0.6:
            for x in re.findall(r"\d+(?:\.\d+)?", normalizar(w["p"])):
                bajos[x] = min(bajos.get(x, 1.0), w["conf"])

    salida = []
    for linea in informe.splitlines():
        segs = []
        l = linea.rstrip()
        if re.match(r"(?i)^-\s*(es un |un )?protocolo( normal)?\.?$", l.strip()):
            salida.append(
                {
                    "segs": [
                        (
                            "[COMPLETAR: protocolo normal de este estudio]",
                            "completar",
                            "La IA escribió «protocolo normal» sin el texto: falta la plantilla de este "
                            "estudio. Escribí las viñetas del protocolo normal",
                        )
                    ],
                    "linea": None,
                    "titulo": False,
                }
            )
            continue
        low = sin_acentos(l.lower()).strip()
        fija = low.startswith(LINEAS_FIJAS) or not l.strip() or PL.es_linea_fija(l)
        es_titulo_l = PL.es_titulo(l)
        # 1) marcas de la IA
        partes = re.split(r"(\[\[.*?\]\])", l)
        for p in partes:
            m = re.match(r"\[\[(COMPLETAR:?|\?)\s*(.*?)\]\]$", p, flags=re.S)
            if m:
                if m.group(1).startswith("COMPLETAR"):
                    segs.append(
                        (
                            "[COMPLETAR: " + m.group(2) + "]",
                            "completar",
                            f"Falta: {m.group(2).strip() or 'un dato'}. No se dictó: completalo escuchando "
                            "el audio o borralo si no corresponde",
                        )
                    )
                else:
                    segs.append(
                        (
                            m.group(2),
                            "dudoso",
                            f"La IA no entendió bien esta parte y propone «{m.group(2)}». "
                            "Escuchá el audio para confirmarlo",
                        )
                    )
                continue
            if fija or not p:
                segs.append((p, None, None))
                continue
            # 2) numeros y codigos
            pos = 0
            for mm in re.finditer(r"\b[HCDLST]\d{1,2}(?:-[CDLS]\d{1,2})?\b|(?<![A-Za-z0-9.,])\d+(?:[.,]\d+)?", p):
                tok = mm.group(0)
                if pos < mm.start():
                    segs.append((p[pos : mm.start()], None, None))
                key = tok.lower().replace("-", "").replace(",", ".")
                if key[0].isalpha():
                    ok = key in cods_dict
                else:
                    ok = key in nums_dict
                if not ok:
                    segs.append((tok, "numero", motivo_numero(tok, l, toks)))
                elif key in bajos:
                    segs.append(
                        (
                            tok,
                            "bajaconf",
                            f"Whisper oyó «{tok}» con poca seguridad "
                            f"(confianza {round(bajos[key] * 100)} %): escuchalo para confirmar",
                        )
                    )
                else:
                    segs.append((tok, None, None))
                pos = mm.end()
            if pos < len(p):
                segs.append((p[pos:], None, None))
        # 3) soporte de la linea completa en el dictado
        tipo_linea = motivo_l = None
        if es_titulo_l and not fija:
            # el tipo de estudio del titulo tiene que poder reconocerse en el dictado
            sin_rotulos = " ".join(p for p in PAL.palabras_norm(l) if p not in IGNORAR_TITULO)
            if sin_rotulos and soporte(sin_rotulos, vocab) < 0.5:
                tipo_linea = "verificar"
                motivo_l = motivo_linea(tipo_linea, l, vocab, norm_dict, es_tit=True)
        elif l.startswith("-") and not fija:
            sop = soporte(re.sub(r"\[\[.*?\]\]", "", l), vocab)
            if sop < 0.5:
                tipo_linea = "plantilla" if l in plantilla else "verificar"
                motivo_l = motivo_linea(tipo_linea, l, vocab, norm_dict)
        salida.append({"segs": segs, "linea": tipo_linea, "motivo": motivo_l, "titulo": bool(es_titulo_l and not fija)})
    CLI.controles_clinicos(salida, norm_dict, formas_originales(dictado))
    control_palabras_raras(salida)
    return salida


# Palabras que nunca aparecieron en tus informes (ej. "para el horario" copiado de Whisper).
# Con pocos informes de referencia daria demasiadas falsas alarmas: se activa sola al llegar a UMBRAL.
UMBRAL_VOCABULARIO = 150
_VOCAB = {"n": None, "set": None}


MOTIVO_RARA = "Palabra que no aparece en tus informes anteriores: posible error de Whisper copiado"


def vocabulario_informes():
    if _VOCAB["set"] is None:
        banco = EJEM.cargar_banco()
        _VOCAB["n"] = len(banco)
        v = set(re.findall(r"[a-záéíóúñü]+", PL.texto_todas_las_plantillas().lower()))
        for e in banco:
            v |= set(re.findall(r"[a-záéíóúñü]+", e["informe"].lower()))
        _VOCAB["set"] = v
    return _VOCAB["set"] if _VOCAB["n"] >= UMBRAL_VOCABULARIO else None


def control_palabras_raras(salida):
    try:
        v = vocabulario_informes()
    except Exception:
        return
    if not v:
        return
    for ln in salida:
        texto = "".join(t for t, _, _ in ln["segs"])
        if not texto.strip() or sin_acentos(texto.lower()).startswith(LINEAS_FIJAS):
            continue
        ln["segs"] = CLI.partir(
            ln["segs"], r"[A-Za-zÁÉÍÓÚáéíóúñÑüÜ]{3,}", "dudoso", MOTIVO_RARA, lambda m: m.group(0).lower() not in v
        )


def texto_limpio(informe):
    """Informe sin las marcas [[...]] (para comparar con el informe real)."""
    t = re.sub(r"\[\[COMPLETAR:?\s*(.*?)\]\]", r"[COMPLETAR: \1]", informe)
    return re.sub(r"\[\[\?\s*(.*?)\]\]", r"\1", t)


MOTIVO_LINEA = {
    "plantilla": "Frase de plantilla que no se dictó explícitamente: confirmá que corresponde",
    "verificar": "La IA escribió esta línea y no se encuentra en el dictado: verificar",
}


def buscar_tiempo(texto, palabras):
    """Segundo del audio donde aparece (aprox.) este texto en el dictado."""
    if not palabras:
        return None
    nt = normalizar(texto)
    claves = re.findall(r"\d+(?:\.\d+)?", nt) or [p for p in PAL.palabras_norm(texto) if p not in ESTRUCTURALES][:3]
    for w in palabras:
        nw = normalizar(w["p"])
        for c in claves:
            if c.isdigit() or "." in c:
                if c in re.findall(r"\d+(?:\.\d+)?", nw):
                    return w["ini"]
            elif difflib.SequenceMatcher(a=c, b=re.sub(r"[^a-z]", "", nw)).ratio() > 0.75:
                return w["ini"]
    return None


def a_html(marcado, palabras=None):
    out = []
    for ln in marcado:

        def mk(t, tipo, mot):
            seg = buscar_tiempo(t, palabras) if palabras else None
            click = f' onclick="ir({seg})" style="cursor:pointer"' if seg is not None else ""
            return f'<mark class="m-{tipo}" title="{html.escape(mot)}"{click}>{html.escape(t)}</mark>'

        inner = "".join(html.escape(t) if not tipo else mk(t, tipo, mot) for t, tipo, mot in ln["segs"])
        cls = ["ln"]
        tit = ""
        if ln["linea"]:
            cls.append("l-" + ln["linea"])
            tit = f' title="{html.escape(ln.get("motivo") or MOTIVO_LINEA[ln["linea"]])}"'
        if ln["titulo"]:
            cls.append("tit")
        out.append(f'<div class="{" ".join(cls)}"{tit}>{inner or "&nbsp;"}</div>')
    return "\n".join(out)


def contar_marcas(marcado):
    c = {}
    for ln in marcado:
        if ln["linea"]:
            c[ln["linea"]] = c.get(ln["linea"], 0) + 1
        for _, tipo, _ in ln["segs"]:
            if tipo:
                c[tipo] = c.get(tipo, 0) + 1
    return c


CSS_MARCAS = """
mark{color:inherit;border-radius:3px;padding:0 2px}
.m-dudoso{background:var(--amarillo)}.m-bajaconf{background:var(--amarillo);outline:1px dashed var(--naranja)}
.m-completar{background:var(--rojo);font-weight:600}.m-numero{background:var(--rojo)}
.l-plantilla{color:var(--mu);border-left:3px solid var(--gris);padding-left:6px}
.l-verificar{border-left:3px solid var(--naranja);padding-left:6px;background:var(--naranja-bg)}
.tit{font-weight:700}
"""
