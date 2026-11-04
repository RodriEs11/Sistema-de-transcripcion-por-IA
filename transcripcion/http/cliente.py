"""API de la app de escritorio del trabajo: vincular, sesión, estado, actualización, avisos y audios."""

import json
import urllib.parse
from pathlib import Path

from transcripcion.acceso import remoto as R
from transcripcion.acceso import usuarios as U
from transcripcion.base import registro as L
from transcripcion.casos.repositorio import EXT_AUDIO
from transcripcion.http.acceso import avisar_fallo
from transcripcion.http.audios import guardar_audio_nuevo
from transcripcion.operacion import app_cliente as A


def estado(h, pedido):
    """GET /api/cliente/estado."""
    sis = h.sis
    instantanea = sis.vista.listar_casos(h.pc)
    casos = [
        {
            "nombre": c["nombre"],
            "titulo": c["titulo"],
            "estado": c["estado"],
            "marcas": c["marcas"],
            "paciente": c["paciente"],
        }
        for c in instantanea
        if c["origen"] == h.pc
    ][:40]
    cola = sum(1 for c in instantanea if c["estado"] in ("en cola", "transcribiendo", "generando"))
    A.anotar_version(h.pc, h.headers.get("User-Agent"))
    h._json(
        {
            "ok": True,
            "pc": h.pc,
            "ia": sis.ia.ia_lista(),
            "cola": cola,
            "casos": casos,
            "version": sis.version,
            "app": A.resumen(),
        }
    )


def actualizacion(h, pedido):
    """GET /api/cliente/actualizacion."""
    # lista de archivos de la app con sus huellas: la app baja solo los que cambiaron
    h._json(A.manifiesto())


def archivo(h, pedido):
    """GET /api/cliente/archivo."""
    q = pedido.q
    rel = q.get("ruta", [""])[0]
    p = A.archivo(rel)
    if not p or not p.exists():
        h.send_error(404)
        return
    if rel.lower() == "transcripcion.exe" and L.una_vez(("app_baja", h.pc, A.resumen()["huella"]), 3600):
        L.info("APP", f"{h.pc} está bajando la versión {A.resumen()['version'] or 'nueva'} de la app.")
    h._enviar_archivo(p)


def vincular(h, pedido):
    """POST /api/cliente/vincular."""
    sis = h.sis
    d = json.loads(h._body(64 * 1024) or b"{}")
    pc_nueva = str(d.get("pc", "")).strip()
    usu = str(d.get("usuario") or "").strip()
    llave, err = R.vincular(pc_nueva, str(d.get("contrasena", "")), h._ip(), usuario=usu or None)
    if err:
        if err.startswith(("Contraseña", "Usuario")):
            avisar_fallo(pc_nueva, h._ip(), "al vincular la aplicación" + (f" (usuario «{usu[:24]}»)" if usu else ""))
        else:
            L.aviso("ACCESO", f"No se vinculó «{pc_nueva[:24]}» (IP {h._ip()}): {err}")
        return h._json({"error": err}, 403)
    L.ok(
        "ACCESO",
        f"PC vinculada: {pc_nueva} (IP {h._ip()})"
        + (f" con el usuario «{usu[:40]}»" if usu else "")
        + ". Ya puede enviar audios.",
    )
    r = {"ok": True, "llave": llave, "pc": d["pc"].strip(), "version": sis.version}
    usu_ok = U.verificar(usu, str(d.get("contrasena", ""))) if usu and U.hay_usuarios() else None
    if usu_ok:  # la página abre ya con este transcriptor: no se le pide el usuario dos veces
        r["codigo"] = R.nuevo_codigo(pc_nueva, usuario=usu_ok, seg=180)
    return h._json(r)


def sesion(h, pedido):
    """POST /api/cliente/sesion."""
    if not h._llave() or not R.pc_de_llave(h._llave()):
        if L.una_vez(("llave", h._ip()), 600):
            L.aviso(
                "ACCESO",
                f"Una aplicación con una llave no autorizada (¿PC anulada?) intentó entrar desde la IP {h._ip()}.",
            )
        return h._json({"error": "Esta PC no está autorizada"}, 401)
    d = json.loads(h._body(16 * 1024) or b"{}")
    # «reconectar»: la app ya estaba abierta y volvió a conectarse (servidor caído o reiniciado, dirección
    # nueva del túnel): sigue la persona que tenía la sesión abierta en esta PC, sin pedirle el usuario
    usu = R.usuario_de_pc(h.pc) if isinstance(d, dict) and d.get("reconectar") is True else None
    return h._json({"ok": True, "codigo": R.nuevo_codigo(h.pc, usuario=usu)})


def aviso(h, pedido):
    """POST /api/cliente/aviso."""
    # la app avisa algo que conviene ver en el servidor (ej. una actualización que no abrió)
    d = json.loads(h._body(16 * 1024) or b"{}")
    texto = " ".join(str(d.get("texto", "")).split())[:400]
    if texto:
        (L.ok if d.get("tipo") == "ok" else L.aviso)("APP", f"{h.pc}: {texto}")
    return h._json({"ok": True})


def audio(h, pedido):
    """POST /api/cliente/audio."""
    original = urllib.parse.unquote(h.headers.get("X-Archivo") or "audio.wav")
    if Path(original).suffix.lower() not in EXT_AUDIO:
        L.aviso("AUDIO", f"{h.pc} envió «{original}»: formato de audio no soportado.")
        return h._json({"error": "Formato de audio no soportado"}, 400)
    r, err = guardar_audio_nuevo(h, original, h._body(), h.headers.get("X-Huella"))
    return h._json(r) if r else h._json({"error": err}, 422)
