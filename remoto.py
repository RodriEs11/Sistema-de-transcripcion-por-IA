# -*- coding: utf-8 -*-
"""
ACCESO REMOTO: lo que necesita el servidor para que las PC del trabajo (info-01, info-02...)
se conecten por el tunel rapido de Cloudflare.

- Contrasena del sistema (se guarda solo su "huella" PBKDF2, nunca la contrasena).
- Una llave por PC: se crea al vincular la PC y se puede anular.
- Sesiones de la interfaz (cookie de 12 h) y codigos de un solo uso para que la app entre sin
  volver a pedir la contrasena.
- Bloqueo de casos: un caso abierto en una PC no se puede abrir en otra.
- Medico elegido por PC.
- Tunel: arranca cloudflared, toma la direccion *.trycloudflare.com y la publica en un canal de
  avisos (ntfy.sh) con nombre secreto para que la app la encuentre sola.

Los pedidos que llegan por el tunel traen los encabezados de Cloudflare (Cf-Ray, Cf-Connecting-Ip):
esos SIEMPRE necesitan llave o sesion. Los que vienen directo de esta PC (127.0.0.1) no.
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

import registro as L

AQUI = Path(__file__).resolve().parent
ARCH = AQUI / "acceso_remoto.json"
CARPETA_CLIENTE = AQUI / "cliente"
NTFY = "https://ntfy.sh"
SESION_SEG = 12 * 3600
BLOQUEO_SEG = 45
_lock = threading.RLock()

SESIONES = {}    # sid -> {"pc", "exp"}
CODIGOS = {}     # codigo -> {"pc", "exp"}
BLOQUEOS = {}    # nombre de caso -> {"pc", "t"}
FALLOS = {}      # ip -> [tiempos de intentos fallidos]   (para el panel: "admin:<pc>" -> [...])
ADMIN_SES = {}   # token -> {"pc", "ip", "desde", "ult", "exp"}: panel de administración abierto desde una PC del trabajo
ADMIN_MAX_SEG = 8 * 3600        # una sesión del panel dura como mucho 8 horas
ADMIN_INACTIVA_SEG = 30 * 60    # y se cierra sola tras 30 minutos sin usarla
URL_TUNEL = {"url": None, "desde": None, "proceso": None,
             # para el panel de administración
             "estado": None, "publicada": None, "error_pub": None, "reinicios": 0, "centro": None,
             "iniciado": False, "cambio": None}
_PEDIDO = {"reinicio": False}
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


def vincular(pc, contrasena, ip):
    """Devuelve (llave, error)."""
    if demasiados_fallos(ip):
        return None, "Demasiados intentos fallidos. Esperá 10 minutos."
    if not PC_VALIDA.match(pc or ""):
        return None, "El nombre de la PC solo puede tener letras, números y guiones (ej. info-01)."
    if not contrasena_ok(contrasena):
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
        for sid in [s for s, v in SESIONES.items() if v["pc"] == pc]:
            SESIONES.pop(sid, None)
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
    return sum(1 for v in SESIONES.values() if v["pc"] == pc and v["exp"] > ahora)


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


def nueva_sesion(pc):
    sid = secrets.token_urlsafe(32)
    with _lock:
        ahora = time.time()
        for s in [s for s, v in SESIONES.items() if v["exp"] < ahora]:
            SESIONES.pop(s, None)
        SESIONES[sid] = {"pc": pc, "exp": ahora + SESION_SEG}
    return sid


def pc_de_sesion(sid):
    v = SESIONES.get(sid or "")
    if not v or v["exp"] < time.time():
        return None
    return v["pc"]


def cerrar_sesion(sid):
    SESIONES.pop(sid or "", None)


def cookie_sesion(sid):
    return f"ts={sid}; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age={SESION_SEG}"


# -------------------------------------------------------------- bloqueos
def bloquear(nombre, pc):
    """True si quedó para esta PC; si no, devuelve la PC que lo tiene."""
    ahora = time.time()
    with _lock:
        b = BLOQUEOS.get(nombre)
        if b and b["pc"] != pc and ahora - b["t"] < BLOQUEO_SEG:
            return b["pc"]
        BLOQUEOS[nombre] = {"pc": pc, "t": ahora}
    return True


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
        f.write_text(json.dumps(d, ensure_ascii=False, indent=0), encoding="utf-8")


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
            f.write_text(json.dumps(resto, ensure_ascii=False, indent=0), encoding="utf-8")


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
def publicar_url(url):
    tema = _leer().get("tema_aviso")
    if not tema:
        return False
    try:
        req = urllib.request.Request(f"{NTFY}/{tema}", data=url.encode("utf-8"), method="POST",
                                     headers={"Title": "Transcripcion", "Cache": "yes"})
        urllib.request.urlopen(req, timeout=15).read()
        L.debug("TÚNEL", f"Dirección publicada en el canal de avisos: {url}")
        URL_TUNEL.update(publicada=time.time(), error_pub=None)
        return True
    except Exception as ex:
        URL_TUNEL.update(error_pub=f"{ex}"[:200])
        L.aviso("TÚNEL", f"No se pudo publicar la dirección en el canal de avisos (ntfy.sh): {ex}. "
                         f"Si las aplicaciones no se conectan solas, escribí la dirección a mano.")
        return False


def _estado_tunel(e):
    URL_TUNEL.update(estado=e, cambio=time.time())
    L.estado(tunel=e)


def reiniciar_tunel():
    """Desde el panel: cierra cloudflared y el hilo del túnel lo vuelve a abrir enseguida (dirección nueva).
    Devuelve un texto de error o None."""
    if not URL_TUNEL.get("iniciado"):
        return "El túnel no está en marcha (el servidor se abrió sin acceso remoto)."
    p = URL_TUNEL.get("proceso")
    if URL_TUNEL.get("estado") == "sin cloudflared" or p is None:
        return "No encuentro cloudflared.exe: ejecutá iniciar_servidor.bat para descargarlo."
    if p.poll() is not None:
        return "El túnel ya se está volviendo a abrir."
    _PEDIDO["reinicio"] = True
    try:
        p.terminate()
    except Exception as ex:
        _PEDIDO["reinicio"] = False
        return f"No se pudo cerrar cloudflared: {ex}"
    return None


def cerrar_tunel():
    """Al apagar el servidor: cerrar cloudflared para que no quede andando solo."""
    p = URL_TUNEL.get("proceso")
    if p and p.poll() is None:
        try:
            p.terminate()
            L.info("TÚNEL", "Túnel cerrado.")
        except Exception:
            pass


def iniciar_tunel(puerto, exe):
    """Corre cloudflared en un hilo; si se cae lo vuelve a abrir y publica la dirección nueva."""
    def hilo():
        vez = 0
        while True:
            vez += 1
            L.info("TÚNEL", "Abriendo el túnel de Cloudflare para las PC del trabajo…" if vez == 1
                   else "Volviendo a abrir el túnel…")
            _estado_tunel("abriendo")
            try:
                p = subprocess.Popen([str(exe), "tunnel", "--no-autoupdate", "--url", f"http://127.0.0.1:{puerto}"],
                                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                     encoding="utf-8", errors="replace",
                                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            except FileNotFoundError:
                L.error("TÚNEL", f"No encuentro {Path(exe).name}. Ejecutá iniciar_servidor.bat para descargarlo. "
                                 f"Mientras tanto el sistema funciona solo en esta PC.")
                _estado_tunel("sin cloudflared")
                return
            URL_TUNEL["proceso"] = p
            conectado = False
            for linea in p.stdout:
                linea = linea.rstrip()
                if not linea.strip():
                    continue
                L.debug("TÚNEL", "cloudflared: " + linea)      # todo lo de cloudflared queda en el archivo
                m = re.search(r"https://[a-z0-9-]+\.trycloudflare\.com", linea)
                if m and m.group(0) != URL_TUNEL["url"]:
                    URL_TUNEL.update(url=m.group(0), desde=time.time())
                    L.ok("TÚNEL", "Dirección para las PC del trabajo:", det=[m.group(0)])
                    if publicar_url(m.group(0)):
                        L.ok("TÚNEL", "Dirección publicada: las aplicaciones del trabajo la encuentran solas.")
                elif "Registered tunnel connection" in linea and not conectado:
                    conectado = True
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
            URL_TUNEL.update(url=None, desde=None, centro=None)
            URL_TUNEL["reinicios"] += 1
            _estado_tunel("reconectando")
            if _PEDIDO["reinicio"]:
                _PEDIDO["reinicio"] = False
                L.info("TÚNEL", "Túnel cerrado desde el panel de administración: se abre de nuevo con otra dirección.")
                time.sleep(1)
                continue
            L.aviso("TÚNEL", f"El túnel se cerró (código {cod}). Lo vuelvo a abrir en 10 s; la dirección nueva "
                             f"se publica sola.")
            time.sleep(10)

    def republicar():   # cloudflared puede quedar callado horas: republicar igual
        while True:
            time.sleep(3 * 3600)
            if URL_TUNEL["url"]:
                publicar_url(URL_TUNEL["url"])

    if URL_TUNEL.get("iniciado"):
        return
    URL_TUNEL["iniciado"] = True
    threading.Thread(target=hilo, daemon=True, name="tunel").start()
    threading.Thread(target=republicar, daemon=True, name="tunel-republicar").start()
