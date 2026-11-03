# -*- coding: utf-8 -*-
"""
APRENDIZAJE: convierte tus informes revisados en ejemplos para la IA.

Como funciona:
  1. informe.bat genera Informes\\NOMBRE.docx con marcas de color.
  2. Vos lo corregis en ese mismo Word, sacas TODOS los resaltados y guardas (Ctrl+G / Ctrl+S).
  3. La proxima vez que uses informe.bat (o aprender.bat) ese Word se guarda como ejemplo:
     el dictado + tu version final. La IA los usa para los informes siguientes.
  Un Word que todavia tiene resaltados se considera "sin revisar" y se ignora.

Ademas lleva un historial indexado (resultados\\historial.sqlite3; importa el CSV anterior) con el % de palabras que tuviste
que corregir en cada informe, para ver si el sistema mejora con el tiempo.
"""
import difflib
import json
import re
import sys
import time
import hashlib
from pathlib import Path

import nucleo as N
from transcripcion.base.persistencia import escribir_atomico
from transcripcion.aprendizaje import almacen as AL

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


def registrar_ejemplo(nombre, dictado, ia, final, clave=None, medico=None, *, recalcular=True, fecha=None,
                      usuario=None):
    """Guarda el par dictado -> informe final como ejemplo y anota el historial.
    usuario: transcriptor que lo revisó (el ejemplo es de su estilo); None = general.
    Devuelve (clave, porcentaje_corregido)."""
    EJ.mkdir(exist_ok=True)
    HIST.parent.mkdir(parents=True, exist_ok=True)
    clave = clave or time.strftime("%Y%m%d_%H%M%S_") + nombre
    escribir_atomico(EJ / f"{clave}.dictado.txt", dictado)
    escribir_atomico(EJ / f"{clave}.informe.txt", final.strip() + "\n")
    escribir_atomico(EJ / f"{clave}.ia.txt", N.texto_limpio(ia))
    if medico:
        escribir_atomico(EJ / f"{clave}.medico.txt", medico)
    else:
        (EJ / f"{clave}.medico.txt").unlink(missing_ok=True)
    if usuario:
        escribir_atomico(EJ / f"{clave}.usuario.txt", usuario)
    else:
        (EJ / f"{clave}.usuario.txt").unlink(missing_ok=True)
    ia_sin_espacios = "\n".join(l.rstrip() for l in N.texto_limpio(ia).splitlines())
    pc = pct_corregido(ia_sin_espacios, final)
    fecha = fecha or time.strftime("%Y-%m-%d %H:%M")
    with AL.abrir(HIST) as c:
        c.execute('INSERT OR REPLACE INTO historial VALUES (?,?,?,?,?)',
                  (fecha[:10], nombre, fecha, len(final.split()), f"{pc*100:.1f}"))
        _indexar_correcciones(c, clave, N.texto_limpio(ia), final.strip() + "\n")
        AL.poner_usuario(c, clave, usuario)
    if recalcular:
        try:
            analizar_correcciones()
        except Exception:
            from transcripcion.base import registro as L
            L.aviso("APRENDIZAJE", "No se pudieron actualizar las correcciones frecuentes.", exc=True)
    return clave, pc


# ------------------------------------------------ correcciones repetidas
ARCH_CORR = AQUI / "conocimiento" / "correcciones_aprendidas.md"
DATOS_INF = AQUI.parent / "Informes" / "revision" / "datos"


def _norm_tok(w):
    return w.strip(".,;:").lower()


def cambios_de_textos(ia, final):
    a = re.findall(r"\S+", ia)
    b = re.findall(r"\S+", final)
    cambios = set()
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(a=a, b=b, autojunk=False).get_opcodes():
        if op == "equal" or max(i2-i1, j2-j1) > 12:
            continue
        de, a_ = " ".join(a[i1:i2]), " ".join(b[j1:j2])
        if re.search(r"\d", de + a_):
            continue
        if [_norm_tok(x) for x in a[i1:i2]] == [_norm_tok(x) for x in b[j1:j2]]:
            continue
        cambios.add((op, de.strip(".,;:"), a_.strip(".,;:")))
    return cambios


def _indexar_correcciones(c, clave, ia, final):
    firma = hashlib.sha256(json.dumps([ia, final], ensure_ascii=False).encode('utf-8')).hexdigest()
    return AL.actualizar_ejemplo(c, clave, firma, lambda: cambios_de_textos(ia, final))


def _lineas_correcciones(frec, titulo):
    lineas = [titulo, "# Tenelas en cuenta, pero usalas solo si el dictado lo justifica.", ""]
    for n, (op, de, a_) in frec[:40]:
        if op == "replace":
            lineas.append(f"- La IA escribió «{de}» y el transcriptor lo cambió por «{a_}» ({n} informes).")
        elif op == "insert":
            lineas.append(f"- El transcriptor tuvo que AGREGAR «{a_}» ({n} informes).")
        else:
            lineas.append(f"- El transcriptor tuvo que BORRAR «{de}» ({n} informes).")
    return "\n".join(lineas) + "\n"


def repartir_correcciones(fuentes, minimo=2):
    """Una corrección repetida es GENERAL si se repite entre los ejemplos generales (los de antes de los usuarios)
    o si la hicieron al menos dos fuentes distintas (dos transcriptores, o uno y los generales). Si la repite un
    solo transcriptor, queda solo para él. Devuelve (generales, {usuario: [...]}) con elementos (n, (op, de, a))."""
    generales, propias = [], {}
    for k, cnt in fuentes.items():
        n = sum(cnt.values())
        if n < minimo:
            continue
        if cnt.get("", 0) >= minimo or len(cnt) >= 2:
            generales.append((n, k))
        else:
            (u, m), = cnt.items()
            propias.setdefault(u, []).append((m, k))
    orden = lambda x: (x[0], x[1][0], x[1][1], x[1][2])
    generales.sort(key=orden, reverse=True)
    for v in propias.values():
        v.sort(key=orden, reverse=True)
    return generales[:40], {u: v[:40] for u, v in propias.items()}


def analizar_correcciones(minimo=2, *, reconstruir=False):
    """Publica las 40 reglas principales (generales y de cada transcriptor).
    Solo recorre el corpus al migrar o reconciliar explícitamente."""
    with AL.abrir(HIST) as c:
        inicializado = c.execute("SELECT v FROM meta WHERE k='correcciones'").fetchone()
        if reconstruir or not inicializado:
            claves = set()
            for inf in EJ.glob('*.informe.txt'):
                clave = inf.name[:-len('.informe.txt')]
                ia_f = EJ / f'{clave}.ia.txt'
                if not ia_f.exists():
                    nombre = clave.split('_', 2)[-1]
                    viejo = DATOS_INF / f'{nombre}.informe_ia.txt'
                    if not viejo.exists():
                        continue
                    escribir_atomico(ia_f, N.texto_limpio(viejo.read_text(encoding='utf-8')))
                claves.add(clave)
                _indexar_correcciones(c, clave, ia_f.read_text(encoding='utf-8'), inf.read_text(encoding='utf-8'))
                usu = EJ / f'{clave}.usuario.txt'
                AL.poner_usuario(c, clave, usu.read_text(encoding='utf-8').strip() if usu.exists() else None)
            for (clave,) in c.execute('SELECT clave FROM ejemplos').fetchall():
                if clave not in claves:
                    AL.quitar_ejemplo(c, clave)
            c.execute("INSERT OR REPLACE INTO meta VALUES ('correcciones','1')")
        frec, propias = repartir_correcciones(AL.correcciones_por_fuente(c), minimo)
    salida = _lineas_correcciones(frec, "# CORRECCIONES QUE EL TRANSCRIPTOR HIZO VARIAS VECES (se actualiza solo; no editar)")
    if not ARCH_CORR.exists() or ARCH_CORR.read_text(encoding="utf-8") != salida:
        escribir_atomico(ARCH_CORR, salida)
    from transcripcion.acceso import usuarios as U
    for clave in set(U.claves_con_carpeta()) | set(propias):
        try:
            if propias.get(clave):
                texto = _lineas_correcciones(propias[clave], "# CORRECCIONES QUE HICISTE VARIAS VECES "
                                                             "(solo para tu estilo; se actualiza solo; no editar)")
                if U.leer_archivo(clave, "correcciones_aprendidas.md") != texto:
                    U.escribir_archivo(clave, "correcciones_aprendidas.md", texto)
            else:
                U.archivo(clave, "correcciones_aprendidas.md").unlink(missing_ok=True)
        except ValueError:
            continue
    return frec


def _importar_procesados(c):
    if c.execute("SELECT v FROM meta WHERE k='procesados'").fetchone():
        return
    reg = json.loads(REG.read_text(encoding='utf-8')) if REG.exists() else {}
    for ruta, d in reg.items():
        c.execute('INSERT OR REPLACE INTO procesados VALUES (?,?,?)', (ruta,d['mtime'],d['ejemplo']))
    c.execute("INSERT INTO meta VALUES ('procesados','1')")


def procesado(docx):
    with AL.abrir(HIST) as c:
        _importar_procesados(c)
        r = c.execute('SELECT mtime,ejemplo FROM procesados WHERE ruta=?', (str(docx),)).fetchone()
        return {'mtime':r[0], 'ejemplo':r[1]} if r else {}


def anotar_procesado(docx, clave):
    with AL.abrir(HIST) as c:
        _importar_procesados(c)
        c.execute('INSERT OR REPLACE INTO procesados VALUES (?,?,?)', (str(docx),Path(docx).stat().st_mtime,clave))


def aprender(cfg, silencioso=False):
    sal = cfg["carpeta_informes"]
    datos = sal / "revision" / "datos"
    EJ.mkdir(exist_ok=True)
    HIST.parent.mkdir(parents=True, exist_ok=True)
    nuevos, pendientes = [], []
    for docx in sorted(sal.glob("*.docx")):
        if docx.name.startswith("~$"):
            continue
        nombre = docx.stem
        dic_f, ia_f = datos / f"{nombre}.dictado.txt", datos / f"{nombre}.informe_ia.txt"
        if not (dic_f.exists() and ia_f.exists()):
            continue
        mt = docx.stat().st_mtime
        registro = procesado(docx)
        if registro.get("mtime") == mt:
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
                                      final, registro.get("ejemplo"))
        anotar_procesado(docx, clave)
        nuevos.append((nombre, pc))

    if nuevos:
        print(f"Aprendidos {len(nuevos)} informe(s) revisado(s): " +
              ", ".join(f"{n} ({p*100:.0f}% corregido)" for n, p in nuevos))
    if pendientes and not silencioso:
        print(f"Sin revisar todavía (tienen resaltados): {', '.join(pendientes)}")
    return nuevos


def resumen():
    if not HIST.exists() and not AL.ruta_base(HIST).exists():
        print("Todavía no hay informes revisados en el historial.")
        return
    filas = AL.leer_historial(HIST)
    pcs = [float(f["porcentaje_corregido"]) for f in filas]
    print(f"\nHistorial: {len(pcs)} informes revisados · promedio corregido {sum(pcs)/len(pcs):.1f}%")
    if len(pcs) >= 20:
        a, b = pcs[:-10], pcs[-10:]
        print(f"  primeros {len(a)}: {sum(a)/len(a):.1f}%   ·   últimos 10: {sum(b)/len(b):.1f}%")
    n_ej = len(list(EJ.glob("*.informe.txt")))
    print(f"Ejemplos aprendidos disponibles para la IA: {n_ej} (+ los 33 del dataset)")


if __name__ == "__main__":
    from informe import config
    cfg = config()
    N.preparar_conocimiento()
    aprender(cfg)
    resumen()
