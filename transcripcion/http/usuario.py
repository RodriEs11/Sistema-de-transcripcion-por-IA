"""Lo de cada transcriptor: su PC, su estilo y lo que cambia de sí mismo."""

from transcripcion.acceso import remoto as R
from transcripcion.acceso import usuarios as U
from transcripcion.base import registro as L
from transcripcion.conocimiento import medicos as MED
from transcripcion.conocimiento import plantillas as PL


def mi_pc(h, pedido):
    """GET /api/mi_pc."""
    du = U.datos(h.usuario) if h.usuario else None
    h._json(
        {
            "pc": h.pc,
            "remoto": h.remoto,
            "medico": R.medico_pc(h.pc),
            "admin": (not h.remoto) or R.admin_configurado(),  # si se muestra el engranaje del panel
            "con_usuarios": U.hay_usuarios(),
            "usuario": {"clave": du["clave"], "nombre": du["nombre"], "cambiar": du["cambiar"]} if du else None,
            # None = nunca guardó preferencias: la página sube las de esta PC
            "preferencias": U.preferencias(h.usuario)
            if du and U.archivo(h.usuario, "preferencias.json").exists()
            else None,
        }
    )


def estilo(h, pedido):
    """GET /api/usuario/estilo."""
    sis = h.sis
    if not h.usuario:
        return h._json({"error": "Entrá con tu usuario."}, 403)
    h._json(
        {
            "formato": U.formato(h.usuario),
            "general": {k: sis.cfg.get(k) for k in U.FORMATO},
            "fuentes": list(U.FUENTES),
            "reglas": U.leer_archivo(h.usuario, "reglas_dictado.md"),
            "plantillas_propias": [n for n, _ in PL.secciones_de_usuario(h.usuario)],
            "medicos_propios": MED.medicos_con_notas_propias(h.usuario),
        }
    )


def accion(h, pedido):
    """POST /api/usuario/…"""
    datos = pedido.datos
    if not h.usuario:
        return h._json({"error": "Entrá con tu usuario."}, 403)
    return h._json(*accion_usuario(pedido.ruta[len("/api/usuario/") :], datos, h.usuario, h.pc))


def accion_usuario(accion, d, usuario, pc):
    """Lo que cada transcriptor cambia de sí mismo. Devuelve (respuesta, código)."""
    nombre = U.nombre_de(usuario)
    if accion == "contrasena":
        err = U.cambiar_propia(usuario, str(d.get("actual") or ""), str(d.get("nueva") or ""))
        if err:
            return {"error": err}, 400
        L.ok("ACCESO", f"{nombre} cambió su contraseña ({pc}).")
        return {"ok": True}, 200
    if accion == "preferencias":
        return {"ok": True, "preferencias": U.guardar_preferencias(usuario, d.get("preferencias"))}, 200
    if accion == "formato":
        try:
            f = U.guardar_formato(usuario, d.get("formato") or {})
        except ValueError as ex:
            return {"error": str(ex)}, 400
        L.info(
            "CONFIG",
            f"{nombre} cambió el formato de su Word ({pc}): "
            + (", ".join(f"{k}={v}" for k, v in f.items()) or "vuelve al general")
            + ".",
        )
        return {"ok": True, "formato": f}, 200
    if accion == "reglas":
        texto = d.get("reglas")
        if not isinstance(texto, str) or len(texto) > 50_000:
            return {"error": "Las reglas tienen que ser texto (como mucho 50.000 caracteres)."}, 400
        U.escribir_archivo(usuario, "reglas_dictado.md", texto.strip() + "\n" if texto.strip() else "")
        L.ok("CONFIG", f"{nombre} guardó sus reglas de dictado propias ({pc}).")
        return {"ok": True}, 200
    return {"error": "Acción desconocida"}, 404
