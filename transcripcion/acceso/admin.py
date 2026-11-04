# -*- coding: utf-8 -*-
"""
PANEL DE ADMINISTRACIÓN (http://127.0.0.1:8765/admin, solo en la PC del servidor).

Acá está lo que no depende del servidor HTTP:
- leer los últimos errores y avisos de los archivos de registros\\ (hoy y ayer);
- decidir si un pedido puede usar el panel (solo esta PC, nunca por el túnel).
El estado completo lo arma servidor.py (que tiene la cola, la IA, etc.).
"""

import re
import threading
import time

from transcripcion.base import plataforma as P
from transcripcion.base import registro as L
from transcripcion.acceso import remoto as R

# 2026-10-25 01:44:02  AVISO  TÚNEL     mensaje
_LINEA = re.compile(r"^(\d{4}-\d\d-\d\d) (\d\d:\d\d:\d\d)  (AVISO|ERROR)\s+(\S+)\s+(.*)$")
_CABECERA = re.compile(r"^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d  ")
_DET = " " * 31 + "· "
_TB = "    | "
_MAX_LEER = 3 * 1024 * 1024  # del final de cada archivo alcanza
_CACHE = {}  # ruta -> (firma, eventos)
_lock = threading.Lock()


def _eventos_de(ruta):
    """Avisos y errores de un archivo del día, en orden. Se cachea por tamaño y fecha."""
    try:
        st = ruta.stat()
    except OSError:
        return []
    firma = (st.st_size, st.st_mtime_ns)
    with _lock:
        c = _CACHE.get(ruta)
        if c and c[0] == firma:
            return c[1]
    try:
        with open(ruta, "rb") as f:
            if st.st_size > _MAX_LEER:
                f.seek(st.st_size - _MAX_LEER)
                f.readline()  # la primera puede venir cortada
            texto = f.read().decode("utf-8", "replace")
    except OSError:
        return []
    eventos, actual = [], None
    for linea in texto.splitlines():
        m = _LINEA.match(linea)
        if m:
            actual = {
                "fecha": m.group(1),
                "hora": m.group(2),
                "nivel": m.group(3).lower(),
                "area": m.group(4),
                "msg": m.group(5).strip(),
                "det": [],
                "tb": [],
            }
            eventos.append(actual)
            continue
        if actual is None:
            continue
        if linea.startswith(_DET):
            if len(actual["det"]) < 12:
                actual["det"].append(linea[len(_DET) :].strip())
        elif linea.startswith(_TB):
            if len(actual["tb"]) < 60:
                actual["tb"].append(linea[len(_TB) :])
        elif _CABECERA.match(linea) or not linea.startswith(" "):
            actual = None  # otra línea del registro (OK, INFO, cartel…): termina el evento
    with _lock:
        _CACHE[ruta] = (firma, eventos)
    return eventos


def ultimos_eventos(limite=60):
    """Errores y avisos de ayer y hoy, del más nuevo al más viejo, + cuántos hubo hoy."""
    ahora = time.time()
    hoy = L.archivo_del_dia(ahora)
    ayer = L.archivo_del_dia(ahora - 86400)
    ev_hoy = _eventos_de(hoy)
    todos = (_eventos_de(ayer) if ayer != hoy else []) + ev_hoy
    return {
        "errores_hoy": sum(1 for e in ev_hoy if e["nivel"] == "error"),
        "avisos_hoy": sum(1 for e in ev_hoy if e["nivel"] == "aviso"),
        "eventos": list(reversed(todos[-limite:])),
        "archivo": str(hoy),
    }


# ------------------------------------------------------------- permisos
LOCALES = {"127.0.0.1", "::1", "::ffff:127.0.0.1"}


def es_local(handler, puerto):
    """Pedido hecho en esta PC: directo (sin encabezados de Cloudflare), desde 127.0.0.1 y con la dirección
    de esta PC en el navegador (evita que una página de internet lo use)."""
    if handler.remoto or handler.client_address[0] not in LOCALES:
        return False
    host = (handler.headers.get("Host") or "").lower()
    return host in (f"127.0.0.1:{puerto}", f"localhost:{puerto}")


def es_admin_remoto(handler):
    """Desde una PC del trabajo: tiene que haber llegado por el túnel con su sesión (handler.pc) y además
    haber escrito la contraseña del panel (cookie «ta» de esa misma PC)."""
    return bool(handler.remoto and getattr(handler, "pc", None) and R.admin_de(handler._cookie("ta"), handler.pc))


def acceso(handler, puerto):
    """'local' (PC del servidor), 'remoto' (PC del trabajo con la contraseña del panel) o None."""
    if es_local(handler, puerto):
        return "local"
    if es_admin_remoto(handler):
        return "remoto"
    return None


def puede_ver(handler, puerto):
    return acceso(handler, puerto) is not None


def _host(url):
    """«https://Algo.devtunnels.ms:443/x» → «algo.devtunnels.ms» (sin esquema, puerto ni ruta)."""
    h = (url or "").strip().lower()
    if "://" in h:
        h = h.split("://", 1)[1]
    h = h.split("/", 1)[0].split(",")[0].strip()
    if h.startswith("["):
        return h.split("]")[0] + "]"
    return h.rsplit(":", 1)[0] if h.count(":") == 1 else h


def origenes_validos(handler, puerto):
    """Hosts aceptados en el encabezado Origin de un botón del panel."""
    if not handler.remoto:
        return {"127.0.0.1", "localhost"}
    hosts = {_host(handler.headers.get("Host")), _host(handler.headers.get("X-Forwarded-Host"))}
    try:
        from transcripcion.acceso import remoto as R

        hosts.add(_host(R.URL_TUNEL.get("url")))
    except Exception:
        pass
    # Microsoft Dev Tunnels reescribe Host y Origin a «localhost:<puerto del túnel>» antes de pasarlos al servidor
    # (por eso desde que se usa Dev Tunnels el panel decía «Pedido rechazado» al entrar). Ese puerto solo recibe lo
    # que llega por el túnel; lo que protege de otras páginas es X-Panel (exige permiso CORS, que el servidor no da),
    # Sec-Fetch-Site y la cookie SameSite=Strict.
    if getattr(handler, "es_puerto_tunel", False):
        hosts |= {"127.0.0.1", "localhost"}
    hosts.discard("")
    return hosts


def motivo_origen(handler, puerto):
    """None si el pedido viene de la página del panel; si no, el motivo (para el registro)."""
    if handler.headers.get("X-Panel") != "1":
        return "falta el encabezado X-Panel"
    origen = handler.headers.get("Origin") or ""
    if origen and _host(origen) not in origenes_validos(handler, puerto):
        return (
            f"Origin «{origen[:80]}» no coincide (Host «{(handler.headers.get('Host') or '')[:60]}», "
            f"X-Forwarded-Host «{(handler.headers.get('X-Forwarded-Host') or '')[:60]}»)"
        )
    sitio = handler.headers.get("Sec-Fetch-Site")
    if sitio and sitio not in ("same-origin", "none"):
        return f"Sec-Fetch-Site «{sitio}»"
    return None


def mismo_origen(handler, puerto):
    """Para los botones (POST): encabezado propio (una página de otro sitio no lo puede mandar sin permiso) y,
    si el navegador dice de dónde viene el pedido, que sea de esta misma página."""
    return motivo_origen(handler, puerto) is None


def puede_cambiar(handler, puerto):
    return puede_ver(handler, puerto) and mismo_origen(handler, puerto)


def abrir_en_windows(ruta):
    """Abre una carpeta o archivo con el programa del escritorio (Explorador y Bloc de notas en Windows,
    xdg-open en Linux). False si en esta PC no se puede (Linux sin pantalla)."""
    return P.abrir(ruta)
