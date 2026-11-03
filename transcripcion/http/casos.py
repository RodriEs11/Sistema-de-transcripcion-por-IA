"""Lista de casos, caso abierto, forma de onda, audio, Word, vista previa y borrado."""

import re
import urllib.parse

from transcripcion.base import registro as L
from transcripcion.casos import borradores as BOR
from transcripcion.casos import paciente as PAC


def word(h, pedido):
    """GET /api/word."""
    sis = h.sis
    q = pedido.q
    n = q.get("nombre", [""])[0]
    p = sis.informes / f"{n}.docx"
    if not h._nombre_valido(n) or not p.exists():
        h.send_error(404)
        return
    pac = PAC.de(sis.datos, n)
    nom = re.sub(r'[\\/:*?"<>|]+', "", f"{pac} - {sis.casos.titulo_de(n)}" if pac else sis.casos.titulo_de(n)).strip()
    h._enviar_archivo(p, descarga=f"{nom or n}.docx")


def lista(h, pedido):
    """GET /api/casos."""
    sis = h.sis
    ok = sis.ia.ia_lista()
    h._json(
        {
            "casos": sis.vista.listar_casos(h.pc, h.remoto),
            "ollama": ok,
            "pc": h.pc,
            "ia_estado": "caida" if not ok else ("sin_modelo" if sis.ia.ultimo["e"] == "sin_modelo" else "ok"),
            "modelo": sis.cfg["modelo_ia"],
            "mensaje": sis.oper.mensaje_para_pcs(),
            "pausa": bool(sis.proc.trabajo.get("en_pausa")),
        }
    )


def caso(h, pedido):
    """GET /api/caso."""
    sis = h.sis
    q = pedido.q
    n = q.get("nombre", [""])[0]
    try:
        c = sis.vista.cargar_caso(n) if h._nombre_valido(n) else None
    except (BOR.Corrupto, OSError):
        L.error("CASO", "No se pudo leer el borrador guardado.", exc=True)
        return h._json(
            {"error": "No se pudo leer el borrador guardado. Conservá sus archivos y solicitá recuperación."}, 503
        )
    h._json(c if c else {"error": "no existe"}, 200 if c else 404)


def onda(h, pedido):
    """GET /api/onda."""
    sis = h.sis
    q = pedido.q
    n = q.get("nombre", [""])[0]
    try:
        d = sis.vista.forma_de_onda(n) if h._nombre_valido(n) else None
    except Exception:
        L.error("CASO", f"No pude dibujar la forma de onda de {sis.casos.visible(n)}.", exc=True)
        d = None
    h._json(d if d else {"error": "sin audio"}, 200 if d else 404)


def audio(h, pedido):
    """GET /audio/…"""
    sis = h.sis
    n = urllib.parse.unquote(pedido.ruta[7:])
    a = sis.casos.ruta_audio(n) if h._nombre_valido(n) else None
    if not a:
        h.send_error(404)
        return
    h._enviar_archivo(a)


def vista_previa(h, pedido):
    """POST /api/vista_previa."""
    sis = h.sis
    datos = pedido.datos
    nv = datos.get("nombre") or None
    return h._json(
        sis.guardado.vista_previa(str(datos.get("texto", "")), nv if nv and h._nombre_valido(nv) else None, h.usuario)
    )


def borrar(h, pedido):
    """POST /api/borrar. Uno o varios casos: {"nombres": [...]}."""
    sis = h.sis
    datos = pedido.datos
    nombres = datos.get("nombres") or ([datos["nombre"]] if datos.get("nombre") else [])
    if not isinstance(nombres, list) or not nombres or len(nombres) > 500:
        return h._json({"error": "No hay informes para borrar"}, 400)
    ok, mal = [], []
    for x in dict.fromkeys(str(v) for v in nombres):
        if not h._nombre_valido(x):
            mal.append({"nombre": x, "error": "nombre inválido"})
            continue
        err = sis.borrado.borrar_caso(x, h.pc, h.remoto)
        (mal.append({"nombre": x, "error": err}) if err else ok.append(x))
    if len(ok) > 1:
        L.ok(
            "CASO",
            f"{h.pc} borró {L.plural(len(ok), 'informe')}"
            + (f" ({len(mal)} no se {'pudo' if len(mal) == 1 else 'pudieron'} borrar)" if mal else "")
            + ".",
        )
    if mal and not ok and len(mal) == 1:
        code = 403 if mal[0]["error"].startswith("Solo se pueden") else 409
        return h._json({"error": mal[0]["error"], "borrados": ok, "fallidos": mal}, code)
    return h._json({"ok": True, "borrados": ok, "fallidos": mal})
