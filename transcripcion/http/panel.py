"""Panel de administración: páginas y consultas, permisos y entrada desde las PC del trabajo.

El estado que muestra está en panel_estado.py y lo que hacen sus botones, en panel_acciones.py.
"""

import json

from transcripcion.acceso import admin as ADM
from transcripcion.acceso import remoto as R
from transcripcion.aprendizaje import correcciones as CORR
from transcripcion.base import registro as L
from transcripcion.conocimiento import medicos as MED
from transcripcion.http.paginas import plantilla
from transcripcion.http.panel_acciones import accion_admin
from transcripcion.http.panel_estado import estado_admin
from transcripcion.operacion import estadisticas as EST

# páginas del panel de administración (solo en esta PC); cada una se abre en su pestaña del navegador
PAGINAS_ADMIN = {
    "/admin": "admin.html",
    "/admin/estadisticas": "estadisticas.html",
    "/admin/correcciones": "correcciones.html",
    "/admin/medicos": "medicos.html",
}


def consultar(h, pedido):
    """GET páginas del panel, /api/admin/…"""
    sis = h.sis
    q = pedido.q
    acc = ADM.acceso(h, sis.puerto)
    if acc is None:
        return panel_sin_permiso(h, pedido.ruta)
    visor = {"remoto": acc == "remoto", "pc": h.pc if acc == "remoto" else None}
    if pedido.ruta in PAGINAS_ADMIN:
        h._html((sis.web / PAGINAS_ADMIN[pedido.ruta]).read_bytes())
    elif pedido.ruta == "/api/admin/estado":
        h._json(dict(estado_admin(sis), visor=visor))
    elif pedido.ruta == "/api/admin/medicos":
        h._json({"medicos": [{"nombre": m, "notas": MED.notas_medico(m)} for m in MED.lista_medicos()], "visor": visor})
    elif pedido.ruta == "/api/admin/estadisticas":
        try:
            dias = int((q.get("dias") or ["30"])[0])
        except ValueError:
            dias = 30
        h._json(
            dict(
                EST.calcular(dias, medico_actual=sis.casos.medico_de, estudios_actual=sis.casos.estudios_de),
                visor=visor,
            )
        )
    elif pedido.ruta == "/api/admin/correcciones":
        try:
            dias = int((q.get("dias") or ["0"])[0])
        except ValueError:
            dias = 0
        h._json(
            dict(
                CORR.calcular(
                    dias,
                    (q.get("medico") or [""])[0],
                    medico_actual=sis.casos.medico_de,
                    puntuacion=(q.get("puntuacion") or [""])[0] == "1",
                ),
                visor=visor,
            )
        )
    else:
        h.send_error(404)


def entrar(h, pedido):
    """POST /api/admin/entrar."""
    datos = pedido.datos
    return panel_entrar(h, datos)


def salir(h, pedido):
    """POST /api/admin/salir."""
    if h.remoto and R.cerrar_sesion_admin(h._cookie("ta")):
        L.info("ACCESO", f"{h.pc} salió del panel de administración.")
    return h._json({"ok": True}, cookie=R.COOKIE_ADMIN_BORRAR if h.remoto else None)


def accion(h, pedido):
    """POST /api/admin/…"""
    sis = h.sis
    datos = pedido.datos
    acc = ADM.acceso(h, sis.puerto)
    if acc is None or not ADM.mismo_origen(h, sis.puerto):
        if acc is None and h.remoto and R.admin_configurado() and ADM.mismo_origen(h, sis.puerto):
            return h._json(
                {"error": "La sesión del panel venció: volvé a escribir su contraseña.", "entrar_panel": True}, 401
            )
        L.aviso("ACCESO", f"Pedido al panel de administración rechazado ({pedido.ruta}, {h.pc}, IP {h._ip()}).")
        return h._json({"error": "No tenés permiso para usar el panel de administración."}, 403)
    return h._json(
        *accion_admin(sis, pedido.ruta[len("/api/admin/") :], datos, quien=h.pc if acc == "remoto" else None)
    )


def panel_sin_permiso(h, ruta):
    """Pedido al panel sin permiso. Desde el trabajo: si el panel está habilitado, se pide su contraseña."""
    sis = h.sis
    es_pagina = ruta in PAGINAS_ADMIN
    if h.remoto:
        if R.admin_configurado():
            if es_pagina:
                return h._html(pagina_panel_entrar(sis, h.pc, ruta))
            return h._json(
                {"error": "La sesión del panel venció: volvé a escribir su contraseña.", "entrar_panel": True}, 401
            )
        if L.una_vez(("admin_remoto", h.pc), 600):
            L.aviso(
                "ACCESO",
                f"{h.pc} intentó abrir el panel de administración, pero no está habilitado para "
                f"las PC del trabajo (falta configurar su contraseña en el panel del servidor).",
            )
        if es_pagina:
            return h._html(plantilla(sis, "panel_no_habilitado.html"))
        return h._json({"error": "El panel de administración no está habilitado para las PC del trabajo."}, 403)
    if L.una_vez(("admin_host", h.headers.get("Host")), 600):
        L.aviso(
            "ACCESO",
            f"Pedido al panel de administración con la dirección «{(h.headers.get('Host') or '')[:60]}» "
            f"rechazado: en esta PC el panel se abre como http://127.0.0.1:{sis.puerto}/admin.",
        )
    if es_pagina:
        return h._html(plantilla(sis, "panel_solo_local.html"), 403)
    return h._json({"error": f"El panel de administración se abre como http://127.0.0.1:{sis.puerto:d}/admin."}, 403)


def panel_entrar(h, datos):
    sis = h.sis
    if not h.remoto:
        return h._json({"ok": True})  # en la PC del servidor no hace falta contraseña
    ip = h._ip()
    motivo = ADM.motivo_origen(h, sis.puerto)
    if motivo:
        L.aviso(
            "ACCESO",
            f"Pedido para entrar al panel desde {h.pc} rechazado: no vino de la página del panel (IP {ip}; {motivo}).",
        )
        return h._json({"error": "Pedido rechazado."}, 403)
    if not R.admin_configurado():
        return h._json({"error": "El panel de administración no está habilitado para las PC del trabajo."}, 403)
    clave = f"admin:{h.pc}"
    if R.demasiados_fallos(clave):
        if L.una_vez(("admin_bloq", h.pc), 120):
            L.aviso(
                "ACCESO",
                f"{h.pc} sigue intentando entrar al panel de administración: bloqueado 10 minutos "
                f"por contraseñas incorrectas (IP {ip}).",
            )
        return h._json({"error": "Demasiados intentos fallidos. Esperá 10 minutos."}, 429)
    if not R.contrasena_admin_ok(str(datos.get("contrasena", ""))):
        R.anotar_fallo(clave)
        k = len(R.FALLOS.get(clave, []))
        L.aviso(
            "ACCESO",
            f"Contraseña del panel de administración incorrecta desde {h.pc} (IP {ip}). "
            + ("Esa PC queda bloqueada 10 minutos para el panel." if k >= 5 else f"Intento {k} de 5."),
        )
        return h._json(
            {
                "error": "Contraseña incorrecta."
                + ("" if k >= 5 else f" Te quedan {5 - k} {'intento' if 5 - k == 1 else 'intentos'}.")
            },
            401,
        )
    R.FALLOS.pop(clave, None)
    tok = R.nueva_sesion_admin(h.pc, ip)
    L.ok("ACCESO", f"{h.pc} entró al panel de administración desde el trabajo (IP {ip}).")
    return h._json({"ok": True}, cookie=R.cookie_admin(tok))


def pagina_panel_entrar(sis, pc, volver):
    import html as _h

    return (
        plantilla(sis, "panel_entrar.html")
        .replace("{{pc}}", _h.escape(pc or ""))
        .replace("{{volver}}", json.dumps(volver if volver in PAGINAS_ADMIN else "/admin"))
    )
