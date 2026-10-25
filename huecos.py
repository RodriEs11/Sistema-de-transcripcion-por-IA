# -*- coding: utf-8 -*-
"""
Deteccion y reparacion de fragmentos que Whisper no transcribio.

Whisper a veces "se come" un pedazo de dictado: deja un silencio donde hay voz,
o estira una palabra varios segundos (ej. "aparte" de 135.7 s a 139.0 s tapando
"aspecto folicular, mide 10 milimetros"). Aca:
  1) se buscan esos lugares mirando la energia (volumen) del audio,
  2) se vuelve a transcribir SOLO ese pedazo y se inserta lo recuperado,
  3) lo que no se pudo recuperar se avisa en la interfaz para escucharlo.
"""
import numpy as np

SR = 16000
# frases que Whisper "inventa" en pedazos cortos o con ruido
ALUCINACIONES = ("gracias por ver", "subtítulos", "subtitulos", "amara.org", "suscríbete", "suscribete",
                 "¡gracias!", "gracias.", "música", "[música]", "www.", "transcripción")
VENT = 0.03          # ventanas de 30 ms


def energia(audio):
    n = int(SR * VENT)
    k = len(audio) // n
    if k == 0:
        return np.zeros(0)
    x = audio[: k * n].reshape(k, n)
    return np.sqrt((x ** 2).mean(axis=1) + 1e-12)


def regiones_sospechosas(audio, palabras, gap_min=1.0, palabra_max=1.4, voz_min=0.6):
    """Devuelve [(ini, fin, motivo)] donde parece haber voz sin transcribir."""
    if not palabras or len(audio) < SR:
        return []
    e = energia(audio)
    t = lambda s: int(s / VENT)
    # umbral de voz: relativo a la energia tipica durante las palabras
    hablado = np.concatenate([e[t(w["ini"]): max(t(w["ini"]) + 1, t(w["fin"]))] for w in palabras]) \
        if palabras else e
    umbral = max(np.percentile(hablado, 50) * 0.35, np.percentile(e, 20) * 2.0)

    cands = []
    ini_audio = 0.0
    prev_fin = ini_audio
    for w in palabras:
        if w["ini"] - prev_fin >= gap_min:
            cands.append((prev_fin, w["ini"], "silencio"))
        if w["fin"] - w["ini"] >= palabra_max:
            cands.append((w["ini"], w["fin"], "palabra larga"))
        prev_fin = max(prev_fin, w["fin"])
    dur = len(audio) / SR
    if dur - prev_fin >= gap_min:
        cands.append((prev_fin, dur, "final"))

    out = []
    for a, b, mot in cands:
        seg = e[t(a): t(b)]
        voz = (seg > umbral).sum() * VENT
        if voz >= voz_min:
            out.append((round(a, 2), round(b, 2), mot, round(float(voz), 2)))
    return out


def reparar(modelo, audio, palabras, prompt_base=None, margen=0.3):
    """Re-transcribe las regiones sospechosas y empalma lo recuperado.
    Devuelve (palabras_nuevas, huecos_sin_recuperar)."""
    regiones = regiones_sospechosas(audio, palabras)
    if not regiones:
        return palabras, []
    palabras = list(palabras)
    pendientes = []
    for a, b, mot, voz in sorted(regiones, reverse=True):     # de atras para adelante
        a0, b0 = max(0.0, a - margen), min(len(audio) / SR, b + margen)
        clip = audio[int(a0 * SR): int(b0 * SR)]
        previas = [w["p"] for w in palabras if w["fin"] <= a][-25:]
        prompt = ((prompt_base or "") + " " + "".join(previas)).strip() or None
        segs, _ = modelo.transcribe(clip, language="es", beam_size=5, vad_filter=False,
                                    word_timestamps=True, condition_on_previous_text=False,
                                    initial_prompt=prompt)
        nuevas = []
        for s in segs:
            for w in (s.words or []):
                ini, fin = a0 + w.start, a0 + w.end
                if fin <= a - 0.05 or ini >= b + 0.05:       # fuera de la region
                    continue
                nuevas.append({"p": w.word, "ini": round(ini, 2), "fin": round(fin, 2),
                               "conf": round(w.probability, 3), "recuperada": True})
        # solo sirve si trae algo distinto a lo que ya habia
        quitar = [w for w in palabras if w["ini"] >= a - 0.05 and w["fin"] <= b + 0.05]
        viejo = " ".join(w["p"].strip().lower() for w in quitar)
        nuevo = " ".join(w["p"].strip().lower() for w in nuevas)
        conf = sum(w["conf"] for w in nuevas) / len(nuevas) if nuevas else 0
        alucinacion = any(x in nuevo for x in ALUCINACIONES)
        if nuevas and not alucinacion and conf >= 0.4 and len(nuevo.split()) > len(viejo.split()):
            palabras = [w for w in palabras if w not in quitar]
            palabras += nuevas
            palabras.sort(key=lambda w: w["ini"])
        elif (mot in ("silencio", "final") and voz >= 1.5) or (mot == "palabra larga" and voz >= 2.0):
            # mucha voz y no se pudo recuperar: avisar para escucharlo
            pendientes.append({"ini": a, "fin": b, "motivo": mot})
    return palabras, sorted(pendientes, key=lambda h: h["ini"])


def texto_de(palabras):
    return "".join(w["p"] for w in palabras).strip()
