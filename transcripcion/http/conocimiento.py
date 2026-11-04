"""Plantillas, médicos y referencias: lo que la IA usa para armar los informes."""

from pathlib import Path

from transcripcion.acceso import remoto as R
from transcripcion.acceso import usuarios as U
from transcripcion.base import registro as L
from transcripcion.conocimiento import medicos as MED
from transcripcion.conocimiento import plantillas as PL
from transcripcion.informe import formato as FMT
from transcripcion.voz import huellas as VOZ


def formato(h, pedido):
    """GET /api/formato."""
    sis = h.sis
    cfg = U.cfg_de(sis.cfg, h.usuario)
    h._json(
        {
            "palabras_titulo": sorted(PL.PALABRAS_ESTUDIO),
            "negrita_titulos": cfg.get("negrita_titulos", True),
            "fuente": cfg.get("fuente"),
            "tamano": cfg.get("tamano_fuente"),
            "prefijos": sis.cfg.get("negrita_si_empieza_con", FMT.NEGRITA_DEF),
            "exactas": sis.cfg.get("negrita_lineas_exactas", FMT.NEGRITA_EXACTAS),
        }
    )


def medicos(h, pedido):
    """GET /api/medicos."""
    rv = VOZ.resumen()
    out = []
    for m in MED.lista_medicos():
        propias = MED.notas_propias(m, h.usuario)
        x = {
            "nombre": m,
            "notas": MED.notas_medico(m, h.usuario),
            "voz": rv.get(m, {}).get("n", 0),
            "propias": propias is not None,
        }
        if propias is not None:
            x["generales"] = MED.notas_medico(m)
        out.append(x)
    h._json({"medicos": out})


def plantillas(h, pedido):
    """GET /api/plantillas."""
    h._json({"secciones": PL.secciones_con_origen(h.usuario), "con_usuario": bool(h.usuario)})


def plantilla_word(h, pedido):
    """POST /api/plantilla_word."""
    q = pedido.q
    arch = q.get("archivo", [""])[0].lower()
    if not arch.endswith(".docx"):
        return h._json(
            {"error": "Guardalo como .docx (en Word: Archivo → Guardar como → Documento de Word) y volvé a intentar."},
            400,
        )
    from transcripcion.conocimiento.importar import plantilla_desde_word

    L.info("CONFIG", f"{h.pc} armó una plantilla desde el Word «{Path(arch).name}».")
    return h._json(plantilla_desde_word(h._body()))


def mi_medico(h, pedido):
    """POST /api/mi_medico."""
    datos = pedido.datos
    med = datos.get("medico", "").strip()
    if med != R.medico_pc(h.pc):
        L.info("CONFIG", f"{h.pc} eligió médico para sus audios: {med or 'ninguno'}.")
    R.poner_medico_pc(h.pc, med)
    return h._json({"ok": True})


def medico(h, pedido):
    """POST /api/medico."""
    datos = pedido.datos
    # destino: "todos" (notas generales, como siempre), "mio" (solo para este transcriptor) o
    # "general" (dejar de usar las propias). Sin destino = "todos" (compatibilidad).
    destino = datos.get("destino") or "todos"
    try:
        if destino in ("mio", "general") and not datos.get("crear"):
            if not h.usuario:
                return h._json({"error": "Para guardar notas solo para vos tenés que entrar con tu usuario."}, 403)
            nom = str(datos.get("medico", ""))
            MED.guardar_notas_propias(nom, h.usuario, datos.get("notas", "") if destino == "mio" else None)
            L.ok(
                "CONFIG",
                f"Notas propias de {h.quien} sobre {nom} "
                + ("guardadas." if destino == "mio" else "quitadas: vuelve a usar las generales."),
            )
            return h._json({"ok": True, "medico": nom, "destino": destino})
        nom = MED.guardar_medico(datos.get("medico", ""), datos.get("notas", ""), crear=datos.get("crear") is True)
        if h.usuario and not datos.get("crear"):
            MED.guardar_notas_propias(nom, h.usuario, None)  # pasan a ser las de todos
    except FileExistsError as ex:
        return h._json({"error": str(ex)}, 409)
    except FileNotFoundError as ex:
        return h._json({"error": str(ex)}, 404)
    except ValueError as ex:
        return h._json({"error": str(ex)}, 400)
    L.ok("CONFIG", f"Notas del médico {nom} guardadas para todos ({h.quien}).")
    return h._json({"ok": True, "medico": nom, "destino": "todos"})


def importar_referencias(h, pedido):
    """POST /api/importar."""
    from transcripcion.conocimiento.importar import importar

    ok, mal = importar()
    L.ok(
        "CONFIG",
        f"Importados {L.plural(len(ok), 'informe')} Word como referencia ({h.pc}).",
        [f"No se pudieron leer: {', '.join(mal)}"] if mal else None,
    )
    return h._json({"ok": ok, "mal": mal})


def guardar_plantillas(h, pedido):
    """POST /api/plantillas."""
    datos = pedido.datos
    secs = [(x.get("nombre", ""), x.get("cuerpo", "")) for x in datos.get("secciones", []) if isinstance(x, dict)]
    if not secs:
        return h._json({"error": "No hay plantillas para guardar"}, 400)
    destino = datos.get("destino") or ("mio" if h.usuario else "todos")
    try:
        r = PL.aplicar_plantillas(secs, h.usuario, destino)
    except ValueError as ex:
        return h._json({"error": str(ex)}, 400)
    if r["sin_cambios"]:
        return h._json({"ok": True, **r})
    if destino == "todos":
        L.ok(
            "CONFIG",
            f"Plantillas guardadas para todos por {h.quien} ({L.plural(r['generales'], 'cambio')}); "
            f"la versión anterior quedó en conocimiento\\copias.",
        )
    else:
        L.ok("CONFIG", f"Plantillas propias de {h.quien} guardadas ({L.plural(r['propias'], 'cambio')}).")
    return h._json({"ok": True, **r})


def plantilla_general(h, pedido):
    """POST /api/plantillas/general. Quitar la versión propia de una plantilla."""
    datos = pedido.datos
    if not h.usuario:
        return h._json({"error": "Entrá con tu usuario."}, 403)
    nom = str(datos.get("nombre") or "")
    ok = PL.volver_a_general(h.usuario, nom)
    if ok:
        L.info("CONFIG", f"{h.quien} volvió a la plantilla general de «{nom}».")
    return h._json({"ok": ok})
