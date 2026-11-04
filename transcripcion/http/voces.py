"""Reconocimiento del médico por la voz: resumen, muestras, agrupar y etiquetar."""

from transcripcion.acceso import remoto as R
from transcripcion.base import registro as L
from transcripcion.casos import paciente as PAC
from transcripcion.voz import huellas as VOZ


def resumen(h, pedido):
    """GET /api/voces."""
    sis = h.sis
    rv = VOZ.resumen()
    h._json(
        {
            "modelo": VOZ.estado_modelo(),
            "error": VOZ._DESCARGA.get("error") or "",
            "parametros": VOZ.parametros(sis.cfg),
            "medicos": rv,
            "sin_etiquetar": len(sis.voces.casos_sin_etiquetar()),
        }
    )


def muestras(h, pedido):
    """GET /api/voces/muestras."""
    sis = h.sis
    q = pedido.q
    med = q.get("medico", [""])[0]
    out = []
    for c, m in VOZ.muestras(med or None):
        f = {
            "caso": c,
            "medico": m.get("medico"),
            "fecha": m.get("fecha"),
            "fuente": m.get("fuente"),
            "seg": m.get("seg"),
            "titulo": c,
            "paciente": "",
            "audio": False,
        }
        try:
            f.update(
                titulo=sis.casos.titulo_de(c), paciente=PAC.de(sis.datos, c), audio=sis.casos.ruta_audio(c) is not None
            )
        except OSError:
            pass
        out.append(f)
    h._json({"muestras": out})


def agrupar(h, pedido):
    """GET /api/voces/agrupar."""
    sis = h.sis
    h._json(sis.voces.grupos_de_voces())


def etiquetar(h, pedido):
    """POST /api/voces/etiquetar. {"nombres": [...], "medico": "..."} desde «Agrupar voces»."""
    sis = h.sis
    datos = pedido.datos
    med = str(datos.get("medico") or "").strip()
    nombres = datos.get("nombres") or []
    if not med or not isinstance(nombres, list) or not nombres or len(nombres) > 500:
        return h._json({"error": "Elegí el médico y al menos un audio."}, 400)
    ok, salteados = [], []
    for x in dict.fromkeys(str(v) for v in nombres):
        v = sis.casos.voz_de(x) if h._nombre_valido(x) else None
        otro = R.bloqueado_por(x, h.pc) if v else None
        if not v or not v.get("h") or otro:
            salteados.append({"nombre": x, "motivo": f"lo está revisando {otro}" if otro else "sin huella de voz"})
            continue
        (sis.datos / f"{x}.medico.txt").write_text(med, encoding="utf-8")
        sis.casos.anotar_voz(x, medico_por="usuaria")
        VOZ.agregar(x, med, v["h"], "etiquetado", v.get("seg"))
        ok.append(x)
    k = VOZ.resumen().get(med, {}).get("n", 0)
    L.ok(
        "VOZ",
        f"{h.pc} etiquetó {L.plural(len(ok), 'audio')} como de «{med}» (ahora tiene "
        f"{L.plural(k, 'muestra')} de voz)" + (f"; {len(salteados)} salteado(s)" if salteados else "") + ".",
    )
    return h._json({"ok": True, "etiquetados": ok, "salteados": salteados, "muestras": k})


def quitar(h, pedido):
    """POST /api/voces/quitar. {"caso": "..."}: sacar una muestra mal etiquetada."""
    sis = h.sis
    datos = pedido.datos
    c = str(datos.get("caso") or "")
    viejo = VOZ.quitar(c) if h._nombre_valido(c) else None
    if viejo:
        if (
            (sis.datos / f"{c}.voz.json").exists()
            and sis.casos.medico_de(c) == viejo
            and not (sis.datos / f"{c}.final.txt").exists()
        ):
            sis.casos.anotar_voz(c, medico_por="")
        L.info("VOZ", f"{h.pc} quitó la muestra de voz de {sis.casos.visible(c)} de «{viejo}».")
    return h._json({"ok": bool(viejo)})
