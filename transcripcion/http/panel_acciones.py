"""Botones del panel de administración: médicos, transcriptores, túnel, PC, contraseñas, reinicio, mensajes,
casos y correcciones."""

from transcripcion import RAIZ
from transcripcion.acceso import admin as ADM
from transcripcion.acceso import remoto as R
from transcripcion.acceso import usuarios as U
from transcripcion.aprendizaje import correcciones as CORR
from transcripcion.base import registro as L
from transcripcion.conocimiento import medicos as MED

# Lo que desde una PC del trabajo no se puede hacer aunque se tenga la contraseña del panel: abrir carpetas o
# archivos (se abrirían en la pantalla del servidor) y tocar la contraseña del propio panel o sus sesiones.
SOLO_EN_EL_SERVIDOR = {
    "abrir",
    "contrasena_admin",
    "contrasena_admin/quitar",
    "sesiones_admin/cerrar",
    "correcciones/regla",
    "caso/pausar",
    "caso/reanudar",
}


def accion_admin(sis, accion, d, quien=None):
    """Botones del panel. Devuelve (respuesta, código). quien = PC del trabajo que usa el panel (None = esta PC)."""
    desde = f"desde el panel de administración (usado en {quien})" if quien else "desde el panel de administración"
    if accion in ("medicos/agregar", "medicos/modificar", "medicos/eliminar"):
        try:
            if accion == "medicos/eliminar":
                MED.eliminar_medico(d.get("original"))
                nombre = d.get("original")
            else:
                if accion == "medicos/modificar" and not isinstance(d.get("original"), str):
                    return {"error": "Elegí el médico que querés modificar."}, 400
                nombre = MED.guardar_medico(
                    d.get("nombre", ""),
                    d.get("notas", ""),
                    crear=accion == "medicos/agregar",
                    original=d.get("original") if accion == "medicos/modificar" else None,
                )
            L.ok("CONFIG", f"Médicos: {accion.split('/')[-1]} «{nombre}» {desde}.")
            return {"ok": True, "medico": nombre}, 200
        except FileExistsError as ex:
            return {"error": str(ex)}, 409
        except FileNotFoundError as ex:
            return {"error": str(ex)}, 404
        except ValueError as ex:
            return {"error": str(ex)}, 400
    if accion.startswith("usuarios/"):
        clave = str(d.get("usuario") or "")
        try:
            if accion == "usuarios/crear":
                clave = U.crear(d.get("nombre", ""), str(d.get("contrasena") or ""))
                L.ok(
                    "ACCESO",
                    f"Transcriptor creado: {U.nombre_de(clave)} {desde}. Entra con la contraseña inicial "
                    f"y la cambia la primera vez.",
                )
                return {"ok": True, "usuario": clave, "msg": f"Listo: {U.nombre_de(clave)} ya puede entrar."}, 200
            if accion == "usuarios/contrasena":
                U.poner_contrasena(clave, str(d.get("contrasena") or ""), cambiar=True)
                n = R.cerrar_sesiones_usuario(clave)
                L.ok(
                    "ACCESO",
                    f"Contraseña de {U.nombre_de(clave)} restablecida {desde}"
                    + (f"; se cerraron {L.plural(n, 'sesión abierta', 'sesiones abiertas')}." if n else "."),
                )
                return {"ok": True, "msg": "Contraseña restablecida: la cambia la próxima vez que entre."}, 200
            if accion == "usuarios/activo":
                activo = d.get("activo") is True
                U.activar(clave, activo)
                if not activo:
                    R.cerrar_sesiones_usuario(clave)
                L.ok(
                    "ACCESO", f"Transcriptor {U.nombre_de(clave)} {'reactivado' if activo else 'desactivado'} {desde}."
                )
                return {"ok": True}, 200
            if accion == "usuarios/nombre":
                U.renombrar(clave, d.get("nombre", ""))
                L.ok("ACCESO", f"Transcriptor renombrado a {U.nombre_de(clave)} {desde}.")
                return {"ok": True}, 200
        except FileExistsError as ex:
            return {"error": str(ex)}, 409
        except FileNotFoundError as ex:
            return {"error": str(ex)}, 404
        except ValueError as ex:
            return {"error": str(ex)}, 400
        return {"error": "Acción desconocida"}, 404
    if quien and accion in SOLO_EN_EL_SERVIDOR:
        L.aviso(
            "ACCESO", f"{quien} intentó «{accion}» en el panel de administración: solo se puede en la PC del servidor."
        )
        return {"error": "Eso solo se puede hacer en la PC del servidor."}, 403
    if accion == "tunel/reiniciar":
        err = R.reiniciar_tunel()
        if err:
            return {"error": err}, 409
        L.info("TÚNEL", f"Reinicio del túnel pedido {desde}.")
        if R.URL_TUNEL.get("servicio") == "devtunnel":
            return {"ok": True, "msg": "Túnel reiniciándose: en unos segundos vuelve, con la misma dirección."}, 200
        return {
            "ok": True,
            "msg": "Túnel reiniciándose: en unos segundos tiene dirección nueva y se publica sola.",
        }, 200
    if accion == "tunel/publicar":
        url = R.URL_TUNEL.get("url")
        if not url:
            return {"error": "Todavía no hay dirección para publicar."}, 409
        if not R.publicar_url(url, forzar=True):
            return {"error": "No se pudo publicar en ntfy.sh: " + (R.URL_TUNEL.get("error_pub") or "sin detalle")}, 502
        L.ok("TÚNEL", f"Dirección publicada de nuevo {desde}.")
        return {"ok": True, "msg": "Dirección publicada: las aplicaciones del trabajo la encuentran solas."}, 200
    if accion == "pc/anular":
        pc = str(d.get("pc", "")).strip()
        if not pc:
            return {"error": "Falta el nombre de la PC."}, 400
        tenia_sesion = R.sesiones_de(pc)
        n = R.anular_pc(pc)
        if not n and not tenia_sesion:
            return {"error": f"No encontré llaves ni sesiones de {pc}."}, 404
        sis.visto.pop(pc, None)
        L.aviso(
            "ACCESO",
            f"PC anulada {desde}: {pc} ({L.plural(n, 'llave')}, "
            f"{L.plural(tenia_sesion, 'sesión abierta', 'sesiones abiertas')}). "
            f"Para volver a usarla hay que vincularla de nuevo con la contraseña.",
        )
        return {"ok": True, "msg": f"{pc} anulada. Para volver a usarla hay que vincularla con la contraseña."}, 200
    if accion == "contrasena":
        c = str(d.get("contrasena", ""))
        if len(c) < 8:
            return {"error": "Usá al menos 8 caracteres."}, 400
        if R.contrasena_admin_ok(c):
            return {"error": "Usá una contraseña distinta de la del panel de administración."}, 400
        ya = R.configurado()
        R.poner_contrasena(c)
        L.ok(
            "ACCESO",
            "Contraseña del acceso remoto "
            + ("cambiada" if ya else "configurada")
            + f" {desde}. Las PC ya vinculadas siguen funcionando.",
        )
        msg = "Contraseña " + ("cambiada" if ya else "guardada") + ". Las PC ya vinculadas siguen funcionando."
        if sis.tunel["modo"] and not R.URL_TUNEL.get("iniciado"):
            sis.abrir_tunel()
            msg += " Abriendo el túnel para las PC del trabajo…"
        return {"ok": True, "msg": msg}, 200
    if accion == "contrasena_admin":
        c = str(d.get("contrasena", ""))
        if len(c) < 10:
            return {"error": "Usá al menos 10 caracteres: con esta contraseña se maneja todo el servidor."}, 400
        if R.contrasena_ok(c):
            return {
                "error": "Usá una contraseña distinta de la del acceso remoto "
                "(esa la conocen todas las PC del trabajo)."
            }, 400
        ya = R.admin_configurado()
        n = R.poner_contrasena_admin(c)
        L.ok(
            "ACCESO",
            "Contraseña del panel de administración desde el trabajo "
            + ("cambiada" if ya else "configurada")
            + ": desde ahora se puede abrir el panel en las PC del trabajo con esa contraseña."
            + (f" Se cerraron {L.plural(n, 'sesión abierta', 'sesiones abiertas')} del panel." if n else ""),
        )
        return {
            "ok": True,
            "msg": ("Contraseña cambiada." if ya else "Listo: el panel ya se puede abrir desde las PC del trabajo.")
            + (f" {_cerradas(n)} del panel abiertas con la anterior." if n else ""),
        }, 200
    if accion == "contrasena_admin/quitar":
        if not R.admin_configurado():
            return {"error": "El panel ya no se puede abrir desde el trabajo."}, 409
        n = R.quitar_contrasena_admin()
        L.aviso(
            "ACCESO",
            "Acceso al panel de administración desde el trabajo desactivado"
            + (f"; se cerraron {L.plural(n, 'sesión abierta', 'sesiones abiertas')}." if n else "."),
        )
        return {
            "ok": True,
            "msg": "Listo: el panel ya no se puede abrir desde las PC del trabajo."
            + (f" {_cerradas(n)}." if n else ""),
        }, 200
    if accion == "sesiones_admin/cerrar":
        n = R.cerrar_sesiones_admin()
        L.info("ACCESO", f"Sesiones del panel de administración cerradas desde esta PC: {n}.")
        return {"ok": True, "msg": f"{_cerradas(n)} del panel." if n else "No había sesiones abiertas."}, 200
    if accion == "reinicio":
        return sis.oper.programar_reinicio(d.get("en"), d.get("avisar", True), d.get("texto"), quien)
    if accion == "reinicio/cancelar":
        return sis.oper.cancelar_reinicio(quien)
    if accion == "reinicio/ya":
        return sis.oper.reiniciar_ya(quien)
    if accion == "mensaje":
        texto = " ".join(str(d.get("texto", "")).split())
        if not texto:
            return {"error": "Escribí el mensaje."}, 400
        if len(texto) > 300:
            return {"error": "El mensaje es muy largo: usá menos de 300 letras."}, 400
        try:
            minutos = max(0, min(int(d.get("minutos") or 0), 24 * 60))
        except (TypeError, ValueError):
            minutos = 0
        tipo = "aviso" if d.get("tipo") == "aviso" else "info"
        if sis.oper.reinicio and sis.oper.reinicio.get("avisar"):
            return {
                "error": "Hay un reinicio programado con su aviso en pantalla: cancelalo o esperá a que termine."
            }, 409
        sis.oper.poner_mensaje(texto, minutos, tipo, por=quien)
        L.info(
            "SERVIDOR", f"Mensaje para las PC {desde}" + (f" (por {minutos} min)" if minutos else "") + f": «{texto}»"
        )
        return {"ok": True, "msg": "Mensaje publicado: aparece en todas las PC en unos segundos."}, 200
    if accion == "mensaje/quitar":
        if sis.oper.reinicio and sis.oper.mensaje.get("reinicio"):
            return {"error": "Ese aviso es del reinicio programado: para quitarlo, cancelá el reinicio."}, 409
        if not sis.oper.quitar_mensaje():
            return {"error": "No hay ningún mensaje en pantalla."}, 409
        L.info("SERVIDOR", f"Mensaje para las PC quitado {desde}.")
        return {"ok": True, "msg": "Mensaje quitado."}, 200
    if accion in ("caso/pausar", "caso/reanudar"):
        n = str(d.get("nombre", ""))
        if not n or "/" in n or "\\" in n or ".." in n:
            return {"error": "Caso inválido."}, 400
        return (sis.proc.pausar if accion == "caso/pausar" else sis.proc.reanudar)(n, "el panel de administración")
    if accion == "caso/liberar":
        n = str(d.get("nombre", ""))
        if not n or "/" in n or "\\" in n or ".." in n:
            return {"error": "Caso inválido."}, 400
        pc = R.liberar(n)
        if not pc:
            return {"error": "Ese caso ya no está abierto en ninguna PC."}, 409
        L.aviso(
            "CASO",
            f"{sis.casos.visible(n)} liberado {desde}: lo tenía abierto {pc}. Lo que escribió hasta su último "
            f"guardado automático quedó como borrador; ya se puede abrir desde otra PC.",
        )
        return {
            "ok": True,
            "msg": f"Caso liberado. {pc} deja de poder guardar cambios en él; ya se puede abrir desde otra PC.",
        }, 200
    if accion == "correcciones/regla":
        r = CORR.agregar_regla(str(d.get("texto", "")))
        if r.get("error"):
            return r, 400
        L.ok(
            "CONFIG",
            f"Regla agregada a reglas_dictado.md {desde}: «{r['linea']}» (copia anterior en conocimiento\\copias).",
        )
        return {"ok": True, "msg": "Regla agregada: la IA la usa desde el próximo informe.", "linea": r["linea"]}, 200
    if accion == "abrir":
        que = d.get("que")
        rutas = {"registros": L.CARPETA, "registro_hoy": L.archivo_del_dia(), "cliente": RAIZ / "cliente"}
        if que not in rutas:
            return {"error": "No sé qué abrir."}, 400
        try:
            if not ADM.abrir_en_windows(rutas[que]):
                return {"error": f"Abrilo a mano: {rutas[que]}"}, 501
        except OSError as ex:
            return {"error": f"No se pudo abrir {rutas[que]}: {ex}"}, 500
        return {"ok": True}, 200
    return {"error": "Acción desconocida."}, 404


def _cerradas(n):
    return "Se cerró 1 sesión" if n == 1 else f"Se cerraron {n} sesiones"
