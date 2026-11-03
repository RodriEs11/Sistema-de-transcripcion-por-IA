# -*- coding: utf-8 -*-
"""
ACCESO REMOTO: lo que necesita el servidor para que las PC del trabajo (info-01, info-02...)
se conecten por un tunel: el rapido de Cloudflare o Microsoft Dev Tunnels (se elige con configurar_tunel).

- Contrasena del sistema (se guarda solo su "huella" PBKDF2, nunca la contrasena). Cuando hay transcriptores
  creados (usuarios.py) ya no sirve para entrar: cada uno entra con su usuario y su contrasena.
- Una llave por PC: se crea al vincular la PC y se puede anular.
- Sesiones de la interfaz (cookie hasta cerrar la app, 12 h como mucho, con el transcriptor que entro) y codigos de un solo uso para que la app entre sin
  volver a pedir la contrasena.
- Bloqueo de casos: un caso abierto en una PC no se puede abrir en otra.
- Medico elegido por PC.
- Tunel: arranca cloudflared (direccion *.trycloudflare.com, cambia en cada reinicio) o devtunnel
  (direccion *.devtunnels.ms fija) y la publica en un canal de avisos (ntfy.sh) con nombre secreto
  para que la app la encuentre sola.

Los pedidos que llegan por Cloudflare traen sus encabezados (Cf-Ray, Cf-Connecting-Ip); los de Dev
Tunnels llegan a un puerto propio (PUERTO_TUNEL) donde todo cuenta como remoto. Esos SIEMPRE necesitan
llave o sesion. Los que vienen directo de esta PC (127.0.0.1, puerto de la interfaz) no.
"""
import hashlib
import hmac
import json
import re
import secrets
import subprocess
import threading
import time
import urllib.request
from pathlib import Path

import plataforma as P
import registro as L
import usuarios as U
from persistencia import escribir_atomico

AQUI = Path(__file__).resolve().parent
ARCH = AQUI / "acceso_remoto.json"
ARCH_SESIONES = AQUI / "sesiones.json"
CARPETA_CLIENTE = AQUI / "cliente"
NTFY = "https://ntfy.sh"
SESION_SEG = 12 * 3600
SESION_INACTIVA_SEG = 30 * 60     # sesión con transcriptor sin ninguna consulta de la página en ese tiempo: se cierra
ACTIVO_SEG = 5 * 60               # «usuario activo» de una PC: su página consultó en los últimos 5 minutos
BLOQUEO_SEG = 45
_lock = threading.RLock()

SESIONES = {}    # huella del sid -> {"pc", "exp", "usuario", "local", "ult"}
CODIGOS = {}     # codigo -> {"pc", "exp"}
BLOQUEOS = {}    # nombre de caso -> {"pc", "t" (última señal), "desde" (cuándo lo abrió)}
LIBERADOS = {}   # nombre de caso -> {"pc", "t"}: casos que el panel le sacó a una PC
LIBERADO_SEG = 15 * 60
FALLOS = {}      # ip -> [tiempos de intentos fallidos]   (para el panel: "admin:<pc>" -> [...])
ADMIN_SES = {}   # token -> {"pc", "ip", "desde", "ult", "exp"}: panel de administración abierto desde una PC del trabajo
ADMIN_MAX_SEG = 8 * 3600        # una sesión del panel dura como mucho 8 horas
ADMIN_INACTIVA_SEG = 30 * 60    # y se cierra sola tras 30 minutos sin usarla
URL_TUNEL = {"url": None, "desde": None, "proceso": None,
             # para el panel de administración
             "estado": None, "publicada": None, "error_pub": None, "reinicios": 0, "centro": None,
             "iniciado": False, "cambio": None, "servicio": None, "url_publicada": None}
_PEDIDO = {"reinicio": False, "despertar": False, "cerrando": False}
ULTIMA_GRABADA = {}  # pc -> cuándo se guardó por última vez su última conexión (para no escribir en cada pedido)


# ---------------------------------------------------------------- datos
def _leer():
    if ARCH.exists():
        try:
            return json.loads(ARCH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _grabar(d):
    tmp = ARCH.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(ARCH)


def configurado():
    return bool(_leer().get("contrasena"))


def _huella_contrasena(c, sal):
    return hashlib.pbkdf2_hmac("sha256", c.encode("utf-8"), bytes.fromhex(sal), 200_000).hex()


def poner_contrasena(c):
    with _lock:
        d = _leer()
        sal = secrets.token_hex(16)
        d["contrasena"] = {"sal": sal, "huella": _huella_contrasena(c, sal)}
        d.setdefault("tema_aviso", "transcripcion-" + secrets.token_urlsafe(18).replace("_", "").replace("-", "")[:24])
        d.setdefault("clientes", {})
        d.setdefault("medico_pc", {})
        _grabar(d)
        escribir_conexion_cliente(d)
    return d


# ------------------------------------------- panel de administración desde el trabajo
# Contraseña aparte de la del acceso remoto: solo quien la sepa puede abrir el panel desde una PC del trabajo
# (que además tiene que estar vinculada o con sesión). Se configura únicamente en la PC del servidor.
def admin_configurado():
    return bool(_leer().get("contrasena_admin"))


def admin_desde():
    return (_leer().get("contrasena_admin") or {}).get("desde")


def poner_contrasena_admin(c):
    with _lock:
        d = _leer()
        sal = secrets.token_hex(16)
        d["contrasena_admin"] = {"sal": sal, "huella": _huella_contrasena(c, sal), "desde": time.strftime("%Y-%m-%d %H:%M")}
        _grabar(d)
    return cerrar_sesiones_admin()      # las sesiones abiertas con la contraseña anterior dejan de valer


def quitar_contrasena_admin():
    with _lock:
        d = _leer()
        d.pop("contrasena_admin", None)
        _grabar(d)
    return cerrar_sesiones_admin()


def contrasena_admin_ok(c):
    d = _leer().get("contrasena_admin")
    if not d or not c:
        return False
    return hmac.compare_digest(_huella_contrasena(c, d["sal"]), d["huella"])


def nueva_sesion_admin(pc, ip):
    tok = secrets.token_urlsafe(32)
    ahora = time.time()
    with _lock:
        for t in [t for t, v in ADMIN_SES.items() if not _admin_vigente(v, ahora)]:
            ADMIN_SES.pop(t, None)
        ADMIN_SES[tok] = {"pc": pc, "ip": ip, "desde": ahora, "ult": ahora, "exp": ahora + ADMIN_MAX_SEG}
    return tok


def _admin_vigente(v, ahora):
    return v["exp"] > ahora and ahora - v["ult"] < ADMIN_INACTIVA_SEG


def admin_de(tok, pc):
    """True si el token es una sesión del panel vigente de esa PC (y la renueva)."""
    if not tok or not pc or not admin_configurado():
        return False
    with _lock:
        v = ADMIN_SES.get(tok)
        ahora = time.time()
        if not v or v["pc"] != pc or not _admin_vigente(v, ahora):
            if v:
                ADMIN_SES.pop(tok, None)
                if v["pc"] != pc:      # la cookie de una PC apareció en otra: por las dudas se anula
                    L.aviso("ACCESO", f"La sesión del panel de {v['pc']} se usó desde {pc}: se cerró por seguridad.")
            return False
        v["ult"] = ahora
    return True


def cerrar_sesion_admin(tok):
    with _lock:
        return ADMIN_SES.pop(tok or "", None)


def cerrar_sesiones_admin(pc=None):
    with _lock:
        ts = [t for t, v in ADMIN_SES.items() if pc is None or v["pc"] == pc]
        for t in ts:
            ADMIN_SES.pop(t, None)
    return len(ts)


def sesiones_admin():
    ahora = time.time()
    with _lock:
        return sorted(({"pc": v["pc"], "desde": v["desde"], "ult": v["ult"]} for v in ADMIN_SES.values()
                       if _admin_vigente(v, ahora)), key=lambda x: x["desde"])


def cookie_admin(tok):
    # Strict: el navegador no la manda en pedidos que vengan de otro sitio
    return f"ta={tok}; Path=/; HttpOnly; Secure; SameSite=Strict; Max-Age={ADMIN_MAX_SEG}"


COOKIE_ADMIN_BORRAR = "ta=; Path=/; HttpOnly; Secure; SameSite=Strict; Max-Age=0"


def escribir_conexion_cliente(d=None):
    """Archivo que va junto a Transcripcion.exe para que encuentre este servidor."""
    d = d or _leer()
    if not d.get("tema_aviso"):
        return
    CARPETA_CLIENTE.mkdir(exist_ok=True)
    (CARPETA_CLIENTE / "conexion.json").write_text(
        json.dumps({"tema": d["tema_aviso"], "aviso": NTFY}, indent=1), encoding="utf-8")


def contrasena_ok(c):
    d = _leer().get("contrasena")
    if not d or not c:
        return False
    return hmac.compare_digest(_huella_contrasena(c, d["sal"]), d["huella"])


def demasiados_fallos(ip):
    ahora = time.time()
    with _lock:
        FALLOS[ip] = [t for t in FALLOS.get(ip, []) if ahora - t < 600]
        return len(FALLOS[ip]) >= 5


def anotar_fallo(ip):
    with _lock:
        FALLOS.setdefault(ip, []).append(time.time())


PC_VALIDA = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,23}$")


def vincular(pc, contrasena, ip, usuario=None):
    """Devuelve (llave, error). Con transcriptores creados se vincula con el usuario y la contraseña de
    cualquiera de ellos (la contraseña compartida del sistema deja de servir); sin ninguno, como antes."""
    if demasiados_fallos(ip):
        return None, "Demasiados intentos fallidos. Esperá 10 minutos."
    if not PC_VALIDA.match(pc or ""):
        return None, "El nombre de la PC solo puede tener letras, números y guiones (ej. info-01)."
    if U.hay_usuarios():
        if not usuario:
            anotar_fallo(ip)
            return None, ("Contraseña incorrecta. Ahora cada transcriptor entra con su usuario: actualizá la "
                          "aplicación o pedí al administrador que conecte esta PC.")
        if not U.verificar(usuario, contrasena):
            anotar_fallo(ip)
            return None, "Usuario o contraseña incorrectos."
    elif not contrasena_ok(contrasena):
        anotar_fallo(ip)
        return None, "Contraseña incorrecta."
    llave = secrets.token_urlsafe(32)
    with _lock:
        d = _leer()
        d.setdefault("clientes", {})[hashlib.sha256(llave.encode()).hexdigest()] = {
            "pc": pc, "creado": time.strftime("%Y-%m-%d %H:%M")}
        _grabar(d)
    return llave, None


def pc_de_llave(llave):
    if not llave:
        return None
    c = _leer().get("clientes", {}).get(hashlib.sha256(llave.encode()).hexdigest())
    return c["pc"] if c else None


def anular_pc(pc):
    with _lock:
        d = _leer()
        antes = len(d.get("clientes", {}))
        d["clientes"] = {k: v for k, v in d.get("clientes", {}).items() if v["pc"] != pc}
        d.get("pcs_info", {}).pop(pc, None)       # que no siga figurando en el panel
        ULTIMA_GRABADA.pop(pc, None)
        _grabar(d)
        for h in [s for s, v in SESIONES.items() if v["pc"] == pc]:
            SESIONES.pop(h, None)
        _guardar_sesiones()
        for caso in [c for c, b in BLOQUEOS.items() if b["pc"] == pc]:
            BLOQUEOS.pop(caso, None)
        cerrar_sesiones_admin(pc)
    return antes - len(d["clientes"])


def pcs_vinculadas():
    """{pc: {"llaves", "vinculada" (primera), "ultima_vinculacion", "ultima" (última conexión guardada), "version"}}."""
    d = _leer()
    out = {}
    for c in d.get("clientes", {}).values():
        x = out.setdefault(c["pc"], {"llaves": 0, "vinculada": c.get("creado"), "ultima_vinculacion": c.get("creado")})
        x["llaves"] += 1
        if c.get("creado") and (not x["vinculada"] or c["creado"] < x["vinculada"]):
            x["vinculada"] = c["creado"]
        if c.get("creado") and (not x["ultima_vinculacion"] or c["creado"] > x["ultima_vinculacion"]):
            x["ultima_vinculacion"] = c["creado"]
    for pc, info in d.get("pcs_info", {}).items():
        out.setdefault(pc, {"llaves": 0, "vinculada": None, "ultima_vinculacion": None}).update(
            ultima=info.get("ultima"), version=info.get("version"))
    return out


def anotar_visto(pc, version=None):
    """Guarda en acceso_remoto.json la última conexión de cada PC (como mucho cada 5 min por PC),
    para que el panel la muestre aunque se haya reiniciado el servidor."""
    ahora = time.time()
    if not pc or ahora - ULTIMA_GRABADA.get(pc, 0) < 300:
        return
    ULTIMA_GRABADA[pc] = ahora
    try:
        with _lock:
            d = _leer()
            if not d:
                return
            info = d.setdefault("pcs_info", {}).setdefault(pc, {})
            info["ultima"] = round(ahora)
            if version:
                info["version"] = version
            _grabar(d)
    except OSError:
        pass


def sesiones_de(pc):
    ahora = time.time()
    return sum(1 for v in list(SESIONES.values()) if v["pc"] == pc and _sesion_vigente(v, ahora))


# -------------------------------------------------------------- sesiones
def nuevo_codigo(pc):
    c = secrets.token_urlsafe(24)
    with _lock:
        CODIGOS[c] = {"pc": pc, "exp": time.time() + 60}
    return c


def canjear_codigo(c):
    with _lock:
        v = CODIGOS.pop(c or "", None)
    if not v or v["exp"] < time.time():
        return None
    return nueva_sesion(v["pc"])


def _h(sid):
    """Las sesiones se guardan por la huella del identificador: el archivo no sirve para entrar."""
    return hashlib.sha256(sid.encode()).hexdigest() if sid else ""


def _limpiar_sesiones(ahora):
    for s in [s for s, v in SESIONES.items() if not _sesion_vigente(v, ahora)]:
        SESIONES.pop(s, None)


def _sesion_vigente(v, ahora):
    if v["exp"] < ahora:
        return False
    # con transcriptor: la página consulta cada pocos segundos; si deja de hacerlo (se cerró la app o el
    # navegador) la sesión se cierra sola aunque la cookie siguiera viva
    return not v.get("usuario") or ahora - v.get("ult", ahora) < SESION_INACTIVA_SEG


def _guardar_sesiones():
    """Solo las sesiones con transcriptor: así un reinicio del servidor no obliga a volver a entrar."""
    try:
        datos = {h: {k: v[k] for k in ("pc", "exp", "usuario", "local") if k in v}
                 for h, v in SESIONES.items() if v.get("usuario")}
        escribir_atomico(ARCH_SESIONES, json.dumps(datos, ensure_ascii=False))
    except OSError:
        L.aviso("ACCESO", "No se pudieron guardar las sesiones abiertas (al reiniciar habrá que volver a entrar).", exc=True)


def cargar_sesiones():
    try:
        datos = json.loads(ARCH_SESIONES.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return 0
    ahora = time.time()
    with _lock:
        for h, v in (datos or {}).items():
            if isinstance(v, dict) and v.get("exp", 0) > ahora and v.get("usuario") and v.get("pc"):
                SESIONES[h] = {**v, "ult": ahora}
    return len(SESIONES)


def nueva_sesion(pc, usuario=None, local=False, reemplaza=None):
    """Sesión de la página. Sin usuario solo sirve para elegir quién entra (la PC ya está identificada)."""
    sid = secrets.token_urlsafe(32)
    with _lock:
        ahora = time.time()
        _limpiar_sesiones(ahora)
        if reemplaza:
            SESIONES.pop(_h(reemplaza), None)
        SESIONES[_h(sid)] = {"pc": pc, "exp": ahora + SESION_SEG, "usuario": usuario, "local": bool(local), "ult": ahora}
        if usuario:
            _guardar_sesiones()
    return sid


def sesion(sid):
    """{"pc", "usuario", "local"} de una sesión vigente (y la marca como usada), o None."""
    if not sid:
        return None
    with _lock:
        v = SESIONES.get(_h(sid))
        ahora = time.time()
        if not v or not _sesion_vigente(v, ahora):
            if v:
                SESIONES.pop(_h(sid), None)
            return None
        v["ult"] = ahora
        return dict(v)


def pc_de_sesion(sid):
    v = sesion(sid)
    return v["pc"] if v and not v.get("local") else None


def cerrar_sesion(sid):
    with _lock:
        v = SESIONES.pop(_h(sid), None)
        if v and v.get("usuario"):
            _guardar_sesiones()
    return v


def cerrar_sesiones_usuario(usuario):
    """Al desactivar un transcriptor o restablecerle la contraseña."""
    with _lock:
        hs = [h for h, v in SESIONES.items() if v.get("usuario") == usuario]
        for h in hs:
            SESIONES.pop(h, None)
        if hs:
            _guardar_sesiones()
    return len(hs)


def usuario_activo(pc):
    """Transcriptor que está usando la página en esa PC ahora (para los audios que la app toma sola)."""
    ahora = time.time()
    with _lock:
        cand = [v for v in SESIONES.values() if v["pc"] == pc and v.get("usuario") and _sesion_vigente(v, ahora)
                and ahora - v.get("ult", 0) < ACTIVO_SEG]
    return max(cand, key=lambda v: v.get("ult", 0))["usuario"] if cand else None


def sesiones_de_usuarios():
    """{usuario: [pc, ...]} de las sesiones vigentes (para el panel)."""
    ahora = time.time()
    out = {}
    with _lock:
        for v in SESIONES.values():
            if v.get("usuario") and _sesion_vigente(v, ahora):
                out.setdefault(v["usuario"], []).append(v["pc"])
    return out


def cookie_sesion(sid, local=False):
    # sin Max-Age: la cookie dura hasta que se cierra la app (o el navegador). En la PC del servidor la página es
    # http://127.0.0.1, sin «Secure» para que el navegador la acepte.
    return f"ts={sid}; Path=/; HttpOnly;{'' if local else ' Secure;'} SameSite=Lax"


COOKIE_SESION_BORRAR = "ts=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax"


# -------------------------------------------------------------- bloqueos
LIBERADO = object()      # respuesta de bloquear(): el panel de administración le sacó el caso a esta PC


def bloquear(nombre, pc, renovar=False):
    """True si quedó para esta PC; si no, devuelve la PC que lo tiene (o LIBERADO).
    renovar: la página que ya tenía el caso abierto avisa que sigue ahí (cada 15 s). Si el panel le liberó el
    caso, la renovación se rechaza; abrirlo de nuevo a propósito sí se puede."""
    ahora = time.time()
    with _lock:
        lib = LIBERADOS.get(nombre)
        if lib and ahora - lib["t"] > LIBERADO_SEG:
            LIBERADOS.pop(nombre, None)
            lib = None
        if lib and lib["pc"] == pc:
            if renovar:
                return LIBERADO
            LIBERADOS.pop(nombre, None)
        b = BLOQUEOS.get(nombre)
        vigente = b and ahora - b["t"] < BLOQUEO_SEG
        if vigente and b["pc"] != pc:
            return b["pc"]
        desde = b.get("desde", b["t"]) if vigente else ahora
        BLOQUEOS[nombre] = {"pc": pc, "t": ahora, "desde": desde}
    return True


def liberar(nombre):
    """Desde el panel: saca el caso a la PC que lo tiene abierto (por ejemplo, si esa PC se apagó o quedó
    abierta sin nadie). Devuelve la PC que lo tenía o None."""
    with _lock:
        b = BLOQUEOS.pop(nombre, None)
        if not b or time.time() - b["t"] >= BLOQUEO_SEG:
            return None
        LIBERADOS[nombre] = {"pc": b["pc"], "t": time.time()}
        return b["pc"]


def liberado_para(nombre, pc):
    """True si el panel le liberó este caso a esta PC (y no lo volvió a abrir): sus cambios ya no se guardan."""
    lib = LIBERADOS.get(nombre)
    return bool(lib and lib["pc"] == pc and time.time() - lib["t"] <= LIBERADO_SEG)


def soltar(nombre, pc):
    with _lock:
        b = BLOQUEOS.get(nombre)
        if b and b["pc"] == pc:
            BLOQUEOS.pop(nombre, None)


def bloqueado_por(nombre, pc):
    b = BLOQUEOS.get(nombre)
    if b and b["pc"] != pc and time.time() - b["t"] < BLOQUEO_SEG:
        return b["pc"]
    return None


# ---------------------------------------------------------- medico por PC
def medico_pc(pc):
    return _leer().get("medico_pc", {}).get(pc, "")


def poner_medico_pc(pc, med):
    with _lock:
        d = _leer()
        d.setdefault("medico_pc", {})[pc] = med
        _grabar(d)


# -------------------------------------------------------------- huellas
def archivo_huellas(datos):
    return datos / "_huellas.json"


def buscar_huella(datos, h):
    f = archivo_huellas(datos)
    if not f.exists():
        return None
    return json.loads(f.read_text(encoding="utf-8")).get(h)


def guardar_huella(datos, h, nombre):
    with _lock:
        f = archivo_huellas(datos)
        d = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
        d[h] = nombre
        escribir_atomico(f, json.dumps(d, ensure_ascii=False, indent=0))


def quitar_huellas(datos, nombre):
    """Al borrar un caso: olvida la huella de su audio, así si se vuelve a enviar se procesa de nuevo."""
    with _lock:
        f = archivo_huellas(datos)
        if not f.exists():
            return
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except ValueError:
            return
        resto = {h: n for h, n in d.items() if n != nombre}
        if len(resto) != len(d):
            escribir_atomico(f, json.dumps(resto, ensure_ascii=False, indent=0))


def nombre_unico(pc, original, existe):
    base = Path(original).stem
    base = re.sub(r"[^\w\- ]+", "", base, flags=re.UNICODE).strip().replace(" ", "-")[:60] or "audio"
    n = f"{pc}_{time.strftime('%Y%m%d-%H%M%S')}_{base}"
    k, final = 2, n
    while existe(final):
        final = f"{n}-{k}"
        k += 1
    return final


# ----------------------------------------------------------------- tunel
# Dos servicios posibles (se elige con configurar_tunel; queda en acceso_remoto.json -> "tunel"):
#  - "cloudflare": túnel rápido sin cuenta (*.trycloudflare.com). La dirección cambia en cada reinicio.
#  - "devtunnel":  Microsoft Dev Tunnels con una cuenta de Microsoft o GitHub (*.devtunnels.ms). Túnel
#                  persistente: la dirección es SIEMPRE la misma. Reenvía al puerto propio del túnel
#                  (PUERTO_TUNEL, 8766 por defecto), donde el servidor trata todo como remoto, sin
#                  depender de los encabezados que agregue Microsoft.
SERVICIOS = {"cloudflare": "Cloudflare", "devtunnel": "Microsoft Dev Tunnels"}
RE_CLOUDFLARE = re.compile(r"https://(?!api\.)[a-z0-9]+(?:-[a-z0-9]+)+\.trycloudflare\.com")
REPUBLICAR_SEG = 3 * 3600


def config_tunel():
    t = _leer().get("tunel")
    return t if isinstance(t, dict) else {}


def servicio_tunel():
    s = config_tunel().get("servicio") or "cloudflare"
    return s if s in SERVICIOS else "cloudflare"


def nombre_servicio(s=None):
    return SERVICIOS[s or servicio_tunel()]


def guardar_config_tunel(**cambios):
    d = _leer()
    t = d.get("tunel") if isinstance(d.get("tunel"), dict) else {}
    t.update(cambios)
    d["tunel"] = t
    _grabar(d)


def publicar_url(url, forzar=False):
    """Publica la dirección en el canal de avisos (ntfy.sh). Sin forzar, no repite la misma dirección
    publicada hace menos de una hora (antes, un túnel que se caía cada 10 s llenaba el canal: error 429)."""
    tema = _leer().get("tema_aviso")
    if not tema or not url:
        return False
    if (not forzar and URL_TUNEL.get("url_publicada") == url and URL_TUNEL.get("publicada")
            and time.time() - URL_TUNEL["publicada"] < 3600):
        return True
    try:
        req = urllib.request.Request(f"{NTFY}/{tema}", data=url.encode("utf-8"), method="POST",
                                     headers={"Title": "Transcripcion", "Cache": "yes"})
        urllib.request.urlopen(req, timeout=15).read()
        L.debug("TÚNEL", f"Dirección publicada en el canal de avisos: {url}")
        URL_TUNEL.update(publicada=time.time(), error_pub=None, url_publicada=url)
        return True
    except Exception as ex:
        URL_TUNEL.update(error_pub=f"{ex}"[:200])
        if forzar or L.una_vez(("ntfy", f"{ex}"[:60]), 600):
            L.aviso("TÚNEL", f"No se pudo publicar la dirección en el canal de avisos (ntfy.sh): {ex}. "
                             f"Si las aplicaciones no se conectan solas, escribí la dirección a mano.")
        return False


def _estado_tunel(e):
    URL_TUNEL.update(estado=e, cambio=time.time())
    L.estado(tunel=e)


def reiniciar_tunel():
    """Desde el panel: cierra el programa del túnel y el hilo lo vuelve a abrir enseguida.
    Devuelve un texto de error o None."""
    if not URL_TUNEL.get("iniciado"):
        return "El túnel no está en marcha (el servidor se abrió sin acceso remoto)."
    p = URL_TUNEL.get("proceso")
    est = URL_TUNEL.get("estado")
    if est in ("sin cloudflared", "sin devtunnel"):
        return f"Falta el programa del túnel: ejecutá {P.script('configurar_tunel')}."
    if p is None or p.poll() is not None:
        if est in ("sin sesion", "sin configurar", "error"):
            _PEDIDO["despertar"] = True         # p. ej. ya se volvió a iniciar sesión: probar ahora, sin esperar
            return None
        _PEDIDO["despertar"] = True
        return "El túnel ya se está volviendo a abrir."
    _PEDIDO["reinicio"] = True
    try:
        p.terminate()
    except Exception as ex:
        _PEDIDO["reinicio"] = False
        return f"No se pudo cerrar el programa del túnel: {ex}"
    return None


def cerrar_tunel():
    """Al apagar el servidor: cerrar el programa del túnel para que no quede andando solo."""
    _PEDIDO["cerrando"] = True          # que el hilo del túnel no lo vuelva a abrir mientras el servidor se cierra
    _PEDIDO["despertar"] = True
    p = URL_TUNEL.get("proceso")
    if p and p.poll() is None:
        try:
            p.terminate()
            L.info("TÚNEL", "Túnel cerrado.")
        except Exception:
            pass


def _esperar(seg):
    """Espera antes de reabrir el túnel; el botón «Reiniciar túnel» del panel la corta."""
    fin = time.time() + seg
    while time.time() < fin and not _PEDIDO.get("despertar"):
        time.sleep(0.5)
    _PEDIDO["despertar"] = False


# ---------------------------------------------------------------- Microsoft Dev Tunnels
def _correr(args, timeout=90):
    """Corre devtunnel y devuelve (código, salida). Código None = no se pudo correr."""
    try:
        r = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=timeout, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except FileNotFoundError:
        return None, "no existe"
    except subprocess.TimeoutExpired:
        return 1, "tiempo agotado"


def falta_sesion(texto):
    t = (texto or "").lower()
    return any(p in t for p in ("not logged in", "login required", "user login", "log in", "sign in",
                                "unauthorized", "not authenticated", "token expired", "token has expired"))


def no_existe(texto):
    t = (texto or "").lower()
    return any(p in t for p in ("not found", "does not exist", "no tunnel"))


def crear_devtunnel(exe, tid, puerto):
    """Crea el túnel persistente con acceso anónimo y su puerto. Devuelve (id con región o None, salida)."""
    cod, sal = _correr([str(exe), "create", tid, "--allow-anonymous", "--expiration", "30d"])
    if cod != 0 and "already" not in sal.lower() and "conflict" not in sal.lower():
        return None, sal
    m = re.search(r"Tunnel ID\s*:\s*(\S+)", sal)
    completo = m.group(1) if m else tid
    cod2, sal2 = _correr([str(exe), "port", "create", completo, "-p", str(puerto), "--protocol", "http"])
    if cod2 != 0 and "already" not in sal2.lower() and "conflict" not in sal2.lower():
        return None, sal + "\n" + sal2
    return completo, sal + "\n" + sal2


def asegurar_devtunnel(exe, puerto):
    """Antes de abrirlo: que haya sesión iniciada y que el túnel exista con su puerto (si Microsoft lo borró
    por falta de uso, se crea de nuevo con el mismo nombre). Devuelve (id, None) o (None, estado)."""
    tid = (config_tunel().get("devtunnel") or {}).get("id")
    if not tid:
        return None, "sin configurar"
    cod, sal = _correr([str(exe), "show", tid])
    if cod is None:
        return None, "sin devtunnel"
    L.debug("TÚNEL", "devtunnel show: " + " | ".join(x.strip() for x in sal.splitlines() if x.strip())[:600])
    if cod != 0:
        if falta_sesion(sal) and not no_existe(sal):
            return None, "sin sesion"
        if no_existe(sal):
            L.aviso("TÚNEL", f"El túnel «{tid}» ya no existe en Microsoft (se borran tras 30 días sin usar). "
                             f"Lo creo de nuevo con el mismo nombre.")
            nuevo, sal2 = crear_devtunnel(exe, tid.split(".")[0], puerto)
            if not nuevo:
                L.error("TÚNEL", "No se pudo crear el túnel de nuevo: " + sal2.strip()[-300:])
                return None, "sin sesion" if falta_sesion(sal2) else "error"
            d = dict(config_tunel().get("devtunnel") or {})
            d.update(id=nuevo, creado=time.time())
            guardar_config_tunel(devtunnel=d)
            return nuevo, None
        L.aviso("TÚNEL", "devtunnel respondió con un error: " + sal.strip()[-300:])
        return None, "error"
    if not re.search(rf"\b{puerto}\b", sal):         # el túnel existe pero no tiene el puerto
        cod2, sal2 = _correr([str(exe), "port", "create", tid, "-p", str(puerto), "--protocol", "http"])
        L.debug("TÚNEL", "devtunnel port create: " + sal2.strip()[:300])
    return tid, None


def _hilo_devtunnel(puerto):
    exe = P.ruta_devtunnel()
    fallos = 0
    while True:
        _estado_tunel("abriendo")
        tid, problema = asegurar_devtunnel(exe, puerto)
        if problema:
            _estado_tunel(problema)
            URL_TUNEL["reinicios"] += 1
            if problema == "sin devtunnel":
                L.error("TÚNEL", f"No encuentro {Path(exe).name}. Ejecutá {P.script('configurar_tunel')} para "
                                 f"descargarlo e iniciar sesión. Mientras tanto el sistema funciona solo en esta PC.")
            elif problema == "sin configurar":
                L.error("TÚNEL", f"Microsoft Dev Tunnels todavía no está configurado: ejecutá "
                                 f"{P.script('configurar_tunel')}. Mientras tanto el sistema funciona solo en esta PC.")
            elif problema == "sin sesion":
                L.error("TÚNEL", f"La sesión de Microsoft Dev Tunnels venció o no está iniciada: ejecutá "
                                 f"{P.script('configurar_tunel')} y volvé a entrar con tu cuenta. Lo reintento cada 5 minutos.")
            _esperar(300 if problema != "error" else min(30 * 2 ** fallos, 300))
            fallos += 1
            continue
        L.info("TÚNEL", "Abriendo el túnel de Microsoft (Dev Tunnels) para las PC del trabajo…" if not fallos
               else "Volviendo a abrir el túnel de Microsoft…")
        try:
            p = subprocess.Popen([str(exe), "host", tid], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                 text=True, encoding="utf-8", errors="replace",
                                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except FileNotFoundError:
            _estado_tunel("sin devtunnel")
            _esperar(300)
            continue
        URL_TUNEL["proceso"] = p
        re_url = re.compile(rf"https://[a-z0-9-]+-{puerto}\.([a-z0-9]+)\.devtunnels\.ms")
        sesion = False
        for linea in p.stdout:
            linea = linea.rstrip()
            if not linea.strip():
                continue
            L.debug("TÚNEL", "devtunnel: " + linea)
            m = re_url.search(linea)
            bajo = linea.lower()
            if m:
                url = m.group(0)
                if url != URL_TUNEL["url"]:
                    URL_TUNEL.update(url=url, desde=time.time(), centro=m.group(1))
                    L.ok("TÚNEL", "Dirección para las PC del trabajo (siempre la misma):", det=[url])
                    if publicar_url(url):
                        L.ok("TÚNEL", "Dirección publicada: las aplicaciones del trabajo la encuentran solas.")
                if URL_TUNEL.get("estado") != "activo":
                    L.ok("TÚNEL", f"Túnel conectado con Microsoft (región {m.group(1)}). Ya se puede usar desde el trabajo.")
                    _estado_tunel("activo")
                    fallos = 0
            elif "relay" in bajo and ("lost" in bajo or "disconnect" in bajo):
                L.aviso("TÚNEL", "Se cortó la conexión con Microsoft; devtunnel la recupera solo.")
                _estado_tunel("reconectando")
            elif "relay" in bajo and ("restored" in bajo or "reconnected" in bajo):
                if URL_TUNEL.get("url"):
                    L.ok("TÚNEL", "Conexión con Microsoft recuperada.")
                    _estado_tunel("activo")
            elif falta_sesion(linea) and not sesion:
                sesion = True
                L.error("TÚNEL", f"Microsoft Dev Tunnels pide iniciar sesión: ejecutá {P.script('configurar_tunel')}.")
            elif re.search(r"\b(error|fail|failed|exception)\b", bajo):
                clave = re.sub(r"[0-9a-f]{6,}|\d+", "#", linea)[:80]
                if L.una_vez(("devtunnel", clave), 300):
                    L.aviso("TÚNEL", "Microsoft Dev Tunnels informó un problema: " + linea.strip()[:200])
        cod = p.wait()
        if _PEDIDO["cerrando"]:
            return                           # el servidor se está cerrando (o reiniciando): no reabrir
        URL_TUNEL["reinicios"] += 1
        URL_TUNEL["proceso"] = None
        if _PEDIDO["reinicio"]:
            _PEDIDO["reinicio"] = False
            _estado_tunel("reconectando")
            L.info("TÚNEL", "Túnel cerrado desde el panel de administración: se abre de nuevo (la dirección no cambia).")
            time.sleep(1)
            continue
        fallos += 1
        espera = 300 if sesion else min(10 * 2 ** (fallos - 1), 300)
        _estado_tunel("sin sesion" if sesion else "reconectando")
        L.aviso("TÚNEL", f"El túnel de Microsoft se cerró (código {cod}). Lo vuelvo a abrir en {espera} s.")
        _esperar(espera)


# ---------------------------------------------------------------- Cloudflare (túnel rápido)
def _hilo_cloudflare(puerto):
    exe = P.ruta_cloudflared()
    vez = 0
    fallos = 0          # cierres seguidos sin llegar a conectarse: la espera crece (10 s, 20 s, 40 s… hasta 5 min)
    while True:
        vez += 1
        if vez == 1:
            L.info("TÚNEL", "Abriendo el túnel de Cloudflare para las PC del trabajo…")
        elif fallos < 3 or L.una_vez(("cloudflared", "reabrir"), 1800):
            L.info("TÚNEL", "Volviendo a abrir el túnel…")
        _estado_tunel("abriendo")
        try:
            p = subprocess.Popen([str(exe), "tunnel", "--no-autoupdate", "--url", f"http://127.0.0.1:{puerto}"],
                                 stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                 encoding="utf-8", errors="replace",
                                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except FileNotFoundError:
            L.error("TÚNEL", f"No encuentro {Path(exe).name}. Ejecutá {P.script('iniciar_servidor')} para descargarlo. "
                             f"Mientras tanto el sistema funciona solo en esta PC.")
            _estado_tunel("sin cloudflared")
            return
        URL_TUNEL["proceso"] = p
        conectado = False
        sin_dns = False
        for linea in p.stdout:
            linea = linea.rstrip()
            if not linea.strip():
                continue
            L.debug("TÚNEL", "cloudflared: " + linea)      # todo lo de cloudflared queda en el archivo
            m = RE_CLOUDFLARE.search(linea)
            if "failed to request quick tunnel" in linea.lower():
                if "no such host" in linea.lower() or "lookup" in linea.lower():
                    sin_dns = True
                continue
            if m and m.group(0) != URL_TUNEL["url"]:
                URL_TUNEL.update(url=m.group(0), desde=time.time())
                L.ok("TÚNEL", "Dirección para las PC del trabajo:", det=[m.group(0)])
                if publicar_url(m.group(0)):
                    L.ok("TÚNEL", "Dirección publicada: las aplicaciones del trabajo la encuentran solas.")
            elif "Registered tunnel connection" in linea and not conectado:
                conectado = True
                fallos = 0
                lugar = re.search(r"location=(\S+)", linea)
                URL_TUNEL["centro"] = lugar.group(1) if lugar else None
                L.ok("TÚNEL", "Túnel conectado con Cloudflare" + (f" (centro {lugar.group(1)})" if lugar else "")
                     + ". Ya se puede usar desde el trabajo.")
                _estado_tunel("activo")
            else:
                e = re.match(r"^\S+\s+ERR\s+(.*)$", linea)
                if e:
                    clave = re.sub(r"[0-9a-f]{6,}|\d+", "#", e.group(1))[:80]
                    if L.una_vez(("cloudflared", clave), 300):
                        L.aviso("TÚNEL", "Cloudflare informó un problema: " + e.group(1)[:200])
        cod = p.wait()
        if _PEDIDO["cerrando"]:
            return                           # el servidor se está cerrando (o reiniciando): no reabrir
        URL_TUNEL.update(url=None, desde=None, centro=None, proceso=None)
        URL_TUNEL["reinicios"] += 1
        _estado_tunel("reconectando")
        if _PEDIDO["reinicio"]:
            _PEDIDO["reinicio"] = False
            L.info("TÚNEL", "Túnel cerrado desde el panel de administración: se abre de nuevo con otra dirección.")
            time.sleep(1)
            continue
        if not conectado:
            fallos += 1
        espera = min(10 * 2 ** max(fallos - 1, 0), 300)
        if sin_dns and L.una_vez(("cloudflared", "sin_dns"), 1800):
            L.error("TÚNEL", "Esta PC no encuentra el servicio de túneles rápidos de Cloudflare (api.trycloudflare.com "
                             "no existe para su DNS: puede estar bloqueado por el proveedor de internet o caído). "
                             f"Alternativa: Microsoft Dev Tunnels, con {P.script('configurar_tunel')}.")
        if fallos < 3 or L.una_vez(("cloudflared", "cerrado"), 1800):
            L.aviso("TÚNEL", f"El túnel se cerró (código {cod}). Lo vuelvo a abrir en {espera} s; la dirección nueva "
                             f"se publica sola.")
        _esperar(espera)


def iniciar_tunel(puerto, puerto_tunel=None):
    """Abre el túnel elegido en un hilo; si se cae lo vuelve a abrir.
    puerto = el de la interfaz (Cloudflare); puerto_tunel = el propio del túnel (Dev Tunnels)."""
    def republicar():   # el programa del túnel puede quedar callado horas: republicar igual (el aviso dura 12 h)
        while True:
            time.sleep(REPUBLICAR_SEG)
            if URL_TUNEL["url"]:
                publicar_url(URL_TUNEL["url"], forzar=True)

    if URL_TUNEL.get("iniciado"):
        return
    URL_TUNEL["iniciado"] = True
    URL_TUNEL["servicio"] = s = servicio_tunel()
    if s == "devtunnel":
        threading.Thread(target=_hilo_devtunnel, args=(puerto_tunel or puerto + 1,), daemon=True, name="tunel").start()
    else:
        threading.Thread(target=_hilo_cloudflare, args=(puerto,), daemon=True, name="tunel").start()
    threading.Thread(target=republicar, daemon=True, name="tunel-republicar").start()
