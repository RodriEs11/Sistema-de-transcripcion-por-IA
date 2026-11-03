# -*- coding: utf-8 -*-
"""
Nucleo de la fase 2: arma el prompt, llama a la IA local (Ollama), y marca
en el informe resultante los lugares que hay que revisar a mano.

Marcas que produce (en el texto: [[tipo|texto|motivo]]):
  dudoso     -> la IA no entendio bien el dictado y propone un texto
  completar  -> falta un dato que la plantilla necesita
  numero     -> numero / nivel / hora que NO aparece en el dictado
  bajaconf   -> numero que aparece en el dictado pero Whisper lo oyo con poca seguridad
  plantilla  -> frase de plantilla que el medico no dicto explicitamente (verificar que corresponda)
  verificar  -> texto que la IA escribio y no se encuentra en el dictado
"""
import difflib
import html
import json
import os
from functools import lru_cache
import re
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

from fase1_transcribir import normalizar, sin_acentos, datos_criticos
import usuarios as U

AQUI = Path(__file__).resolve().parent
CONOC = AQUI / "conocimiento"
OLLAMA = "http://localhost:11434"


def preparar_conocimiento():
    """Primera vez (repositorio recién clonado): crea conocimiento/ a partir de conocimiento.ejemplo/.
    Solo copia los archivos que faltan; nunca pisa los que ya existen.
    La llaman los puntos de entrada (servidor, informe, aprender, importar_informes) al arrancar, no la
    importación del módulo (docs/refactor.md, etapa 1)."""
    ejemplo = AQUI / "conocimiento.ejemplo"
    if not ejemplo.is_dir():
        return
    for f in ejemplo.rglob("*"):
        destino = CONOC / f.relative_to(ejemplo)
        if f.is_file() and f.name != "README.md" and not f.name.startswith(".") and not destino.exists():
            destino.parent.mkdir(parents=True, exist_ok=True)
            destino.write_bytes(f.read_bytes())


# ------------------------------------------------------------- conocimiento
def leer(nombre):
    return (CONOC / nombre).read_text(encoding="utf-8-sig")


def texto_todas_las_plantillas():
    """plantillas.md general + las plantillas propias de cada transcriptor. Sirve para los controles (frases de
    plantilla, texto fijo, estudios conocidos): una frase de la plantilla de cualquiera es frase de plantilla."""
    partes = [leer("plantillas.md")]
    for clave in U.claves_con_carpeta():
        t = U.leer_archivo(clave, "plantillas.md")
        if t.strip():
            partes.append(t)
    return "\n\n".join(partes)


def _firma_plantillas():
    fs = [CONOC / "plantillas.md"] + [U.CARPETA / c / "plantillas.md" for c in U.claves_con_carpeta()]
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
    for l in texto_todas_las_plantillas().splitlines():
        l = l.strip()
        if l.startswith("-") and "<" not in l and "|" not in l and "/  -" not in l:
            out.add(l)
    return out


def categorias(texto, claves=None):
    t = sin_acentos(texto.lower())
    c = set()
    if re.search(r"\bmamm?(a|as|o|ografia|aria)\b|birads|bi-rads|birrad|\bacr\b", t): c.add("mama")
    if re.search(r"transvag|trasvag|atrapag|utero|endometr|ovario", t): c.add("gine")
    if re.search(r"tiroid", t): c.add("tiroides")
    if re.search(r"espinograma|colum|colonia\s+(?:lumb|lomb|cerv|dors)|vertebr|lumbo|lombo|cervical", t): c.add("columna")
    if re.search(r"torax|torads|pulmon|costofren", t): c.add("torax")
    if re.search(r"\bmanos?\b|muneca|hombro|rodilla|cadera|\bpies?\b|brazo|codo|tobillo", t): c.add("osteo")
    if re.search(r"\btc\b|tomograf|\btomo\b|\bte ce\b|tomografo", t): c.add("tc")
    if re.search(r"\bpet\b|captacion|\bfdg\b|\bsuv\b|radiofarmaco", t): c.add("pet")
    # estudios agregados en plantillas.md (ej. "ECOGRAFÍA ABDOMINAL" -> "abdominal")
    palabras = set(re.findall(r"[a-z]{5,}", t))
    for clave in claves_de_plantillas() if claves is None else claves:
        if clave in palabras or difflib.get_close_matches(clave, list(palabras), n=1, cutoff=0.85):
            c.add("pl:" + clave)
    return c


GENERICAS = {"ecografia", "mamografia", "estudio", "digital", "bilateral", "frente", "perfil", "ambas", "ambos",
             "derecha", "derecho", "izquierda", "izquierdo", "osteoarticular", "orden", "cierre", "informe",
             "columna", "espinograma", "torax", "mamaria", "transvaginal", "ginecologica", "tiroidea", "cervical",
             "dorsal", "lumbosacra", "dorsolumbar", "manos", "muneca", "hombros", "rodillas", "caderas", "brazo",
             "region", "texto", "comun", "tomografia", "partes", "blandas"}


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
    pre, secs = _partir_secciones(leer("plantillas.md"))
    propias = secciones_de_usuario(usuario)
    if propias:
        por_clave = {_clave_seccion(n): (n, c) for n, c in propias}
        secs = [por_clave.pop(_clave_seccion(n), (n, c)) for n, c in secs]
        secs += list(por_clave.values())
    return pre, secs


def todas_las_secciones():
    """Las generales y las de todos los transcriptores (para reconocer estudios y títulos)."""
    secs = list(_partir_secciones(leer("plantillas.md"))[1])
    for clave in U.claves_con_carpeta():
        secs += secciones_de_usuario(clave)
    return secs


def secciones_con_origen(usuario=None):
    """Para el editor de plantillas: cada sección con su origen.
    origen: 'general' · 'propia' (cambiada solo para este transcriptor) · 'nueva' (solo existe en las suyas)."""
    generales = {_clave_seccion(n): c for n, c in _partir_secciones(leer("plantillas.md"))[1]}
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
    U.escribir_archivo(usuario, "plantillas.md", "# PLANTILLAS PROPIAS (reemplazan a la general del mismo nombre)\n\n"
                       + texto + "\n" if texto else "")


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
    cambiadas = {k: v for k, v in nuevas.items() if k not in vistas or vistas[k][1].strip() != v[1].strip()
                 or vistas[k][0] != v[0]}
    borradas = [k for k in vistas if k not in nuevas]
    if not cambiadas and not borradas:
        return {"generales": 0, "propias": 0, "sin_cambios": True}
    _, generales = _partir_secciones(leer("plantillas.md"))
    gen = {_clave_seccion(n): (n, c) for n, c in generales}
    propias = {_clave_seccion(n): (n, c) for n, c in secciones_de_usuario(usuario)}
    if destino == "todos":
        orden = [k for k in gen if k not in borradas]
        for k, v in cambiadas.items():
            gen[k] = v
            if k not in orden:
                orden.append(k)
            propias.pop(k, None)              # ya es la general: deja de ser propia
        for k in borradas:
            gen.pop(k, None)
            propias.pop(k, None)
        guardar_secciones([gen[k] for k in orden])
    else:
        for k, v in cambiadas.items():
            if k in gen and gen[k][1].strip() == v[1].strip() and gen[k][0] == v[0]:
                propias.pop(k, None)          # quedó igual a la general
            else:
                propias[k] = v
        for k in borradas:
            if k in propias:
                propias.pop(k)                # borrar la propia = volver a la general (si existe)
    if usuario:
        guardar_secciones_usuario(usuario, list(propias.values()))
    return {"generales": len(cambiadas) + len(borradas) if destino == "todos" else 0,
            "propias": len(cambiadas) + len(borradas) if destino == "mio" else 0, "sin_cambios": False,
            "no_borradas": [vistas[k][0] for k in borradas if destino == "mio" and k in gen]}


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
    bk = CONOC / "copias"
    bk.mkdir(exist_ok=True)
    (bk / time.strftime("plantillas_%Y%m%d_%H%M%S.md")).write_text(leer("plantillas.md"), encoding="utf-8")
    texto = pre.rstrip() + "\n\n" + "\n\n".join(f"## {n.strip()}\n{c.strip()}" for n, c in secs if n.strip()) + "\n"
    (CONOC / "plantillas.md").write_text(texto, encoding="utf-8")


def titulos_conocidos():
    tit = set()
    for nombre, cuerpo in todas_las_secciones():
        tit.add(_clave_titulo(nombre))
        for l in cuerpo.splitlines():
            if l.strip().upper().startswith("TITULO:"):
                for alt in re.split(r"\||;", l.split(":", 1)[1]):
                    tit.add(_clave_titulo(alt))
    tit.discard("")
    return tit


def _clave_titulo(t):
    t = re.sub(r"\(.*?\)|<.*?>|\".*?\"", " ", sin_acentos(t.lower()))
    ws = [w for w in re.findall(r"[a-z]{3,}", t) if w not in ("con", "del", "las", "los", "variantes")]
    return " ".join(ws[:2])


def estudios_sin_plantilla(informe):
    """Titulos del informe que no corresponden a ninguna plantilla conocida."""
    conocidos = titulos_conocidos()
    ls = [l.strip() for l in texto_limpio(informe).splitlines()]
    out = []
    for i, l in enumerate(ls):
        low = sin_acentos(l.lower())
        if not l or l.startswith("-") or l.endswith((".", ":")) or low.startswith(LINEAS_FIJAS + ("categorizacion", "nota")):
            continue
        if es_linea_fija(l) or l.rstrip(":") in NEGRITA_EXACTAS:
            continue                    # texto fijo o subtitulo (Tórax / Abdomen / Pelvis)
        rodeada = (i == 0 or not ls[i - 1]) and (i + 1 >= len(ls) or not ls[i + 1])
        if not (es_titulo(l) or rodeada):
            continue
        clave = _clave_titulo(l)
        if not clave or (low.startswith("rx ") and "rx osteoarticular" in " ".join(n.lower() for n, _ in
                                                                              todas_las_secciones())):
            continue                    # cualquier RX de una region usa la plantilla osteoarticular
        if low.startswith("tc ") and any(n.lower().startswith("tc osteo") or "texto común" in n.lower()
                                         for n, _ in todas_las_secciones()):
            continue                    # cualquier TC usa el texto comun de tomografia
        if not any(clave == k or clave.split()[0] == k.split()[0] and
                   (len(clave.split()) == 1 or len(k.split()) == 1 or clave.split()[1][:4] == k.split()[1][:4])
                   for k in conocidos):
            out.append(l)
    return out


@lru_cache(maxsize=4096)
def _perfil_ejemplo(texto, claves):
    return frozenset(categorias(texto, claves)), frozenset(_palabras_norm(texto))


def elegir_ejemplos(dictado, banco, k=3, excluir=None, medico=None, usuario=None):
    """banco: lista de dicts {nombre, dictado, informe, usuario}. Elige los k mas parecidos.
    Con usuario, primero los del mismo transcriptor (entre los del mismo tipo de estudio); si no alcanzan se completa
    con los generales y los de otros. Los de otro transcriptor salen marcados con "ajeno": True."""
    claves = tuple(sorted(claves_de_plantillas()))
    cd = categorias(dictado, claves)
    pd = set(_palabras_norm(dictado))
    cand = []
    for e in banco:
        if not e["informe"].strip() or e["dictado"] == dictado:
            continue
        if excluir and (e["nombre"] == excluir or e["nombre"].endswith("_" + excluir)):
            continue
        ce, pe = _perfil_ejemplo(e["dictado"], claves)
        jac = len(cd & ce) / len(cd | ce) if (cd | ce) else 0
        sim = len(pd & pe) / len(pd | pe) if (pd | pe) else 0
        if medico and e.get("medico") == medico:
            sim += 0.15                     # preferir informes del mismo medico
        if e.get("aprendido"):
            sim += 0.03                     # y las correcciones recientes
        cand.append((jac, sim, e))
    if not usuario:
        cand.sort(key=lambda x: (x[0], x[1]), reverse=True)
        return [c[2] for c in cand[:k]]
    # los que mejor coinciden en el tipo de estudio primero (como siempre); dentro de ese grupo, los propios antes
    # que los demás. Después, el resto con el mismo criterio.
    tope = max((c[0] for c in cand), default=0)
    def orden(c):
        jac, sim, e = c
        return (jac >= tope - 1e-9, e.get("usuario") == usuario, jac, sim)
    cand.sort(key=orden, reverse=True)
    out = []
    for _, _, e in cand[:k]:
        if e.get("usuario") and e["usuario"] != usuario:
            e = dict(e, ajeno=True)
        out.append(e)
    return out


# ------------------------------------------------------------------ prompt
SISTEMA = """Sos un asistente de transcripción médica de un servicio de diagnóstico por imágenes de Argentina.
Recibís el DICTADO de un médico (texto generado por un reconocedor de voz, con errores) y escribís el INFORME FINAL
exactamente con el formato de las plantillas del servicio.

REGLAS:
1. Usá las plantillas y frases habituales de abajo, palabra por palabra, siempre que correspondan.
2. Todo hallazgo, medida, número, lado (derecho/izquierdo), hora (H12) o nivel (L5-S1) sale SOLO del dictado.
   Nunca inventes datos. Si un dato que la plantilla necesita no fue dictado, escribí [[COMPLETAR: qué falta]].
3. El reconocedor de voz deforma palabras. Corregilas usando el vocabulario de las plantillas.
   Si no estás seguro de qué quiso decir el médico, escribí tu mejor propuesta así: [[?texto propuesto]].
4. No incluyas el nombre del paciente ni comentarios del médico dirigidos al transcriptor.
5. Respondé SOLO con el informe, sin explicaciones, sin markdown, sin ```.
6. Nunca escribas "protocolo normal" como texto: reemplazalo por las viñetas del PROTOCOLO NORMAL de la plantilla.

FORMATO:
- Título de cada estudio en su propia línea, luego una línea en blanco, luego las viñetas que empiezan con "-" (sin espacio).
- Línea en blanco entre estudios. Último renglón: "Lo saluda atte."

===== PLANTILLAS =====
{plantillas}

===== CÓMO DICTAN =====
{reglas}
"""


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
        d = {"pet"}                         # el PET describe todo el cuerpo: solo su plantilla
    elegidas = []
    for nombre, cuerpo in secs:
        if d:
            tit = " ".join(l for l in cuerpo.splitlines() if l.strip().upper().startswith("TITULO"))
            c = {x for x in categorias(_base(nombre) + " " + tit) if not x.startswith("pl:")} | \
                {x for x in categorias(_base(nombre).split("(")[0]) if x.startswith("pl:")}
            if any(x in c and x not in d for x in ("tc", "pet")):
                continue                    # no mezclar TC/PET con RX/ecografias
            if c and any(x in d and x not in c for x in ("tc", "pet")):
                continue                    # ni RX/ecografias en una TC/PET
            organo = c - {"tc", "pet"}
            if c and not (organo & d if organo else c & d):
                continue                    # la TC de otro organo no va
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
                final.append((nombre, "VARIANTE DE OTRO MÉDICO: usala solo si el dictado usa estas mismas frases.\n"
                              + cuerpo))
        elif _base(nombre) not in propias:
            final.append((nombre, cuerpo))
    return pre.rstrip() + "\n\n" + "\n\n".join(f"## {n}\n{c}" for n, c in final)


DIR_REF = AQUI / "referencias"


def elegir_referencias(dictado, k=2, medico=None):
    """Informes terminados (sin audio) del mismo tipo de estudio, para copiar formato y frases."""
    if not DIR_REF.exists():
        return []
    d = categorias(dictado)
    if not d:
        return []
    pd = set(_palabras_norm(dictado))
    cand = []
    for f in DIR_REF.glob("*.txt"):
        t = f.read_text(encoding="utf-8")
        c = categorias("\n".join(t.splitlines()[:6]))
        if not (c & d):
            continue
        jac = len(c & d) / len(c | d)
        pe = set(_palabras_norm(t))
        sim = len(pd & pe) / max(1, len(pd | pe))
        if medico and sin_acentos(medico.lower()).split()[-1] in sin_acentos(f.stem.lower()):
            sim += 0.5                      # informe del mismo medico
        cand.append((jac, sim, t))
    cand.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return [x[2] for x in cand[:k] if x[0] >= 0.5]


def reglas_de(usuario=None):
    """reglas_dictado.md general + las reglas propias del transcriptor (se suman; si se contradicen, valen las suyas)."""
    reglas = leer("reglas_dictado.md")
    propias = U.leer_archivo(usuario, "reglas_dictado.md").strip() if usuario else ""
    if propias:
        reglas = (reglas.rstrip() + "\n\n===== REGLAS PROPIAS DE ESTE TRANSCRIPTOR "
                  "(si contradicen a las de arriba, valen estas) =====\n" + propias + "\n")
    return reglas


def armar_mensajes(dictado, ejemplos, medico=None, sin_estilos=False, usuario=None):
    """usuario: transcriptor con cuyo estilo se arma el informe (plantillas, notas, reglas y correcciones propias)."""
    sis = SISTEMA.format(plantillas=plantillas_relevantes(dictado, medico, sin_estilos, usuario), reglas=reglas_de(usuario))
    # referencias: solo si los ejemplos con dictado no cubren bien este tipo de estudio
    d = categorias(dictado)
    cubre = max((len(d & categorias(e["dictado"])) / len(d | categorias(e["dictado"])) for e in ejemplos),
                default=0) if d else 1
    if cubre < 1:
        refs = elegir_referencias(dictado, medico=medico)
        if refs:
            sis += ("\n===== INFORMES DE REFERENCIA DE ESTE TIPO DE ESTUDIO (sin dictado) =====\n"
                    "Usalos para copiar el formato, el texto fijo y el estilo de las frases. "
                    "NO copies sus hallazgos ni sus medidas: todo hallazgo sale del dictado.\n\n"
                    + "\n\n----------\n\n".join(refs) + "\n")
    notas = notas_medico(medico, usuario) if medico else ""
    if notas.strip():
        sis += f"\n===== CÓMO DICTA ESTE MÉDICO ({medico}) =====\n{notas.strip()}\n"
    corr = CONOC / "correcciones_aprendidas.md"
    if corr.exists() and corr.read_text(encoding="utf-8").count("\n- ") > 0:
        sis += "\n===== CORRECCIONES FRECUENTES DEL TRANSCRIPTOR =====\n" + corr.read_text(encoding="utf-8")
    propias = U.leer_archivo(usuario, "correcciones_aprendidas.md") if usuario else ""
    if propias.count("\n- ") > 0:
        sis += "\n===== CORRECCIONES FRECUENTES DE ESTE TRANSCRIPTOR =====\n" + propias
    if any(e.get("ajeno") for e in ejemplos):
        sis += ("\nAlgunos ejemplos son de OTRO transcriptor (lo dice antes del dictado): usalos para entender cómo "
                "dicta el médico, pero NO copies su formato ni sus frases si las plantillas dicen otra cosa.\n")
    msgs = [{"role": "system", "content": sis}]
    for e in ejemplos:
        msgs.append({"role": "user", "content": ("DICTADO (ejemplo de otro transcriptor: solo para entender el "
                                                 "dictado):\n" if e.get("ajeno") else "DICTADO:\n") + e["dictado"]})
        msgs.append({"role": "assistant", "content": e["informe"].strip()})
    msgs.append({"role": "user", "content": "DICTADO:\n" + dictado})
    return msgs


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
    txt = ordenar_estudios(txt)
    if metricas is not None:
        for clave in ('total_duration', 'load_duration', 'prompt_eval_duration', 'eval_duration'):
            valor = r.get(clave)
            if isinstance(valor, (int, float)) and not isinstance(valor, bool) and valor >= 0:
                metricas[clave + '_s'] = valor / 1_000_000_000
        for clave in ('prompt_eval_count', 'eval_count'):
            if isinstance(r.get(clave), int):
                metricas[clave] = r[clave]
    return txt, time.perf_counter() - t0, r.get("prompt_eval_count"), r.get("eval_count")


# ----------------------------------------------------------- marcas
NUM_RE = re.compile(r"(?<![A-Za-z0-9.,])(\d+(?:[.,]\d+)?)")
COD_RE = re.compile(r"\b([HCDLST]\d{1,2}(?:-[CDLS]\d{1,2})?)\b")
LINEAS_FIJAS = ("hemos obtenido", "lo saluda")
IGNORAR_TITULO = {"digital", "bilateral", "prolongaciones", "axilares", "ginecologica", "ambas", "ambos",
                  "frente", "perfil", "oblicuo", "tecnica", "derecha", "derecho", "izquierda", "izquierdo"}


def _palabras_norm(t):
    return re.findall(r"[a-z]{4,}", sin_acentos(t.lower()))


ESTRUCTURALES = {"dimensiones", "uterinas", "longitudinal", "anteroposterior", "transverso",
                 "transversal", "endometrio", "espesor", "ovario", "derecho", "izquierdo", "mide",
                 "lobulo", "istmo", "categorizacion", "conjunta", "central", "ecogenico"}


def palabras_estructurales():
    """Rotulos de las plantillas que el medico no dicta ('Dimensiones uterinas: Longitudinal...')."""
    return ESTRUCTURALES


def soporte(linea, vocab_dictado):
    """Fraccion de palabras de contenido de la linea que aparecen (aprox.) en el dictado."""
    ignorar = palabras_estructurales() | {"como", "para", "sobre", "ambas", "ambos", "nivel"}
    ps = [p for p in _palabras_norm(linea) if p not in ignorar]
    if not ps:
        return 1.0
    ok = 0
    for p in ps:
        if p in vocab_dictado or difflib.get_close_matches(p, vocab_dictado, n=1, cutoff=0.7):
            ok += 1
    return ok / len(ps)


# ------------------------------------------- explicacion de cada marca
# Cada marca lleva un motivo concreto ("Dictado: 12 / Informe: 2") en vez de uno generico.
STOP_ALINEAR = {"como", "para", "sobre", "entre", "desde", "hasta", "este", "esta", "estos", "estas", "tiene",
                "presenta", "pero", "porque", "cual", "cuales", "donde", "cuando", "nivel", "ambas", "ambos"}
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
    return c[:2] == t[:2] and abs(len(c) - len(t)) <= 3 and \
        difflib.SequenceMatcher(a=c, b=t).ratio() >= 0.82


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
    for t in toks[max(0, a - 6): b + 7]:
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
    plantilla = frases_de_plantilla()
    norm_dict = normalizar(dictado)
    nums_dict = set(re.findall(r"(?<![a-z0-9.])\d+(?:\.\d+)?", norm_dict))
    cods_dict = set(re.findall(r"\b[hcdlst]\d{1,2}(?:[cdls]\d{1,2})?\b", norm_dict))
    vocab = set(_palabras_norm(dictado))
    toks = toks_dictado(norm_dict)
    bajos = {}
    for w in (palabras_whisper or []):
        if w["conf"] < 0.6:
            for x in re.findall(r"\d+(?:\.\d+)?", normalizar(w["p"])):
                bajos[x] = min(bajos.get(x, 1.0), w["conf"])

    salida = []
    for linea in informe.splitlines():
        segs = []
        l = linea.rstrip()
        if re.match(r"(?i)^-\s*(es un |un )?protocolo( normal)?\.?$", l.strip()):
            salida.append({"segs": [("[COMPLETAR: protocolo normal de este estudio]", "completar",
                                     "La IA escribió «protocolo normal» sin el texto: falta la plantilla de este "
                                     "estudio. Escribí las viñetas del protocolo normal")],
                           "linea": None, "titulo": False})
            continue
        low = sin_acentos(l.lower()).strip()
        fija = low.startswith(LINEAS_FIJAS) or not l.strip() or es_linea_fija(l)
        es_titulo_l = es_titulo(l)
        # 1) marcas de la IA
        partes = re.split(r"(\[\[.*?\]\])", l)
        for p in partes:
            m = re.match(r"\[\[(COMPLETAR:?|\?)\s*(.*?)\]\]$", p, flags=re.S)
            if m:
                if m.group(1).startswith("COMPLETAR"):
                    segs.append(("[COMPLETAR: " + m.group(2) + "]", "completar",
                                 f"Falta: {m.group(2).strip() or 'un dato'}. No se dictó: completalo escuchando "
                                 "el audio o borralo si no corresponde"))
                else:
                    segs.append((m.group(2), "dudoso", f"La IA no entendió bien esta parte y propone «{m.group(2)}». "
                                                       "Escuchá el audio para confirmarlo"))
                continue
            if fija or not p:
                segs.append((p, None, None)); continue
            # 2) numeros y codigos
            pos = 0
            for mm in re.finditer(r"\b[HCDLST]\d{1,2}(?:-[CDLS]\d{1,2})?\b|(?<![A-Za-z0-9.,])\d+(?:[.,]\d+)?", p):
                tok = mm.group(0)
                if pos < mm.start():
                    segs.append((p[pos:mm.start()], None, None))
                key = tok.lower().replace("-", "").replace(",", ".")
                if key[0].isalpha():
                    ok = key in cods_dict
                else:
                    ok = key in nums_dict
                if not ok:
                    segs.append((tok, "numero", motivo_numero(tok, l, toks)))
                elif key in bajos:
                    segs.append((tok, "bajaconf", f"Whisper oyó «{tok}» con poca seguridad "
                                                  f"(confianza {round(bajos[key] * 100)} %): escuchalo para confirmar"))
                else:
                    segs.append((tok, None, None))
                pos = mm.end()
            if pos < len(p):
                segs.append((p[pos:], None, None))
        # 3) soporte de la linea completa en el dictado
        tipo_linea = motivo_l = None
        if es_titulo_l and not fija:
            # el tipo de estudio del titulo tiene que poder reconocerse en el dictado
            sin_rotulos = " ".join(p for p in _palabras_norm(l) if p not in IGNORAR_TITULO)
            if sin_rotulos and soporte(sin_rotulos, vocab) < 0.5:
                tipo_linea = "verificar"
                motivo_l = motivo_linea(tipo_linea, l, vocab, norm_dict, es_tit=True)
        elif l.startswith("-") and not fija:
            sop = soporte(re.sub(r"\[\[.*?\]\]", "", l), vocab)
            if sop < 0.5:
                tipo_linea = "plantilla" if l in plantilla else "verificar"
                motivo_l = motivo_linea(tipo_linea, l, vocab, norm_dict)
        salida.append({"segs": segs, "linea": tipo_linea, "motivo": motivo_l,
                       "titulo": bool(es_titulo_l and not fija)})
    controles_clinicos(salida, norm_dict, formas_originales(dictado))
    control_palabras_raras(salida)
    return salida


# Palabras que nunca aparecieron en tus informes (ej. "para el horario" copiado de Whisper).
# Con pocos informes de referencia daria demasiadas falsas alarmas: se activa sola al llegar a UMBRAL.
UMBRAL_VOCABULARIO = 150
_VOCAB = {"n": None, "set": None}
MOTIVO_RARA = "Palabra que no aparece en tus informes anteriores: posible error de Whisper copiado"


def vocabulario_informes():
    if _VOCAB["set"] is None:
        banco = cargar_banco()
        _VOCAB["n"] = len(banco)
        v = set(re.findall(r"[a-záéíóúñü]+", texto_todas_las_plantillas().lower()))
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
        ln["segs"] = _partir(ln["segs"], r"[A-Za-zÁÉÍÓÚáéíóúñÑüÜ]{3,}", "dudoso", MOTIVO_RARA,
                             lambda m: m.group(0).lower() not in v)


# ------------------------------------------------- controles clinicos extra
# Terminos que cambian el sentido clinico: si la IA los escribe tienen que haberse
# dictado CERCA del hallazgo (alrededor de sus medidas / hora / nivel).
TERMINOS_CLAVE = ("solid", "quist", "liquid", "ovalad", "redond", "irregular", "circunscrip", "espicul",
                  "lobulad", "anecoic", "hiperecog", "isoecog", "hipoecog", "calcific", "sombra",
                  "vasculariz", "sospech", "benign", "mioma", "intramural", "subseros", "submucos",
                  "derech", "izquierd", "bilateral", "denso", "densa", "asimetr", "persist", "estable",
                  "sin cambios", "periareolar", "periferic")
# como suele deformar Whisper algunos terminos ("impecogénica", "el otro" = el otro ovario)
VARIANTES_WHISPER = {"hipoecog": ("cogenic", "ecogen"), "periareolar": ("perio", "areol"),
                     "izquierd": ("otro",), "derech": ("otro",)}
MOTIVO_CONTEXTO = "No se dictó junto a este hallazgo: verificar que corresponda"


def _bi_rads_dictados(nd):
    nd = re.sub(r"\bbirr?astre\w*", "birads 3", nd)          # "un birrastre" = Bi-Rads 3
    pat = r"(?:bi\W?rr?ads?\w*|vrads?\w*|birra\w*|ponemos un|poner un|ponemos|es un)\W{0,3}(\d)\b"
    return set(re.findall(pat, nd))


def _acr_dictados(nd):
    return set(re.findall(r"\b(?:acr|acdr|acrd?|crd?|r)\W{0,3}([abcd])\b", nd)) | \
        set(re.findall(r"\bacr([abcd])\b", nd))


def _partir(segs, patron, tipo, motivo, filtro=lambda m: True):
    """Marca dentro de los segmentos sin marca las coincidencias de 'patron'.
    'motivo' puede ser un texto o una funcion que recibe la coincidencia."""
    out = []
    for t, tp, mot in segs:
        if tp:
            out.append((t, tp, mot)); continue
        pos = 0
        for m in re.finditer(patron, t, flags=re.I):
            if not filtro(m):
                continue
            g = m.span(1) if m.groups() else m.span()
            if pos < g[0]:
                out.append((t[pos:g[0]], None, None))
            out.append((t[g[0]:g[1]], tipo, motivo(m) if callable(motivo) else motivo))
            pos = g[1]
        if pos < len(t):
            out.append((t[pos:], None, None))
    return out


# familias de terminos: si el informe dice "quístico" y cerca se dicto "sólido", se muestra "sólido"
FAMILIAS = (("solid", "quist", "liquid", "anecoic", "mixt"),
            ("anecoic", "hiperecog", "isoecog", "hipoecog", "heterog"),
            ("ovalad", "redond", "irregular", "lobulad"),
            ("circunscrip", "espicul", "irregular", "lobulad", "microlobul"),
            ("derech", "izquierd", "bilateral"),
            ("intramural", "subseros", "submucos"),
            ("benign", "sospech"),
            ("persist", "estable", "sin cambios", "nuev"))


def _y(xs):
    xs = list(xs)
    return xs[0] if len(xs) == 1 else ", ".join(xs[:-1]) + " y " + xs[-1]


def controles_clinicos(salida, nd, formas=None):
    formas = formas or {}
    toks = nd.split()
    birads = _bi_rads_dictados(nd)
    acr = _acr_dictados(nd)
    for ln in salida:
        texto = "".join(t for t, _, _ in ln["segs"])
        low = sin_acentos(texto.lower())
        # Bi-Rads: el numero tiene que estar dictado como Bi-Rads ("le ponemos un 3", "birads 3")
        if "bi-rads" in low or "birads" in low:
            dict_br = ("Dictado: Bi-Rads " + _y(sorted(birads))) if birads else \
                "No encontré un Bi-Rads en el dictado (suele estar al final)"
            nuevos = []
            for t, tp, mot in ln["segs"]:
                if re.fullmatch(r"\d", t.strip()) and t.strip() not in birads:
                    nuevos.append((t, "numero", (dict_br + f" / Informe: Bi-Rads {t.strip()}") if birads
                                   else dict_br + f" · Informe: Bi-Rads {t.strip()}"))
                elif re.fullmatch(r"\d", t.strip()) and tp == "numero":
                    nuevos.append((t, None, None))      # dictado como Bi-Rads ("un birrastre" = 3)
                else:
                    nuevos.append((t, tp, mot))
            ln["segs"] = nuevos
        # ACR: la letra tiene que estar dictada
        if re.search(r"\bacr\b", low):
            dict_acr = ("Dictado: ACR " + _y(sorted(x.upper() for x in acr))) if acr else \
                "No encontré la categoría ACR en el dictado"
            ln["segs"] = _partir(ln["segs"], r"\bACR:?\s*([ABCD])\b", "numero",
                                 lambda m: dict_acr + (" / " if acr else " · ") + f"Informe: ACR {m.group(1)}",
                                 lambda m: m.group(1).lower() not in acr)
        # descripciones decisivas cerca de las medidas del hallazgo
        if not texto.startswith("-"):
            continue
        anclas = [t.strip().lower().replace(",", ".") for t, tp, _ in ln["segs"]
                  if tp in (None, "bajaconf") and re.fullmatch(r"\s*(\d+(?:[.,]\d+)?|[HhCcDdLl]\d{1,2})\s*", t)]
        anclas = [a.replace("-", "") for a in anclas]
        idx = [i for i, w in enumerate(toks) if w.strip(".,;:") in anclas]
        if not idx:
            continue
        orden = []
        for i in idx:
            orden += [re.sub(r"[^a-z]", "", w) for w in toks[max(0, i - 30): i + 25]]
        orden = [w for w in dict.fromkeys(orden) if w]
        ventana = set(orden)

        def falta(m):
            w = sin_acentos(m.group(0).lower())
            raiz = next((r for r in TERMINOS_CLAVE if w.startswith(r)), None)
            if not raiz:
                return False
            if any(v.startswith(raiz) for v in ventana):
                return False
            if any(x in v for x in VARIANTES_WHISPER.get(raiz, ()) for v in ventana):
                return False
            return not difflib.get_close_matches(w, list(ventana), n=1, cutoff=0.7)

        def motivo(m):
            w = sin_acentos(m.group(0).lower())
            raiz = next((r for r in TERMINOS_CLAVE if w.startswith(r)), "")
            fam = {r for f in FAMILIAS if raiz in f for r in f} - {raiz}
            otros = [formas.get(v, v) for v in orden if any(v.startswith(r) for r in fam)]
            txt = f"Informe: «{m.group(0)}» · no se dictó junto a este hallazgo"
            if otros:
                txt += ". Cerca se dictó: " + ", ".join(dict.fromkeys(otros[:4]))
            return txt + ". Verificá que corresponda"
        ln["segs"] = _partir(ln["segs"], r"[A-Za-zÁÉÍÓÚáéíóúñÑüÜ]{5,}", "verificar", motivo, falta)


def texto_limpio(informe):
    """Informe sin las marcas [[...]] (para comparar con el informe real)."""
    t = re.sub(r"\[\[COMPLETAR:?\s*(.*?)\]\]", r"[COMPLETAR: \1]", informe)
    return re.sub(r"\[\[\?\s*(.*?)\]\]", r"\1", t)


MOTIVO_LINEA = {"plantilla": "Frase de plantilla que no se dictó explícitamente: confirmá que corresponde",
                "verificar": "La IA escribió esta línea y no se encuentra en el dictado: verificar"}


def buscar_tiempo(texto, palabras):
    """Segundo del audio donde aparece (aprox.) este texto en el dictado."""
    if not palabras:
        return None
    nt = normalizar(texto)
    claves = re.findall(r"\d+(?:\.\d+)?", nt) or [p for p in _palabras_norm(texto) if p not in ESTRUCTURALES][:3]
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


# ---------------------------------------------------------- banco de ejemplos
_BANCO_LOCK = threading.Lock()
_BANCO_CACHE = {"firma": None, "banco": []}


def cargar_banco(dir_fase1=None, dir_audios=None, dir_extra=None):
    carpetas = [Path(dir_fase1 or AQUI/'resultados'/'fase1'/'json'),
                Path(dir_audios or AQUI.parent/'Dataset'/'Audios_Transcripcion'),
                Path(dir_extra or AQUI/'ejemplos')]
    firma = []
    for carpeta in carpetas:
        archivos = []
        if carpeta.exists():
            with os.scandir(carpeta) as entradas:
                for e in entradas:
                    if e.is_file() and e.name.endswith(('.json','.txt')):
                        try:
                            st = e.stat()
                            archivos.append((e.name, st.st_size, st.st_mtime_ns))
                        except FileNotFoundError:
                            pass
        firma.append((str(carpeta.resolve()), tuple(sorted(archivos))))
    firma = tuple(firma)
    with _BANCO_LOCK:
        if _BANCO_CACHE['firma'] != firma:
            banco = _leer_banco(*carpetas)
            _BANCO_CACHE.update(firma=firma, banco=banco)
        return [dict(e) for e in _BANCO_CACHE['banco']]


def _leer_banco(dir_fase1=None, dir_audios=None, dir_extra=None):
    """Pares dictado -> informe real que la IA usa como ejemplo.
    - los 35 de la fase 1 (dictado de Whisper + tu .txt)
    - y los que agregues en la carpeta 'ejemplos' como  NOMBRE.dictado.txt + NOMBRE.informe.txt"""
    dir_fase1 = Path(dir_fase1 or AQUI / "resultados" / "fase1" / "json")
    dir_audios = Path(dir_audios or AQUI.parent / "Dataset" / "Audios_Transcripcion")
    dir_extra = Path(dir_extra or AQUI / "ejemplos")
    banco, vistos = [], set()
    for js in sorted(dir_fase1.glob("*.json")):
        r = json.loads(js.read_text(encoding="utf-8"))
        txt = dir_audios / (js.stem + ".txt")
        inf = txt.read_text(encoding="utf-8-sig", errors="replace") if txt.exists() else ""
        dic = r["con_vocab"]["texto"]
        if inf.strip() and dic not in vistos:
            banco.append({"nombre": js.stem, "dictado": dic, "informe": inf})
            vistos.add(dic)
    for d in sorted(dir_extra.glob("*.dictado.txt")) if dir_extra.exists() else []:
        inf = d.with_name(d.name.replace(".dictado.txt", ".informe.txt"))
        if inf.exists():
            med = d.with_name(d.name.replace(".dictado.txt", ".medico.txt"))
            usu = d.with_name(d.name.replace(".dictado.txt", ".usuario.txt"))
            banco.append({"nombre": d.name[:-12], "dictado": d.read_text(encoding="utf-8-sig"),
                          "informe": inf.read_text(encoding="utf-8-sig"), "aprendido": True,
                          "medico": med.read_text(encoding="utf-8").strip() if med.exists() else None,
                          "usuario": (usu.read_text(encoding="utf-8").strip() or None) if usu.exists() else None})
    aprendidos = {e["nombre"].split("_", 2)[-1] for e in banco if e.get("aprendido")}
    return [e for e in banco if e.get("aprendido") or e["nombre"] not in aprendidos]


def liberar_ia(modelo):
    """Saca el modelo de Ollama de la placa de video (para que entre Whisper)."""
    try:
        req = urllib.request.Request(OLLAMA + "/api/generate",
                                     data=json.dumps({"model": modelo, "keep_alive": 0}).encode(),
                                     headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=30).read()
    except Exception:
        pass


# ------------------------------------------------------------- omisiones
def omisiones(dictado, informe, palabras=None):
    """Datos dictados (medidas, numeros, H12, L5-S1...) que no aparecen en el informe."""
    crudos = set(re.findall(r"\d+", dictado))
    dic = {x for x in datos_criticos(dictado)
           if not (x.isdigit() and int(x) <= 2 and x not in crudos)}   # "dos puntos", "un"
    faltan = sorted(dic - datos_criticos(texto_limpio(informe), True),
                    key=lambda x: (buscar_tiempo(x, palabras) or 0) if palabras else 0)
    out = []
    for x in faltan:
        etiqueta = x.upper() if x[0].isalpha() else x
        etiqueta = re.sub(r"^([CDLS]\d+)([CDLS]\d+)$", r"\1-\2", etiqueta)
        out.append({"dato": etiqueta, "seg": buscar_tiempo(x, palabras) if palabras else None})
    return out


# ----------------------------------------------------------------- medicos
DIR_MED = CONOC / "medicos"
_MED_LOCK = threading.RLock()


def clave_medico(nombre):
    return " ".join(sin_acentos(nombre).casefold().split())


def validar_nombre_medico(nombre):
    if not isinstance(nombre, str):
        raise ValueError("Escribí el nombre del médico.")
    nombre = " ".join(nombre.split())
    if (len(nombre) < 2 or len(nombre) > 120 or not any(c.isalpha() for c in nombre)
            or re.search(r"[^\w .,-]", nombre) or nombre.endswith(".")
            or nombre.split(".")[0].upper() in {"CON", "PRN", "AUX", "NUL", "COM1", "COM2", "COM3", "COM4",
                                                  "COM5", "COM6", "COM7", "COM8", "COM9", "LPT1", "LPT2",
                                                  "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9"}):
        raise ValueError("Usá un nombre de 2 a 120 caracteres, con letras y sin símbolos especiales ni punto final.")
    return nombre


def _archivo_medico(nombre):
    seguro = re.sub(r"[^\w .,-]", "", nombre).strip()
    return DIR_MED / f"{seguro}.md"


def lista_medicos():
    if not DIR_MED.exists():
        return []
    return sorted(p.stem for p in DIR_MED.glob("*.md"))


def notas_medico(nombre, usuario=None):
    """Notas de cómo dicta el médico. Si el transcriptor tiene las suyas, reemplazan a las generales."""
    propias = notas_propias(nombre, usuario)
    if propias is not None:
        return propias
    f = _archivo_medico(nombre) if nombre else None
    return f.read_text(encoding="utf-8") if f and f.exists() else ""


def _archivo_medico_usuario(nombre, usuario):
    return U.carpeta(usuario) / "medicos" / _archivo_medico(nombre).name


def notas_propias(nombre, usuario):
    """Notas «solo para mí» del transcriptor sobre ese médico, o None si usa las generales."""
    if not nombre or not usuario:
        return None
    f = _archivo_medico_usuario(nombre, usuario)
    return f.read_text(encoding="utf-8") if f.exists() else None


def guardar_notas_propias(nombre, usuario, notas):
    """notas=None: vuelve a usar las generales."""
    with _MED_LOCK:
        if nombre not in lista_medicos():
            raise FileNotFoundError("El médico ya no existe. Actualizá la lista.")
        f = _archivo_medico_usuario(nombre, usuario)
        if notas is None:
            f.unlink(missing_ok=True)
            return
        if not isinstance(notas, str):
            raise ValueError("Las notas deben ser texto.")
        f.parent.mkdir(parents=True, exist_ok=True)
        temporal = f.with_suffix(".md.nuevo")
        temporal.write_text(notas, encoding="utf-8")
        temporal.replace(f)


def medicos_con_notas_propias(usuario):
    d = U.carpeta(usuario) / "medicos" if usuario else None
    return sorted(p.stem for p in d.glob("*.md")) if d and d.is_dir() else []


def guardar_medico(nombre, notas, *, crear=False, original=None):
    nombre = validar_nombre_medico(nombre)
    if not isinstance(notas, str):
        raise ValueError("Las notas deben ser texto.")
    with _MED_LOCK:
        existentes = lista_medicos()
        if original is not None and original not in existentes:
            raise FileNotFoundError("El médico ya no existe. Actualizá la lista.")
        for otro in existentes:
            if clave_medico(otro) == clave_medico(nombre) and (crear or otro != (original or nombre)):
                raise FileExistsError(f"Ya existe un médico con ese nombre: {otro}.")
        DIR_MED.mkdir(parents=True, exist_ok=True)
        f = _archivo_medico(nombre)
        if original and original != nombre:
            anterior = _archivo_medico(original)
            # El renombrado también admite cambios de mayúsculas en Windows.
            anterior.rename(f)
            for clave in U.claves_con_carpeta():      # las notas propias de cada transcriptor siguen al médico
                viejo = _archivo_medico_usuario(original, clave)
                if viejo.exists():
                    viejo.rename(_archivo_medico_usuario(nombre, clave))
        temporal = f.with_suffix(".md.nuevo")
        temporal.write_text(notas, encoding="utf-8")
        temporal.replace(f)
        return nombre


def eliminar_medico(nombre):
    with _MED_LOCK:
        if nombre not in lista_medicos():
            raise FileNotFoundError("El médico ya no existe. Actualizá la lista.")
        _archivo_medico(nombre).unlink()
        for clave in U.claves_con_carpeta():
            _archivo_medico_usuario(nombre, clave).unlink(missing_ok=True)


# ------------------------------------------------- titulos y lineas fijas
PALABRAS_ESTUDIO = {"rx", "tc", "ecografia", "eco", "mamografia", "doppler", "ecodoppler", "rm", "resonancia",
                    "servicio", "pet", "densitometria", "angiotc", "angiografia", "colangiorresonancia", "uro",
                    "radiografia", "tomografia", "centellograma", "seriada", "espinograma", "artrorresonancia"}


def es_titulo(linea):
    """Titulo de un estudio: 'RX de Tórax (frente)', 'Ecografía Abdominal', 'TC de Tórax'..."""
    l = linea.strip()
    if not l or l.startswith("-") or l.endswith((".", ":")) or len(l) > 110:
        return False
    w = re.findall(r"[a-z]+", sin_acentos(l.lower()))
    return bool(w) and (w[0] in PALABRAS_ESTUDIO or _clave_titulo(l) in titulos_conocidos())


_SOBRA_TITULO = re.compile(r"\b(?:digital|bilateral(?:es)?|con\s+prolongaciones\s+axilares|con\s+contraste|"
                           r"sin\s+contraste)\b", re.I)
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
    out = " ".join([w[0].upper() if p0 in _SIGLAS else w[0]] + [x if x.isupper() and len(x) <= 4 else x.lower()
                                                                for x in w[1:]])
    out = out.rstrip(" ,")
    return out if len(out) <= 30 else out[:29].rstrip(" ,") + "…"


def estudios_del_informe(texto):
    """'Mamografía + Eco mamaria' con los estudios del informe, en orden y sin repetir."""
    vistos = []
    for l in (texto or "").splitlines():
        if es_titulo(l):
            k = estudio_corto(l)
            if k and k not in vistos:
                vistos.append(k)
    if not vistos:
        return None
    return " + ".join(vistos[:3]) + (f" + {len(vistos) - 3} más" if len(vistos) > 3 else "")


_FIJAS = {"mt": None, "exactas": set(), "prefijos": ()}


def es_linea_fija(linea):
    """Lineas de 'texto fijo' de las plantillas (equipo, tecnica...): no se controlan contra el dictado."""
    mt = _firma_plantillas()
    if _FIJAS["mt"] != mt:
        ex, pre = set(), []
        en_bloque = False
        for l in texto_todas_las_plantillas().splitlines():
            l = l.strip()
            up = sin_acentos(l.upper())
            if up.startswith("TEXTO FIJO"):
                en_bloque = True; continue
            if l.startswith("## ") or up.startswith(("PROTOCOLO NORMAL", "FRASES", "NOTAS", "VARIANTE", "COMO ELEGIR",
                                                      "CIERRE", "TITULO")):
                en_bloque = False; continue
            if not en_bloque or not l or l.startswith(("-", "#", "<")) or len(l) < 15:
                continue
            if "<" in l:
                p = l.split("<")[0].strip()
                if len(p) >= 15:
                    pre.append(p.lower())
            else:
                ex.add(l.lower())
        _FIJAS.update(mt=mt, exactas=ex, prefijos=tuple(pre))
    l = linea.strip().lower()
    return l in _FIJAS["exactas"] or l.startswith(_FIJAS["prefijos"]) if l else False


def debe_ir_en_negrita(linea, titulo, cfg):
    if not linea.strip():
        return False
    if titulo and cfg.get("negrita_titulos", True):
        return True
    if linea.strip().rstrip(":") in cfg.get("negrita_lineas_exactas", NEGRITA_EXACTAS):
        return True
    return linea.strip().startswith(tuple(cfg.get("negrita_si_empieza_con", NEGRITA_DEF)))


NEGRITA_EXACTAS = ["Tórax", "Abdomen", "Pelvis", "CONCLUSIÓN"]


NEGRITA_DEF = ["Categorización conjunta", "Se efectuó el estudio en", "Se efectuó en un equipo PET/CT",
               "Hallazgos PET/CT", "Hallazgos CT", "SERVICIO DE"]


# ---------------------------------------------------- orden de los estudios
ORDEN_MAMA = (("mamograf", 0), ("ecografia mamaria", 1), ("ginecolog", 3), ("transvaginal", 3), ("tiroid", 4))


def _rango(titulo):
    low = sin_acentos(titulo.lower())
    for clave, r in ORDEN_MAMA:
        if clave in low:
            return r
    return None


def ordenar_estudios(texto):
    """Ordena Mamografía -> Ecografía Mamaria -> Categorización -> Transvaginal -> Tiroides,
    aunque el médico (y la IA) los dicten en otro orden. Otros estudios no se tocan."""
    ls = texto.replace("\r", "").split("\n")
    cierre = []
    while ls and (not ls[-1].strip() or sin_acentos(ls[-1].strip().lower()).startswith("lo salud")):
        cierre.insert(0, ls.pop())
    bloques, pre, cat = [], [], None
    for l in ls:
        if sin_acentos(l.strip().lower()).startswith("categorizacion"):
            cat = l.strip(); continue
        if es_titulo(l):
            bloques.append([l])
        elif bloques:
            bloques[-1].append(l)
        else:
            pre.append(l)
    rangos = [_rango(b[0]) for b in bloques]
    if len(bloques) < 2 or None in rangos or rangos == sorted(rangos) and cat is None:
        return texto                                    # nada que ordenar (o no son estudios mamarios)
    orden = sorted(range(len(bloques)), key=lambda i: (rangos[i], i))
    out = list(pre)
    puesto = cat is None
    destino = max((i for i in orden if rangos[i] in (0, 1)), key=lambda i: rangos[i], default=None)
    for i in orden:
        b = list(bloques[i])
        while b and not b[-1].strip():
            b.pop()
        out += b + [""]
        if not puesto and i == destino:
            out += [cat, ""]; puesto = True
    if not puesto:
        out += [cat, ""]
    while out and not out[-1].strip():
        out.pop()
    return "\n".join(out + ([""] + [c for c in cierre if c.strip()] if cierre else []))
