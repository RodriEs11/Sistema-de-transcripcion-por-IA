"""Entrar y salir: formulario de usuario y contraseña, códigos de la app del trabajo y sesiones."""

import urllib.parse

from transcripcion.acceso import remoto as R
from transcripcion.acceso import usuarios as U
from transcripcion.base import registro as L
from transcripcion.casos.repositorio import LOCAL
from transcripcion.http.paginas import plantilla


def entrar_get(h, pedido):
    """GET /entrar."""
    q = pedido.q
    cod = q.get("codigo", [""])[0]
    v = R.tomar_codigo(cod) if cod else None
    if v and h.usuario and v.get("usuario") in (None, h.usuario):
        # la app volvió a entrar (p. ej. después de que el servidor se cayó o se reinició) y esta pantalla ya
        # tiene la sesión de un transcriptor: se conserva, no se la cambia por una sesión sin usuario
        L.info("ACCESO", f"{h.quien} volvió a conectarse con su sesión (IP {h._ip()}).")
        return h._redirigir("/")
    sid = R.canjear_codigo(cod, pc_local=None if h.remoto else LOCAL, v=v) if v else None
    if sid:
        v = R.sesion(sid) or {}
        if v.get("usuario"):
            U.anotar_entrada(v["usuario"])
        L.info(
            "ACCESO",
            f"{v.get('pc')} abrió la aplicación"
            + (f" con {U.nombre_de(v['usuario'])}" if v.get("usuario") else "")
            + f" (IP {h._ip()}).",
        )
        return h._redirigir("/", R.cookie_sesion(sid, local=not h.remoto))
    if cod:
        L.aviso("ACCESO", f"Código de entrada vencido o inválido desde la IP {h._ip()}.")
    if h.usuario or (not h.remoto and not U.hay_usuarios()):
        return h._redirigir("/")
    return pagina_entrar(h)


def ingresar_get(h, pedido):
    """GET /ingresar."""
    if h.usuario or not U.hay_usuarios():
        return h._redirigir("/")
    if h.remoto and not h.pc:
        return h._redirigir("/entrar")
    return pagina_entrar(h)


def salir(h, pedido):
    """GET /salir."""
    v = R.cerrar_sesion(h._cookie("ts"))
    if v:
        L.info(
            "ACCESO",
            (f"{U.nombre_de(v['usuario'])} salió en {v['pc']}." if v.get("usuario") else f"{v['pc']} cerró la sesión."),
        )
    if v and v.get("usuario") and not v.get("local"):
        # en el trabajo la PC sigue identificada: el que sigue solo escribe su usuario y contraseña
        return h._redirigir("/ingresar", R.cookie_sesion(R.nueva_sesion(v["pc"])))
    return h._redirigir("/ingresar" if not h.remoto and U.hay_usuarios() else "/entrar", R.COOKIE_SESION_BORRAR)


def entrar_post(h, pedido):
    """POST /entrar, /ingresar. Usuario y contraseña (o, sin transcriptores, la del sistema)."""
    return entrar(h, urllib.parse.parse_qs(h._body(64 * 1024).decode("utf-8", "replace")))


def pagina_entrar(h, error="", usuario=""):
    """Formulario para entrar. Con transcriptores creados pide usuario y contraseña (y el nombre de la PC si
    se entra desde un navegador común del trabajo); sin ninguno, como antes: PC y contraseña del sistema."""
    import html as _h

    err = f'<p class="err">{_h.escape(error)}</p>' if error else ""
    hay = U.hay_usuarios()
    pc_conocida = not h.remoto or bool(h.pc)
    if not hay:
        txt = "Para usar el sistema desde esta PC escribí su nombre y la contraseña."
    elif pc_conocida:
        txt = (
            f"Esta PC: <b>{_h.escape(h.pc)}</b>. " if h.remoto else ""
        ) + "Escribí tu usuario y tu contraseña: la IA arma los informes con tu estilo."
    else:
        txt = "Escribí el nombre de esta PC, tu usuario y tu contraseña."
    campos = ""
    if h.remoto and not pc_conocida:
        campos += (
            '<label>Nombre de esta PC<input name="pc" placeholder="info-01" required '
            'autocomplete="organization"></label>'
        )
    if hay:
        campos += (
            f'<label>Usuario<input name="usuario" value="{_h.escape(usuario)}" required autofocus '
            f'autocomplete="username"></label>'
        )
    campos += (
        '<label>Contraseña<input name="contrasena" type="password" required autocomplete="current-password"></label>'
    )
    accion = "/ingresar" if hay and pc_conocida else "/entrar"
    h._html(
        plantilla(h.sis, "entrar.html")
        .replace("{{texto}}", txt)
        .replace("{{error}}", err)
        .replace("{{campos}}", campos)
        .replace("{{accion}}", accion),
        401 if error else 200,
    )


def entrar(h, f):
    """POST /entrar: transcriptor (o, sin transcriptores, la contraseña del sistema desde el trabajo)."""
    ip = h._ip()
    pc = (h.pc or (f.get("pc", [""])[0]).strip()) if h.remoto else LOCAL
    nombre = (f.get("usuario", [""])[0]).strip()
    clave_fallo = ip if h.remoto else f"local:{nombre.casefold()}"
    if R.demasiados_fallos(clave_fallo):
        L.aviso(
            "ACCESO",
            f"Intento de entrar como «{(nombre or pc)[:24]}» desde la IP {ip} rechazado: "
            f"está bloqueada 10 minutos por contraseñas incorrectas.",
        )
        return pagina_entrar(h, "Demasiados intentos fallidos. Esperá 10 minutos.", nombre)
    if h.remoto and not R.PC_VALIDA.match(pc):
        return pagina_entrar(h, "Escribí el nombre de esta PC (ej. info-01).", nombre)
    contrasena = f.get("contrasena", [""])[0]
    if not U.hay_usuarios():
        if not h.remoto:
            return h._redirigir("/")
        if not R.contrasena_ok(contrasena):
            R.anotar_fallo(ip)
            avisar_fallo(pc, ip, "desde el navegador")
            return pagina_entrar(h, "Contraseña incorrecta.")
        L.ok("ACCESO", f"{pc} entró desde el navegador (IP {ip}).")
        return h._redirigir("/", R.cookie_sesion(R.nueva_sesion(pc, reemplaza=h._cookie("ts"))))
    usuario = U.verificar(nombre, contrasena)
    if not usuario:
        R.anotar_fallo(clave_fallo)
        k = len(R.FALLOS.get(clave_fallo, []))
        L.aviso(
            "ACCESO",
            f"Usuario o contraseña incorrectos para «{nombre[:24]}» en {pc} (IP {ip})."
            + (" Queda bloqueado 10 minutos." if k >= 5 else f" Intento {k} de 5."),
        )
        return pagina_entrar(h, "Usuario o contraseña incorrectos.", nombre)
    R.FALLOS.pop(clave_fallo, None)
    U.anotar_entrada(usuario)
    sid = R.nueva_sesion(pc, usuario=usuario, local=not h.remoto, reemplaza=h._cookie("ts"))
    L.ok("ACCESO", f"{U.nombre_de(usuario)} entró en {pc}" + (f" (IP {ip})." if h.remoto else "."))
    return h._redirigir("/", R.cookie_sesion(sid, local=not h.remoto))


def avisar_fallo(pc, ip, donde):
    k = len(R.FALLOS.get(ip, []))
    extra = " La IP queda bloqueada 10 minutos." if k >= 5 else f" Intento {k} de 5."
    L.aviso("ACCESO", f"Contraseña incorrecta para «{pc[:24]}» {donde} (IP {ip}).{extra}")
