# -*- coding: utf-8 -*-
"""
FASE 1 - Transcribe los audios de ejemplo con Whisper (en tu PC, sin internet
salvo la primera descarga del modelo) y arma un reporte que compara lo que
dicto el medico con el informe final que escribiste.

Uso (desde fase1_transcribir.bat):
    python herramientas/fase1_transcribir.py              -> procesa todo y genera el reporte
    python herramientas/fase1_transcribir.py --verificar  -> solo prueba que la GPU funcione
Opciones utiles:
    --modelo large-v3-turbo   (mas rapido, un poco menos preciso)
    --device cpu              (si la GPU da error)
    --rehacer                 (vuelve a transcribir aunque ya exista)
"""
import argparse
import html
import json
import os
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]     # carpeta del sistema (este archivo está en herramientas/)
sys.path.insert(0, str(RAIZ))                  # para importar transcripcion

from transcripcion.asr.whisper import (VOCAB_DEF, cargar_modelo, leer_vocabulario,
                                       transcribir, duracion)
from transcripcion.texto.normalizacion import datos_criticos

AQUI = RAIZ
AUDIOS_DEF = AQUI.parent / "Dataset" / "Audios_Transcripcion"
SALIDA_DEF = AQUI / "resultados" / "fase1"

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def comparar(dictado, informe):
    if not informe.strip():
        return None
    oro = datos_criticos(informe, es_informe=True)
    dic = datos_criticos(dictado)
    enc = sorted(oro & dic)
    fal = sorted(oro - dic)
    extra = sorted(dic - oro)
    return {"total": len(oro), "encontrados": enc, "faltan": fal, "extra": extra,
            "cobertura": (len(enc) / len(oro)) if oro else None}


# --------------------------------------------------------------------- reporte
CSS = """
:root{--bg:#f6f6f4;--card:#fff;--tx:#1d1d1b;--mu:#6b6b66;--bd:#e3e2dd;
--baja:#f8c9c4;--media:#fbe7a6;--ok:#2f7d4f;--mal:#b3261e;--ac:#2557a7}
@media(prefers-color-scheme:dark){:root{--bg:#161615;--card:#20201f;--tx:#ecebe6;
--mu:#a3a29c;--bd:#34332f;--baja:#6b2a25;--media:#5c4d1a;--ok:#6fcf97;--mal:#ff8a80;--ac:#8ab4f8}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--tx);
font:15px/1.5 system-ui,Segoe UI,sans-serif;padding:24px 16px}
main{max-width:1200px;margin:auto}h1{font-size:24px;margin:0 0 4px}
.mu{color:var(--mu)}table{border-collapse:collapse;width:100%;background:var(--card);
border:1px solid var(--bd);border-radius:8px;overflow:hidden;font-size:14px}
th,td{padding:6px 10px;border-bottom:1px solid var(--bd);text-align:left}
th{font-weight:600;background:var(--bg)}td.n{text-align:right;font-variant-numeric:tabular-nums}
a{color:var(--ac)}.card{background:var(--card);border:1px solid var(--bd);
border-radius:10px;padding:16px;margin:20px 0}.card h2{font-size:17px;margin:0 0 6px}
.cols{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-top:10px}
@media(max-width:800px){.cols{grid-template-columns:1fr}}
.box{border:1px solid var(--bd);border-radius:8px;padding:10px 12px}
.box h3{font-size:13px;text-transform:uppercase;letter-spacing:.04em;color:var(--mu);margin:0 0 6px}
pre{white-space:pre-wrap;font:inherit;margin:0}
.w{cursor:pointer;border-radius:3px}.w:hover{outline:1px solid var(--ac)}
.baja{background:var(--baja)}.media{background:var(--media)}
.chip{display:inline-block;padding:1px 7px;margin:2px;border-radius:10px;
border:1px solid var(--bd);font-size:13px;font-variant-numeric:tabular-nums}
.chip.f{border-color:var(--mal);color:var(--mal)}.chip.e{border-style:dashed}
.ok{color:var(--ok);font-weight:600}.mal{color:var(--mal);font-weight:600}
audio{width:100%;margin-top:8px}details{margin-top:8px}summary{cursor:pointer;color:var(--mu)}
.ley span{padding:0 6px;border-radius:3px}
"""

JS = """
function ir(id,t){var a=document.getElementById(id);a.currentTime=Math.max(0,t-0.3);a.play();}
"""


def pct(x):
    return "—" if x is None else f"{x*100:.0f}%"


def html_palabras(palabras, audio_id):
    partes = []
    for w in palabras:
        cls = "baja" if w["conf"] < 0.5 else ("media" if w["conf"] < 0.8 else "")
        partes.append(
            f'<span class="w {cls}" title="confianza {w["conf"]:.2f} · {w["ini"]:.1f}s" '
            f'onclick="ir(\'{audio_id}\',{w["ini"]})">{html.escape(w["p"])}</span>')
    return "".join(partes)


def chips(cmp):
    if not cmp:
        return '<span class="mu">Sin informe para comparar.</span>'
    s = ""
    if cmp["faltan"]:
        s += "<div>No aparecen en el dictado: " + "".join(
            f'<span class="chip f">{html.escape(x)}</span>' for x in cmp["faltan"]) + "</div>"
    if cmp["encontrados"]:
        s += "<div>Encontrados: " + "".join(
            f'<span class="chip">{html.escape(x)}</span>' for x in cmp["encontrados"]) + "</div>"
    if cmp["extra"]:
        s += ('<div>En el dictado pero no en el informe (¿error de Whisper o dato descartado?): '
              + "".join(f'<span class="chip e">{html.escape(x)}</span>' for x in cmp["extra"])
              + "</div>")
    return s


def generar_reporte(resultados, salida, audios_dir, meta):
    filas, tarjetas = [], []
    rel_audio = os.path.relpath(audios_dir, salida).replace("\\", "/")
    for i, r in enumerate(resultados):
        A, B = r.get("sin_vocab"), r.get("con_vocab")
        cA = r.get("cmp_sin_vocab"); cB = r.get("cmp_con_vocab")
        dudosas = sum(1 for w in B["palabras"] if w["conf"] < 0.5) if B else 0
        np_dict = len(B["texto"].split()) if B else 0
        np_inf = len(r["informe"].split())
        filas.append(
            f'<tr><td><a href="#a{i}">{html.escape(r["nombre"])}</a></td>'
            f'<td class="n">{r["dur"]:.0f}s</td><td class="n">{np_dict}</td>'
            f'<td class="n">{np_inf}</td>'
            f'<td class="n">{pct(cA and cA["cobertura"])}</td>'
            f'<td class="n">{pct(cB and cB["cobertura"])}</td>'
            f'<td class="n">{dudosas}</td></tr>')
        aid = f"au{i}"
        texto_A = html.escape(A["texto"]) if A else "—"
        cuerpoB = html_palabras(B["palabras"], aid) if B else "—"
        tarjetas.append(f"""
<section class="card" id="a{i}">
  <h2>{html.escape(r["nombre"])} <span class="mu">· {r["dur"]:.0f} s</span></h2>
  <audio id="{aid}" controls preload="none" src="{rel_audio}/{html.escape(r["nombre"])}.wav"></audio>
  <div class="cols">
    <div class="box"><h3>Lo que dictó (Whisper, con vocabulario)</h3>
      <div>{cuerpoB}</div>
      <details><summary>Versión sin vocabulario</summary><p>{texto_A}</p></details>
    </div>
    <div class="box"><h3>Informe final (tu transcripción)</h3>
      <pre>{html.escape(r["informe"].strip()) or '<span class="mu">(archivo vacío)</span>'}</pre>
    </div>
  </div>
  <div style="margin-top:10px"><b>Datos críticos</b> (medidas, números, H12, L5-S1…) —
    cobertura con vocabulario: <b>{pct(cB and cB["cobertura"])}</b>
    {chips(cB)}</div>
</section>""")

    def prom(clave):
        v = [r[clave]["cobertura"] for r in resultados
             if r.get(clave) and r[clave]["cobertura"] is not None]
        return sum(v) / len(v) if v else None

    doc = f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Fase 1 · Reporte</title><style>{CSS}</style><script>{JS}</script></head>
<body><main>
<h1>Fase 1 · Dictado vs. informe final</h1>
<p class="mu">Modelo: {html.escape(meta["modelo"])} · {meta["n"]} audios ·
{meta["min_audio"]:.1f} min de audio procesados en {meta["seg_proc"]:.0f} s ·
{html.escape(meta["fecha"])}</p>
<p>Cobertura promedio de datos críticos: sin vocabulario <b>{pct(prom("cmp_sin_vocab"))}</b> ·
con vocabulario <b>{pct(prom("cmp_con_vocab"))}</b></p>
<p class="ley mu">Hacé clic en cualquier palabra para escuchar ese momento del audio.
<span class="baja">confianza baja (&lt;0.5)</span> <span class="media">confianza media (&lt;0.8)</span></p>
<table><tr><th>Audio</th><th>Duración</th><th>Palabras dictadas</th><th>Palabras informe</th>
<th>Cobertura sin vocab.</th><th>Cobertura con vocab.</th><th>Palabras dudosas</th></tr>
{''.join(filas)}</table>
{''.join(tarjetas)}
</main></body></html>"""
    (salida / "reporte.html").write_text(doc, encoding="utf-8")

    # texto plano para revisar / compartir
    with open(salida / "dictados_vs_informes.txt", "w", encoding="utf-8") as f:
        for r in resultados:
            f.write(f"===== {r['nombre']} ({r['dur']:.0f}s)\n")
            f.write("--- DICTADO (sin vocabulario)\n" + (r["sin_vocab"]["texto"] if r.get("sin_vocab") else "") + "\n")
            f.write("--- DICTADO (con vocabulario)\n" + (r["con_vocab"]["texto"] if r.get("con_vocab") else "") + "\n")
            f.write("--- INFORME FINAL\n" + r["informe"].strip() + "\n\n")


# ------------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--audios", default=str(AUDIOS_DEF))
    ap.add_argument("--salida", default=str(SALIDA_DEF))
    ap.add_argument("--modelo", default="large-v3")
    ap.add_argument("--device", default="cuda", choices=["cuda", "cpu"])
    ap.add_argument("--vocabulario", default=str(VOCAB_DEF))
    ap.add_argument("--rehacer", action="store_true")
    ap.add_argument("--verificar", action="store_true")
    ap.add_argument("--solo-reporte", action="store_true",
                    help="no transcribe, rearma el reporte con lo ya guardado")
    a = ap.parse_args()

    audios = Path(a.audios); salida = Path(a.salida)
    (salida / "json").mkdir(parents=True, exist_ok=True)

    modelo = None
    if not a.solo_reporte:
        try:
            modelo = cargar_modelo(a.modelo, a.device)
            if a.verificar:
                import numpy as np
                list(modelo.transcribe(np.zeros(16000, dtype="float32"), language="es")[0])
                print("\n[OK] Whisper funciona correctamente en", a.device.upper())
                return
        except Exception as e:
            print("\n[ERROR] No se pudo usar el modelo:", e)
            if a.device == "cuda":
                print("Sugerencias: actualizá el driver de NVIDIA y volvé a correr " + ("instalar.bat" if os.name == "nt" else "instalar.sh") + ".\n"
                      "Como alternativa podés probar con:  " + ("python herramientas\\fase1_transcribir.py" if os.name == "nt" else "python herramientas/fase1_transcribir.py") + " --device cpu")
            sys.exit(1)

    prompt = leer_vocabulario(a.vocabulario)
    wavs = sorted(audios.glob("*.wav"))
    if not wavs:
        print("No encontré audios .wav en", audios); sys.exit(1)

    resultados, t0, seg_audio = [], time.time(), 0.0
    for k, wav in enumerate(wavs, 1):
        nombre = wav.stem
        js = salida / "json" / f"{nombre}.json"
        txt = wav.with_suffix(".txt")
        informe = txt.read_text(encoding="utf-8-sig", errors="replace") if txt.exists() else ""
        dur = duracion(wav)
        if js.exists() and not a.rehacer:
            r = json.loads(js.read_text(encoding="utf-8"))
        elif modelo is None:
            continue
        else:
            print(f"[{k}/{len(wavs)}] {nombre} ({dur:.0f}s) ...", end=" ", flush=True)
            ti = time.time()
            r = {"nombre": nombre, "dur": dur,
                 "sin_vocab": transcribir(modelo, wav, None),
                 "con_vocab": transcribir(modelo, wav, prompt)}
            seg_audio += dur
            print(f"{time.time()-ti:.1f}s")
            js.write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
        r["informe"] = informe
        r["dur"] = dur
        r["cmp_sin_vocab"] = comparar(r["sin_vocab"]["texto"], informe)
        r["cmp_con_vocab"] = comparar(r["con_vocab"]["texto"], informe)
        resultados.append(r)

    meta = {"modelo": a.modelo, "n": len(resultados),
            "min_audio": sum(r["dur"] for r in resultados) / 60,
            "seg_proc": time.time() - t0, "fecha": time.strftime("%d/%m/%Y %H:%M")}
    generar_reporte(resultados, salida, audios, meta)
    print(f"\nListo. Reporte: {salida / 'reporte.html'}")


if __name__ == "__main__":
    main()
