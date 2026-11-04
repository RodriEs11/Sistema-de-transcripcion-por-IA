"""Plantillas por estudio (plantillas.md, generales y propias de cada transcriptor): secciones, categorías,
títulos de estudio, líneas de texto fijo y selección de las plantillas relevantes para un dictado.

Viene de nucleo.py (docs/refactor.md, etapa 3).
"""

import difflib
import re
import time
from typing import Any

from transcripcion.acceso import usuarios as U
from transcripcion.conocimiento import archivos as CON
from transcripcion.texto.normalizacion import sin_acentos


def texto_todas_las_plantillas():
    """plantillas.md general + las plantillas propias de cada transcriptor. Sirve para los controles (frases de
    plantilla, texto fijo, estudios conocidos): una frase de la plantilla de cualquiera es frase de plantilla."""
    partes = [CON.leer("plantillas.md")]
    for clave in U.claves_con_carpeta():
        t = U.leer_archivo(clave, "plantillas.md")
        if t.strip():
            partes.append(t)
    return "\n\n".join(partes)


def _firma_plantillas():
    fs = [CON.CONOC / "plantillas.md"] + [U.CARPETA / c / "plantillas.md" for c in U.claves_con_carpeta()]
    out = []
    for f in fs:
        try:
            st = f.stat()
            out.append((str(f), st.st_mtime_ns, st.st_size))
        except FileNotFoundError:
            pass
    return tuple(out)


def frases_de_plantilla():
    """Viñetas fijas de las plantillas (sin huecos <...> ni alternativas |)."""
    out = set()
    for linea in texto_todas_las_plantillas().splitlines():
        linea = linea.strip()
        if linea.startswith("-") and "<" not in linea and "|" not in linea and "/  -" not in linea:
            out.add(linea)
    return out


def categorias(texto, claves=None):
    t = sin_acentos(texto.lower())
    c = set()
    if re.search(r"\bmamm?(a|as|o|ografia|aria)\b|birads|bi-rads|birrad|\bacr\b", t):
        c.add("mama")
    if re.search(r"transvag|trasvag|atrapag|utero|endometr|ovario", t):
        c.add("gine")
    if re.search(r"tiroid", t):
        c.add("tiroides")
    if re.search(r"espinograma|colum|colonia\s+(?:lumb|lomb|cerv|dors)|vertebr|lumbo|lombo|cervical", t):
        c.add("columna")
    if re.search(r"torax|torads|pulmon|costofren", t):
        c.add("torax")
    if re.search(r"\bmanos?\b|muneca|hombro|rodilla|cadera|\bpies?\b|brazo|codo|tobillo", t):
        c.add("osteo")
    if re.search(r"\btc\b|tomograf|\btomo\b|\bte ce\b|tomografo", t):
        c.add("tc")
    if re.search(r"\bpet\b|captacion|\bfdg\b|\bsuv\b|radiofarmaco", t):
        c.add("pet")
    # estudios agregados en plantillas.md (ej. "ECOGRAFÍA ABDOMINAL" -> "abdominal")
    palabras = set(re.findall(r"[a-z]{5,}", t))
    for clave in claves_de_plantillas() if claves is None else claves:
        if clave in palabras or difflib.get_close_matches(clave, list(palabras), n=1, cutoff=0.85):
            c.add("pl:" + clave)
    return c


GENERICAS = {
    "ecografia",
    "mamografia",
    "estudio",
    "digital",
    "bilateral",
    "frente",
    "perfil",
    "ambas",
    "ambos",
    "derecha",
    "derecho",
    "izquierda",
    "izquierdo",
    "osteoarticular",
    "orden",
    "cierre",
    "informe",
    "columna",
    "espinograma",
    "torax",
    "mamaria",
    "transvaginal",
    "ginecologica",
    "tiroidea",
    "cervical",
    "dorsal",
    "lumbosacra",
    "dorsolumbar",
    "manos",
    "muneca",
    "hombros",
    "rodillas",
    "caderas",
    "brazo",
    "region",
    "texto",
    "comun",
    "tomografia",
    "partes",
    "blandas",
}


def claves_de_plantillas():
    """Palabras que identifican cada estudio de plantillas.md (las de los estudios nuevos)."""
    out = set()
    for nombre, _ in todas_las_secciones():
        nombre = nombre.split("(")[0]
        for w in re.findall(r"[a-z]{5,}", sin_acentos(nombre.lower())):
            if w not in GENERICAS:
                out.add(w)
    return out


# ------------------------------------------------------- plantillas (secciones)
def _partir_secciones(texto):
    partes = re.split(r"(?m)^## ", texto)
    pre, secs = partes[0], []
    for p in partes[1:]:
        nombre, _, cuerpo = p.partition("\n")
        secs.append((nombre.strip(), cuerpo.strip("\n")))
    return pre, secs


def _clave_seccion(nombre):
    return " ".join(sin_acentos(nombre or "").casefold().split())


def secciones_de_usuario(usuario):
    """Secciones que el transcriptor cambió o agregó «solo para mí»."""
    if not usuario:
        return []
    return _partir_secciones(U.leer_archivo(usuario, "plantillas.md"))[1]


def secciones_plantillas(usuario=None):
    """plantillas.md -> (encabezado, [(nombre, cuerpo), ...]) separando por '## '.
    Con usuario: sus secciones propias reemplazan a la general del mismo nombre y las nuevas se agregan al final."""
    pre, secs = _partir_secciones(CON.leer("plantillas.md"))
    propias = secciones_de_usuario(usuario)
    if propias:
        por_clave = {_clave_seccion(n): (n, c) for n, c in propias}
        secs = [por_clave.pop(_clave_seccion(n), (n, c)) for n, c in secs]
        secs += list(por_clave.values())
    return pre, secs


def todas_las_secciones():
    """Las generales y las de todos los transcriptores (para reconocer estudios y títulos)."""
    secs = list(_partir_secciones(CON.leer("plantillas.md"))[1])
    for clave in U.claves_con_carpeta():
        secs += secciones_de_usuario(clave)
    return secs


def secciones_con_origen(usuario=None):
    """Para el editor de plantillas: cada sección con su origen.
    origen: 'general' · 'propia' (cambiada solo para este transcriptor) · 'nueva' (solo existe en las suyas)."""
    generales = {_clave_seccion(n): c for n, c in _partir_secciones(CON.leer("plantillas.md"))[1]}
    propias = {_clave_seccion(n) for n, _ in secciones_de_usuario(usuario)}
    out = []
    for n, c in secciones_plantillas(usuario)[1]:
        k = _clave_seccion(n)
        if k not in propias:
            out.append({"nombre": n, "cuerpo": c, "origen": "general"})
        elif k in generales:
            out.append({"nombre": n, "cuerpo": c, "origen": "propia", "general": generales[k]})
        else:
            out.append({"nombre": n, "cuerpo": c, "origen": "nueva"})
    return out


def guardar_secciones_usuario(usuario, secs):
    """Guarda las plantillas propias (con copia de la versión anterior en su carpeta copias/)."""
    anterior = U.leer_archivo(usuario, "plantillas.md")
    if anterior.strip():
        bk = U.carpeta(usuario) / "copias"
        bk.mkdir(parents=True, exist_ok=True)
        (bk / time.strftime("plantillas_%Y%m%d_%H%M%S.md")).write_text(anterior, encoding="utf-8")
    texto = "\n\n".join(f"## {n.strip()}\n{c.strip()}" for n, c in secs if n.strip())
    U.escribir_archivo(
        usuario,
        "plantillas.md",
        "# PLANTILLAS PROPIAS (reemplazan a la general del mismo nombre)\n\n" + texto + "\n" if texto else "",
    )


def aplicar_plantillas(enviadas, usuario, destino):
    """Lo que manda el editor de plantillas (la lista completa que ve el transcriptor).
    destino 'todos': lo cambiado va a plantillas.md (y deja de ser propio); 'mio': lo cambiado queda solo para él.
    Devuelve un resumen {"generales": n, "propias": n, "sin_cambios": bool}."""
    if destino not in ("todos", "mio"):
        raise ValueError("Elegí si el cambio es para vos o para todos.")
    if destino == "mio" and not usuario:
        raise ValueError("Para guardar solo para vos tenés que entrar con tu usuario.")
    enviadas = [(str(n).strip(), str(c)) for n, c in enviadas if str(n).strip()]
    vistas = {_clave_seccion(n): (n, c) for n, c in secciones_plantillas(usuario)[1]}
    nuevas = {_clave_seccion(n): (n, c) for n, c in enviadas}
    if len(nuevas) != len(enviadas):
        raise ValueError("Hay dos plantillas con el mismo nombre: cambiale el nombre a una.")
    cambiadas = {
        k: v
        for k, v in nuevas.items()
        if k not in vistas or vistas[k][1].strip() != v[1].strip() or vistas[k][0] != v[0]
    }
    borradas = [k for k in vistas if k not in nuevas]
    if not cambiadas and not borradas:
        return {"generales": 0, "propias": 0, "sin_cambios": True}
    _, generales = _partir_secciones(CON.leer("plantillas.md"))
    gen = {_clave_seccion(n): (n, c) for n, c in generales}
    propias = {_clave_seccion(n): (n, c) for n, c in secciones_de_usuario(usuario)}
    if destino == "todos":
        orden = [k for k in gen if k not in borradas]
        for k, v in cambiadas.items():
            gen[k] = v
            if k not in orden:
                orden.append(k)
            propias.pop(k, None)  # ya es la general: deja de ser propia
        for k in borradas:
            gen.pop(k, None)
            propias.pop(k, None)
        guardar_secciones([gen[k] for k in orden])
    else:
        for k, v in cambiadas.items():
            if k in gen and gen[k][1].strip() == v[1].strip() and gen[k][0] == v[0]:
                propias.pop(k, None)  # quedó igual a la general
            else:
                propias[k] = v
        for k in borradas:
            if k in propias:
                propias.pop(k)  # borrar la propia = volver a la general (si existe)
    if usuario:
        guardar_secciones_usuario(usuario, list(propias.values()))
    return {
        "generales": len(cambiadas) + len(borradas) if destino == "todos" else 0,
        "propias": len(cambiadas) + len(borradas) if destino == "mio" else 0,
        "sin_cambios": False,
        "no_borradas": [vistas[k][0] for k in borradas if destino == "mio" and k in gen],
    }


def volver_a_general(usuario, nombre):
    """Quita la versión propia de una plantilla (vuelve a usar la general)."""
    propias = [(n, c) for n, c in secciones_de_usuario(usuario) if _clave_seccion(n) != _clave_seccion(nombre)]
    if len(propias) == len(secciones_de_usuario(usuario)):
        return False
    guardar_secciones_usuario(usuario, propias)
    return True


def guardar_secciones(secs):
    """Guarda plantillas.md (con copia de seguridad de la version anterior)."""
    pre, _ = secciones_plantillas()
    bk = CON.CONOC / "copias"
    bk.mkdir(exist_ok=True)
    (bk / time.strftime("plantillas_%Y%m%d_%H%M%S.md")).write_text(CON.leer("plantillas.md"), encoding="utf-8")
    texto = pre.rstrip() + "\n\n" + "\n\n".join(f"## {n.strip()}\n{c.strip()}" for n, c in secs if n.strip()) + "\n"
    (CON.CONOC / "plantillas.md").write_text(texto, encoding="utf-8")


def titulos_conocidos():
    tit = set()
    for nombre, cuerpo in todas_las_secciones():
        tit.add(clave_titulo(nombre))
        for linea in cuerpo.splitlines():
            if linea.strip().upper().startswith("TITULO:"):
                for alt in re.split(r"\||;", linea.split(":", 1)[1]):
                    tit.add(clave_titulo(alt))
    tit.discard("")
    return tit


def clave_titulo(t):
    t = re.sub(r"\(.*?\)|<.*?>|\".*?\"", " ", sin_acentos(t.lower()))
    ws = [w for w in re.findall(r"[a-z]{3,}", t) if w not in ("con", "del", "las", "los", "variantes")]
    return " ".join(ws[:2])


def _estilo(nombre):
    """'ECOGRAFÍA ABDOMINAL (estilo Peña)' -> ['pena']"""
    m = re.search(r"\(estilo ([^)]*)\)", nombre, flags=re.I)
    if not m:
        return None
    return [sin_acentos(x.strip().lower()) for x in re.split(r",|\by\b", m.group(1)) if x.strip()]


def _base(nombre):
    return re.sub(r"\s*\(estilo [^)]*\)", "", nombre, flags=re.I).strip().upper()


def es_del_medico(estilos, medico):
    m = sin_acentos((medico or "").lower())
    return bool(m) and any(e in m or m in e for e in estilos)


def plantillas_relevantes(dictado, medico=None, sin_estilos=False, usuario=None):
    """Solo las secciones de plantillas.md que corresponden a lo dictado (el modelo se confunde menos).
    Las secciones '(estilo X)' reemplazan a la general cuando el medico es X.
    sin_estilos: sin médico confirmado (la voz no lo reconoció con seguridad) no van las variantes de otros
    médicos, solo la plantilla general.
    Si no se reconoce el estudio, van todas las generales.
    usuario: las plantillas propias del transcriptor reemplazan a las generales del mismo nombre."""
    pre, secs = secciones_plantillas(usuario)
    d = categorias(dictado)
    if "pet" in d:
        d = {"pet"}  # el PET describe todo el cuerpo: solo su plantilla
    elegidas = []
    for nombre, cuerpo in secs:
        if d:
            tit = " ".join(linea for linea in cuerpo.splitlines() if linea.strip().upper().startswith("TITULO"))
            c = {x for x in categorias(_base(nombre) + " " + tit) if not x.startswith("pl:")} | {
                x for x in categorias(_base(nombre).split("(")[0]) if x.startswith("pl:")
            }
            if any(x in c and x not in d for x in ("tc", "pet")):
                continue  # no mezclar TC/PET con RX/ecografias
            if c and any(x in d and x not in c for x in ("tc", "pet")):
                continue  # ni RX/ecografias en una TC/PET
            organo = c - {"tc", "pet"}
            if c and not (organo & d if organo else c & d):
                continue  # la TC de otro organo no va
        elegidas.append((nombre, cuerpo))
    # estilos por medico
    propias = {_base(n) for n, _ in elegidas if _estilo(n) and es_del_medico(_estilo(n), medico)}
    final = []
    for nombre, cuerpo in elegidas:
        est = _estilo(nombre)
        if est:
            if es_del_medico(est, medico):
                final.append((nombre, cuerpo))
            elif not medico and d and not sin_estilos:
                final.append(
                    (nombre, "VARIANTE DE OTRO MÉDICO: usala solo si el dictado usa estas mismas frases.\n" + cuerpo)
                )
        elif _base(nombre) not in propias:
            final.append((nombre, cuerpo))
    return pre.rstrip() + "\n\n" + "\n\n".join(f"## {n}\n{c}" for n, c in final)


# ------------------------------------------------- titulos y lineas fijas
PALABRAS_ESTUDIO = {
    "rx",
    "tc",
    "ecografia",
    "eco",
    "mamografia",
    "doppler",
    "ecodoppler",
    "rm",
    "resonancia",
    "servicio",
    "pet",
    "densitometria",
    "angiotc",
    "angiografia",
    "colangiorresonancia",
    "uro",
    "radiografia",
    "tomografia",
    "centellograma",
    "seriada",
    "espinograma",
    "artrorresonancia",
}


def es_titulo(linea):
    """Titulo de un estudio: 'RX de Tórax (frente)', 'Ecografía Abdominal', 'TC de Tórax'..."""
    renglon = linea.strip()
    if not renglon or renglon.startswith("-") or renglon.endswith((".", ":")) or len(renglon) > 110:
        return False
    w = re.findall(r"[a-z]+", sin_acentos(renglon.lower()))
    return bool(w) and (w[0] in PALABRAS_ESTUDIO or clave_titulo(renglon) in titulos_conocidos())


_SOBRA_TITULO = re.compile(
    r"\b(?:digital|bilateral(?:es)?|con\s+prolongaciones\s+axilares|con\s+contraste|"
    r"sin\s+contraste)\b",
    re.I,
)


_SIGLAS = {"rx", "tc", "rm", "tac", "pet", "ct", "us"}


def estudio_corto(titulo):
    """'Ecografía Ginecológica Transvaginal' -> 'Eco transvaginal'; 'Mamografía Digital Bilateral con
    Prolongaciones Axilares' -> 'Mamografía'. Para la lista de casos. None si no es un estudio."""
    t = re.sub(r"\(.*?\)", "", titulo).replace("+", " ").strip(" :-")
    if "pet" in sin_acentos(t.lower()).split() or re.search(r"\bPET\s*/\s*CT\b", t, re.I):
        return "PET/CT"
    t = " ".join(_SOBRA_TITULO.sub(" ", t).split())
    w = t.split()
    if not w:
        return None
    p0 = sin_acentos(w[0].lower())
    if p0 not in PALABRAS_ESTUDIO and p0 not in ("tomografia", "radiografia", "densitometria", "centellograma"):
        return None
    if p0.startswith("mamograf"):
        return "Mamografía focalizada" if "focaliz" in sin_acentos(t.lower()) else "Mamografía"
    if p0 in ("ecografia", "eco"):
        resto = re.split(r"\s+y\s+", " ".join(w[1:]), maxsplit=1, flags=re.I)[0].split()
        resto = [x for x in resto if sin_acentos(x.lower()) not in ("de", "del", "la", "el")]
        if len(resto) > 1 and sin_acentos(resto[0].lower()) == "ginecologica":
            resto = resto[1:]
        return ("Eco " + " ".join(resto[:2]).lower()).strip() if resto else "Ecografía"
    if p0 == "tomografia":
        w, p0 = ["TC"] + w[1:], "tc"
    out = " ".join(
        [w[0].upper() if p0 in _SIGLAS else w[0]] + [x if x.isupper() and len(x) <= 4 else x.lower() for x in w[1:]]
    )
    out = out.rstrip(" ,")
    return out if len(out) <= 30 else out[:29].rstrip(" ,") + "…"


def estudios_del_informe(texto):
    """'Mamografía + Eco mamaria' con los estudios del informe, en orden y sin repetir."""
    vistos = []
    for linea in (texto or "").splitlines():
        if es_titulo(linea):
            k = estudio_corto(linea)
            if k and k not in vistos:
                vistos.append(k)
    if not vistos:
        return None
    return " + ".join(vistos[:3]) + (f" + {len(vistos) - 3} más" if len(vistos) > 3 else "")


_FIJAS: dict[str, Any] = {"mt": None, "exactas": set(), "prefijos": ()}


def es_linea_fija(linea):
    """Lineas de 'texto fijo' de las plantillas (equipo, tecnica...): no se controlan contra el dictado."""
    mt = _firma_plantillas()
    if _FIJAS["mt"] != mt:
        ex, pre = set(), []
        en_bloque = False
        for renglon in texto_todas_las_plantillas().splitlines():
            renglon = renglon.strip()
            up = sin_acentos(renglon.upper())
            if up.startswith("TEXTO FIJO"):
                en_bloque = True
                continue
            if renglon.startswith("## ") or up.startswith(
                ("PROTOCOLO NORMAL", "FRASES", "NOTAS", "VARIANTE", "COMO ELEGIR", "CIERRE", "TITULO")
            ):
                en_bloque = False
                continue
            if not en_bloque or not renglon or renglon.startswith(("-", "#", "<")) or len(renglon) < 15:
                continue
            if "<" in renglon:
                p = renglon.split("<")[0].strip()
                if len(p) >= 15:
                    pre.append(p.lower())
            else:
                ex.add(renglon.lower())
        _FIJAS.update(mt=mt, exactas=ex, prefijos=tuple(pre))
    renglon = linea.strip().lower()
    return renglon in _FIJAS["exactas"] or renglon.startswith(_FIJAS["prefijos"]) if renglon else False
