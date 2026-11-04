"""Cambios sobre un caso: abrirlo para revisar (bloqueo), pausar, médico, paciente, volver a generar,
borrador, formato y «Guardar Word»."""

import json
import time

from transcripcion.acceso import remoto as R
from transcripcion.base import plataforma as P
from transcripcion.base import registro as L
from transcripcion.base.persistencia import escribir_atomico
from transcripcion.casos import borradores as BOR
from transcripcion.casos import paciente as PAC


def pausar_o_reanudar(h, pedido):
    """POST /api/caso/pausar, /api/caso/reanudar."""
    sis = h.sis
    n = pedido.nombre
    accion = "pausar" if pedido.ruta.endswith("/pausar") else "reanudar"
    if h.remoto:
        if L.una_vez(("pausa_remota", h.pc), 600):
            L.aviso(
                "ACCESO",
                f"{h.pc} intentó {accion} la transcripción de {sis.casos.visible(n)}: solo se "
                f"puede desde la PC del servidor.",
            )
        return h._json({"error": "Pausar o reanudar una transcripción solo se puede en la PC del servidor."}, 403)
    if not origen_local(h):
        return h._json({"error": "Pedido rechazado: no viene de esta página."}, 403)
    r, code = (sis.proc.pausar if accion == "pausar" else sis.proc.reanudar)(n, "la lista de informes")
    return h._json(r, code)


def bloquear(h, pedido):
    """POST /api/caso/bloquear."""
    sis = h.sis
    datos = pedido.datos
    n = pedido.nombre
    previo = R.BLOQUEOS.get(n)
    # la página que ya lo tenía abierto avisa cada 15 s que sigue ahí (manda el tiempo de revisión)
    r = R.bloquear(n, h.pc, renovar="rev" in datos or bool(datos.get("renovar")))
    if r is R.LIBERADO:
        return h._json({"ok": False, "liberado": True, "por": "el panel de administración"})
    if r is True:
        sis.casos.sumar_revision(n, datos.get("rev"), h.pc)
        if not previo or previo["pc"] != h.pc or time.time() - previo["t"] > R.BLOQUEO_SEG:
            L.info("CASO", f"{h.pc} abrió {sis.casos.visible(n)} para revisar.")
    elif L.una_vez(("ocupado", n, h.pc), 120):
        L.info("CASO", f"{h.pc} quiso abrir {sis.casos.visible(n)}, pero lo está revisando {r}.")
    return h._json({"ok": True} if r is True else {"ok": False, "por": r})


def soltar(h, pedido):
    """POST /api/caso/soltar."""
    sis = h.sis
    datos = pedido.datos
    n = pedido.nombre
    if R.bloqueado_por(n, h.pc) is None:
        sis.casos.sumar_revision(n, datos.get("rev"), h.pc)
    R.soltar(n, h.pc)
    L.debug("CASO", f"{h.pc} cerró {sis.casos.visible(n)}.")
    return h._json({"ok": True})


def medico(h, pedido):
    """POST /api/caso_medico."""
    sis = h.sis
    datos = pedido.datos
    n = pedido.nombre
    med = datos.get("medico", "").strip()
    f = sis.datos / f"{n}.medico.txt"
    if med:
        f.write_text(med, encoding="utf-8")
    else:
        f.unlink(missing_ok=True)
    sis.casos.anotar_voz(n, medico_por="usuaria" if med else "")
    if (sis.datos / f"{n}.final.txt").exists():
        sis.voces.actualizar_muestra(n, med)  # ya guardado: la muestra de voz se corrige al momento
    L.info("CASO", f"{sis.casos.visible(n)}: médico cambiado a {med or 'ninguno'} ({h.pc}).")
    vz = sis.voces.resumen_voz(n) or {}
    return h._json(
        {
            "ok": True,
            "voz": vz,
            "regenerar": bool(vz)
            and (vz.get("medico_ia") or "") != med
            and not (sis.datos / f"{n}.final.txt").exists(),
        }
    )


def paciente(h, pedido):
    """POST /api/paciente."""
    sis = h.sis
    datos = pedido.datos
    n = pedido.nombre
    p = PAC.corregir(sis.datos, n, datos.get("paciente", ""))
    L.info(
        "CASO",
        f"{sis.casos.visible(n)}: nombre del paciente "
        + ("corregido a mano" if datos.get("paciente", "").strip() else "vuelto a sacar del dictado")
        + f" ({h.pc}).",
    )
    return h._json({"ok": True, "paciente": p})


def procesar(h, pedido):
    """POST /api/procesar."""
    sis = h.sis
    n = pedido.nombre
    if n in sis.proc.pausas or sis.proc.estado.get(n, {}).get("estado") == "en pausa":
        return h._json({"error": "Está en pausa: reanudalo desde la lista."}, 409)
    L.info("IA", f"{h.quien} pidió volver a generar {sis.casos.visible(n)}" + (" con su estilo." if h.usuario else "."))
    if h.usuario:
        sis.casos.poner_usuario_caso(n, h.usuario)  # volver a generar = con el estilo de quien lo pide
    sis.proc.encolar(n)
    return h._json({"ok": True})


def borrador(h, pedido):
    """POST /api/borrador."""
    sis = h.sis
    datos = pedido.datos
    n = pedido.nombre
    try:
        revision = BOR.guardar(sis.datos, n, datos)
    except BOR.Conflicto as ex:
        return h._json({"error": str(ex)}, 409)
    except BOR.Corrupto as ex:
        return h._json({"error": str(ex)}, 503)
    except ValueError as ex:
        return h._json({"error": str(ex)}, 400)
    except OSError:
        L.error("CASO", "No se pudo guardar el borrador en disco.", exc=True)
        return h._json(
            {"error": "No se pudo guardar el borrador en el servidor. Conservá el caso abierto y reintentá."}, 503
        )
    return h._json({"ok": True, "revision": revision})


def formato(h, pedido):
    """POST /api/formato_caso. Formato elegido a mano en la vista previa."""
    sis = h.sis
    datos = pedido.datos
    n = pedido.nombre
    f = sis.datos / f"{n}.formato.json"
    fm = datos.get("formato")
    if isinstance(fm, dict) and fm.get("parrafos"):
        escribir_atomico(f, json.dumps(fm, ensure_ascii=False))
    else:
        f.unlink(missing_ok=True)
    L.debug("CASO", f"{sis.casos.visible(n)}: formato de la vista previa guardado ({h.pc}).")
    return h._json({"ok": True})


def formato_agregar(h, pedido):
    """POST /api/formato_caso/agregar. Formato de una autocorrección de Word (app del trabajo)."""
    sis = h.sis
    datos = pedido.datos
    n = pedido.nombre
    nuevos = []
    for x in (datos.get("parrafos") or [])[:200]:
        if not isinstance(x, dict) or not isinstance(x.get("t"), str) or not x["t"].strip():
            continue
        r = [y for y in (x.get("r") or []) if isinstance(y, dict) and isinstance(y.get("t"), str)]
        nuevos.append({"t": x["t"], "a": x.get("a") if isinstance(x.get("a"), str) else "", "r": r or [{"t": x["t"]}]})
    if nuevos:
        with sis.fmt_lock:
            fm = sis.casos.formato_de(n)
            if not isinstance(fm, dict) or not isinstance(fm.get("parrafos"), list):
                fm = {"v": 1, "parrafos": []}
            fm["parrafos"].extend(nuevos)
            (sis.datos / f"{n}.formato.json").write_text(json.dumps(fm, ensure_ascii=False), encoding="utf-8")
        L.debug("CASO", f"{sis.casos.visible(n)}: formato de una autocorrección de Word agregado ({h.pc}).")
    return h._json({"ok": True})


def finalizar(h, pedido):
    """POST /api/finalizar."""
    sis = h.sis
    datos = pedido.datos
    n = pedido.nombre
    sis.casos.sumar_revision(n, datos.get("rev"), h.pc)
    return h._json(sis.guardado.finalizar(n, datos.get("texto", ""), h.pc, h.usuario))


def abrir_word(h, pedido):
    """POST /api/abrir."""
    sis = h.sis
    n = pedido.nombre
    p = sis.informes / f"{n}.docx"
    if p.exists() and not h.remoto:
        try:
            P.abrir(p)
        except OSError:
            pass
    return h._json({"ok": p.exists()})


def origen_local(h):
    """Para los botones solo locales (pausa): que el pedido no venga de una página de otro sitio."""
    sis = h.sis
    o = (h.headers.get("Origin") or "").lower()
    if o and o not in (f"http://127.0.0.1:{sis.puerto}", f"http://localhost:{sis.puerto}"):
        return False
    return h.headers.get("Sec-Fetch-Site") in (None, "same-origin", "none")


def caso_ocupado(h, n):
    """Si otra PC tiene el caso abierto (o el panel se lo liberó a esta), responde 409 y devuelve True."""
    otro = R.bloqueado_por(n, h.pc) or (R.liberado_para(n, h.pc) and "el panel de administración")
    if not otro:
        return False
    if L.una_vez(("conflicto", n, h.pc), 120):
        L.aviso(
            "CASO",
            f"{h.pc} intentó modificar {h.sis.casos.visible(n)} "
            + (
                "después de que se lo liberaron desde el panel"
                if otro == "el panel de administración"
                else f"mientras lo revisa {otro}"
            )
            + "; no se guardó su cambio.",
        )
    if otro == "el panel de administración":
        h._json(
            {
                "error": "Desde el panel de administración se liberó este caso: cerralo y "
                "volvé a abrirlo desde la lista para seguir.",
                "liberado": True,
            },
            409,
        )
    else:
        h._json({"error": f"Este caso lo está revisando {otro}."}, 409)
    return True
