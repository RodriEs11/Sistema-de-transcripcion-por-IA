# -*- coding: utf-8 -*-
"""
APRENDIZAJE: convierte tus informes revisados en ejemplos para la IA.

Como funciona:
  1. informe.bat genera Informes\\NOMBRE.docx con marcas de color.
  2. Vos lo corregis en ese mismo Word, sacas TODOS los resaltados y guardas (Ctrl+G / Ctrl+S).
  3. La proxima vez que uses informe.bat (o aprender.bat) ese Word se guarda como ejemplo:
     el dictado + tu version final. La IA los usa para los informes siguientes.
  Un Word que todavia tiene resaltados se considera "sin revisar" y se ignora.

Ademas lleva un historial (resultados\\historial.csv) con el % de palabras que tuviste
que corregir en cada informe, para ver si el sistema mejora con el tiempo.
"""
import csv
import difflib
import json
import re
import sys
import time
from pathlib import Path

import nucleo as N

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

AQUI = Path(__file__).resolve().parent
EJ = AQUI / "ejemplos"
HIST = AQUI / "resultados" / "historial.csv"
REG = EJ / "_procesados.json"


def leer_docx(ruta, titulo_ia, n_encabezado):
    from docx import Document
    d = Document(str(ruta))
    pars = d.paragraphs
    resaltados = any(r.font.highlight_color for p in pars for r in p.runs)
    textos = [p.text for p in pars]
    # empezar en el titulo (lo que haya arriba es el encabezado)
    ini = next((i for i, t in enumerate(textos) if t.strip() and t.strip() == titulo_ia.strip()), None)
    if ini is None:
        ini = next((i for i, t in enumerate(textos[n_encabezado:], n_encabezado) if t.strip()), len(textos))
    cuerpo = "\n".join(t.rstrip() for t in textos[ini:]).strip()
    return cuerpo, resaltados


def pct_corregido(ia, final):
    a = re.findall(r"\S+", ia); b = re.findall(r"\S+", final)
    sm = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
    ed = sum(max(i2 - i1, j2 - j1) for op, i1, i2, j1, j2 in sm.get_opcodes() if op != "equal")
    return ed / max(1, len(b))


def registrar_ejemplo(nombre, dictado, ia, final, clave=None, medico=None):
    """Guarda el par dictado -> informe final como ejemplo y anota el historial.
    Devuelve (clave, porcentaje_corregido)."""
    EJ.mkdir(exist_ok=True)
    HIST.parent.mkdir(parents=True, exist_ok=True)
    clave = clave or time.strftime("%Y%m%d_%H%M%S_") + nombre
    (EJ / f"{clave}.dictado.txt").write_text(dictado, encoding="utf-8")
    (EJ / f"{clave}.informe.txt").write_text(final.strip() + "\n", encoding="utf-8")
    (EJ / f"{clave}.ia.txt").write_text(N.texto_limpio(ia), encoding="utf-8")
    if medico:
        (EJ / f"{clave}.medico.txt").write_text(medico, encoding="utf-8")
    ia_sin_espacios = "\n".join(l.rstrip() for l in N.texto_limpio(ia).splitlines())
    pc = pct_corregido(ia_sin_espacios, final)
    # historial: una fila por informe (si lo volves a guardar, se reemplaza la fila)
    filas = []
    if HIST.exists():
        filas = list(csv.reader(open(HIST, encoding="utf-8-sig"), delimiter=";"))[1:]
    hoy = time.strftime("%Y-%m-%d")
    filas = [f for f in filas if not (len(f) >= 2 and f[1] == nombre and f[0].startswith(hoy))]
    filas.append([time.strftime("%Y-%m-%d %H:%M"), nombre, len(final.split()), f"{pc*100:.1f}"])
    with open(HIST, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["fecha", "informe", "palabras", "porcentaje_corregido"])
        w.writerows(filas)
    try:
        analizar_correcciones()
    except Exception as ex:
        try:
            import registro as L
            if L.log.handlers:      # dentro del servidor: al registro
                L.aviso("INFORME", f"No se pudieron analizar las correcciones repetidas: {ex}", exc=True)
            else:
                print("(no se pudieron analizar las correcciones:", ex, ")")
        except ImportError:
            print("(no se pudieron analizar las correcciones:", ex, ")")
    return clave, pc


# ------------------------------------------------ correcciones repetidas
ARCH_CORR = AQUI / "conocimiento" / "correcciones_aprendidas.md"
DATOS_INF = AQUI.parent / "Informes" / "revision" / "datos"


def _norm_tok(w):
    return w.strip(".,;:").lower()


def analizar_correcciones(minimo=2):
    """Compara lo que escribio la IA con tu version final en todos los ejemplos aprendidos.
    Las correcciones que repetiste en >= 'minimo' informes distintos se escriben en
    conocimiento/correcciones_aprendidas.md, que la IA lee en cada informe."""
    from collections import defaultdict
    cambios = defaultdict(set)
    for inf in EJ.glob("*.informe.txt"):
        clave = inf.name[:-len(".informe.txt")]
        ia_f = EJ / f"{clave}.ia.txt"
        if not ia_f.exists():                       # ejemplos viejos: buscar la salida de la IA
            nombre = clave.split("_", 2)[-1]
            viejo = DATOS_INF / f"{nombre}.informe_ia.txt"
            if not viejo.exists():
                continue
            ia_f.write_text(N.texto_limpio(viejo.read_text(encoding="utf-8")), encoding="utf-8")
        a = re.findall(r"\S+", ia_f.read_text(encoding="utf-8"))
        b = re.findall(r"\S+", inf.read_text(encoding="utf-8"))
        sm = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
        for op, i1, i2, j1, j2 in sm.get_opcodes():
            if op == "equal":
                continue
            de, a_ = " ".join(a[i1:i2]), " ".join(b[j1:j2])
            if max(i2 - i1, j2 - j1) > 12:
                continue
            if re.search(r"\d", de + a_):            # los numeros salen del dictado, no se generalizan
                continue
            if [_norm_tok(x) for x in a[i1:i2]] == [_norm_tok(x) for x in b[j1:j2]]:
                continue                              # solo puntuacion
            cambios[(op, de.strip(".,;:"), a_.strip(".,;:"))].add(clave)
    frec = sorted(((len(v), k) for k, v in cambios.items() if len(v) >= minimo), reverse=True)
    lineas = ["# CORRECCIONES QUE EL TRANSCRIPTOR HIZO VARIAS VECES (se actualiza solo; no editar)",
              "# Tenelas en cuenta, pero usalas solo si el dictado lo justifica.", ""]
    for n, (op, de, a_) in frec[:40]:
        if op == "replace":
            lineas.append(f"- La IA escribió «{de}» y el transcriptor lo cambió por «{a_}» ({n} informes).")
        elif op == "insert":
            lineas.append(f"- El transcriptor tuvo que AGREGAR «{a_}» ({n} informes).")
        else:
            lineas.append(f"- El transcriptor tuvo que BORRAR «{de}» ({n} informes).")
    ARCH_CORR.write_text("\n".join(lineas) + "\n", encoding="utf-8")
    return frec


def anotar_procesado(docx, clave):
    """Para que aprender() no vuelva a tomar un Word ya registrado."""
    reg = json.loads(REG.read_text(encoding="utf-8")) if REG.exists() else {}
    reg[str(docx)] = {"mtime": Path(docx).stat().st_mtime, "ejemplo": clave}
    REG.write_text(json.dumps(reg, ensure_ascii=False, indent=1), encoding="utf-8")


def aprender(cfg, silencioso=False):
    sal = cfg["carpeta_informes"]
    datos = sal / "revision" / "datos"
    EJ.mkdir(exist_ok=True)
    HIST.parent.mkdir(parents=True, exist_ok=True)
    reg = json.loads(REG.read_text(encoding="utf-8")) if REG.exists() else {}
    nuevos, pendientes = [], []
    for docx in sorted(sal.glob("*.docx")):
        if docx.name.startswith("~$"):
            continue
        nombre = docx.stem
        dic_f, ia_f = datos / f"{nombre}.dictado.txt", datos / f"{nombre}.informe_ia.txt"
        if not (dic_f.exists() and ia_f.exists()):
            continue
        mt = docx.stat().st_mtime
        if reg.get(str(docx), {}).get("mtime") == mt:
            continue
        ia = N.texto_limpio(ia_f.read_text(encoding="utf-8"))
        titulo = next((l for l in ia.splitlines() if l.strip()), "")
        try:
            final, resaltado = leer_docx(docx, titulo, int(cfg["lineas_vacias_para_encabezado"]))
        except Exception:
            continue  # abierto o dañado
        if resaltado or "[COMPLETAR" in final or "[REVISAR" in final:
            pendientes.append(docx.name)
            continue
        clave, pc = registrar_ejemplo(nombre, dic_f.read_text(encoding="utf-8"), ia_f.read_text(encoding="utf-8"),
                                      final, reg.get(str(docx), {}).get("ejemplo"))
        reg[str(docx)] = {"mtime": mt, "ejemplo": clave}
        nuevos.append((nombre, pc))
    REG.write_text(json.dumps(reg, ensure_ascii=False, indent=1), encoding="utf-8")

    if nuevos:
        print(f"Aprendidos {len(nuevos)} informe(s) revisado(s): " +
              ", ".join(f"{n} ({p*100:.0f}% corregido)" for n, p in nuevos))
    if pendientes and not silencioso:
        print(f"Sin revisar todavía (tienen resaltados): {', '.join(pendientes)}")
    return nuevos


def resumen():
    if not HIST.exists():
        print("Todavía no hay informes revisados en el historial.")
        return
    filas = list(csv.DictReader(open(HIST, encoding="utf-8-sig"), delimiter=";"))
    pcs = [float(f["porcentaje_corregido"]) for f in filas]
    print(f"\nHistorial: {len(pcs)} informes revisados · promedio corregido {sum(pcs)/len(pcs):.1f}%")
    if len(pcs) >= 20:
        a, b = pcs[:-10], pcs[-10:]
        print(f"  primeros {len(a)}: {sum(a)/len(a):.1f}%   ·   últimos 10: {sum(b)/len(b):.1f}%")
    n_ej = len(list(EJ.glob("*.informe.txt")))
    print(f"Ejemplos aprendidos disponibles para la IA: {n_ej} (+ los 33 del dataset)")


if __name__ == "__main__":
    from informe import config
    aprender(config())
    resumen()
