# -*- coding: utf-8 -*-
"""
PANEL DE ADMINISTRACIÓN (http://127.0.0.1:8765/admin, solo en la PC del servidor).

Acá está lo que no depende del servidor HTTP:
- leer los últimos errores y avisos de los archivos de registros\\ (hoy y ayer);
- decidir si un pedido puede usar el panel (solo esta PC, nunca por el túnel).
El estado completo lo arma servidor.py (que tiene la cola, la IA, etc.).
"""
import os
import re
import threading
import time

import registro as L
import remoto as R

# 2026-10-25 01:44:02  AVISO  TÚNEL     mensaje
_LINEA = re.compile(r"^(\d{4}-\d\d-\d\d) (\d\d:\d\d:\d\d)  (AVISO|ERROR)\s+(\S+)\s+(.*)$")
_CABECERA = re.compile(r"^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d  ")
_DET = " " * 31 + "· "
_TB = "    | "
_MAX_LEER = 3 * 1024 * 1024        # del final de cada archivo alcanza
_CACHE = {}                        # ruta -> (firma, eventos)
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
                f.readline()           # la primera puede venir cortada
            texto = f.read().decode("utf-8", "replace")
    except OSError:
        return []
    eventos, actual = [], None
    for linea in texto.splitlines():
        m = _LINEA.match(linea)
        if m:
            actual = {"fecha": m.group(1), "hora": m.group(2), "nivel": m.group(3).lower(), "area": m.group(4),
                      "msg": m.group(5).strip(), "det": [], "tb": []}
            eventos.append(actual)
            continue
        if actual is None:
            continue
        if linea.startswith(_DET):
            if len(actual["det"]) < 12:
                actual["det"].append(linea[len(_DET):].strip())
        elif linea.startswith(_TB):
            if len(actual["tb"]) < 60:
                actual["tb"].append(linea[len(_TB):])
        elif _CABECERA.match(linea) or not linea.startswith(" "):
            actual = None              # otra línea del registro (OK, INFO, cartel…): termina el evento
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
    return {"errores_hoy": sum(1 for e in ev_hoy if e["nivel"] == "error"),
            "avisos_hoy": sum(1 for e in ev_hoy if e["nivel"] == "aviso"),
            "eventos": list(reversed(todos[-limite:])),
            "archivo": str(hoy)}


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


def mismo_origen(handler, puerto):
    """Para los botones (POST): encabezado propio (una página de otro sitio no lo puede mandar sin permiso) y,
    si el navegador dice de dónde viene el pedido, que sea de esta misma página."""
    if handler.headers.get("X-Panel") != "1":
        return False
    origen = (handler.headers.get("Origin") or "").lower()
    if handler.remoto:
        validos = ("https://" + (handler.headers.get("Host") or "").lower(),)
    else:
        validos = (f"http://127.0.0.1:{puerto}", f"http://localhost:{puerto}")
    if origen and origen not in validos:
        return False
    sitio = handler.headers.get("Sec-Fetch-Site")
    return not sitio or sitio in ("same-origin", "none")


def puede_cambiar(handler, puerto):
    return puede_ver(handler, puerto) and mismo_origen(handler, puerto)


def abrir_en_windows(ruta):
    """Abre una carpeta o archivo con el programa de Windows (Explorador, Bloc de notas)."""
    if os.name != "nt":
        return False
    os.startfile(str(ruta))
    return True
