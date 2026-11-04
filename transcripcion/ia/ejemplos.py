"""Ejemplos dictado -> informe para la IA (few-shot): banco de ejemplos, selección por parecido y
referencias de estilo (informes Word sin audio).

Viene de nucleo.py (docs/refactor.md, etapa 3).
"""

import json
import os
from functools import lru_cache
import threading
from pathlib import Path
from transcripcion.texto.normalizacion import sin_acentos
from transcripcion import RAIZ
from transcripcion.conocimiento import plantillas as PL
from transcripcion.texto import palabras as PAL


AQUI = RAIZ  # carpeta del sistema (no la del paquete)


@lru_cache(maxsize=4096)
def _perfil_ejemplo(texto, claves):
    return frozenset(PL.categorias(texto, claves)), frozenset(PAL.palabras_norm(texto))


def elegir_ejemplos(dictado, banco, k=3, excluir=None, medico=None, usuario=None):
    """banco: lista de dicts {nombre, dictado, informe, usuario}. Elige los k mas parecidos.
    Con usuario, primero los del mismo transcriptor (entre los del mismo tipo de estudio); si no alcanzan se completa
    con los generales y los de otros. Los de otro transcriptor salen marcados con "ajeno": True."""
    claves = tuple(sorted(PL.claves_de_plantillas()))
    cd = PL.categorias(dictado, claves)
    pd = set(PAL.palabras_norm(dictado))
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
            sim += 0.15  # preferir informes del mismo medico
        if e.get("aprendido"):
            sim += 0.03  # y las correcciones recientes
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


DIR_REF = AQUI / "referencias"


def elegir_referencias(dictado, k=2, medico=None):
    """Informes terminados (sin audio) del mismo tipo de estudio, para copiar formato y frases."""
    if not DIR_REF.exists():
        return []
    d = PL.categorias(dictado)
    if not d:
        return []
    pd = set(PAL.palabras_norm(dictado))
    cand = []
    for f in DIR_REF.glob("*.txt"):
        t = f.read_text(encoding="utf-8")
        c = PL.categorias("\n".join(t.splitlines()[:6]))
        if not (c & d):
            continue
        jac = len(c & d) / len(c | d)
        pe = set(PAL.palabras_norm(t))
        sim = len(pd & pe) / max(1, len(pd | pe))
        if medico and sin_acentos(medico.lower()).split()[-1] in sin_acentos(f.stem.lower()):
            sim += 0.5  # informe del mismo medico
        cand.append((jac, sim, t))
    cand.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return [x[2] for x in cand[:k] if x[0] >= 0.5]


# ---------------------------------------------------------- banco de ejemplos
_BANCO_LOCK = threading.Lock()
_BANCO_CACHE = {"firma": None, "banco": []}


def cargar_banco(dir_fase1=None, dir_audios=None, dir_extra=None):
    carpetas = [
        Path(dir_fase1 or AQUI / "resultados" / "fase1" / "json"),
        Path(dir_audios or AQUI.parent / "Dataset" / "Audios_Transcripcion"),
        Path(dir_extra or AQUI / "ejemplos"),
    ]
    firma = []
    for carpeta in carpetas:
        archivos = []
        if carpeta.exists():
            with os.scandir(carpeta) as entradas:
                for e in entradas:
                    if e.is_file() and e.name.endswith((".json", ".txt")):
                        try:
                            st = e.stat()
                            archivos.append((e.name, st.st_size, st.st_mtime_ns))
                        except FileNotFoundError:
                            pass
        firma.append((str(carpeta.resolve()), tuple(sorted(archivos))))
    firma = tuple(firma)
    with _BANCO_LOCK:
        if _BANCO_CACHE["firma"] != firma:
            banco = _leer_banco(*carpetas)
            _BANCO_CACHE.update(firma=firma, banco=banco)
        return [dict(e) for e in _BANCO_CACHE["banco"]]


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
            banco.append(
                {
                    "nombre": d.name[:-12],
                    "dictado": d.read_text(encoding="utf-8-sig"),
                    "informe": inf.read_text(encoding="utf-8-sig"),
                    "aprendido": True,
                    "medico": med.read_text(encoding="utf-8").strip() if med.exists() else None,
                    "usuario": (usu.read_text(encoding="utf-8").strip() or None) if usu.exists() else None,
                }
            )
    aprendidos = {e["nombre"].split("_", 2)[-1] for e in banco if e.get("aprendido")}
    return [e for e in banco if e.get("aprendido") or e["nombre"] not in aprendidos]
