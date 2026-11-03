"""Manejador HTTP: lee el pedido, autoriza (sesión, llave de la PC, panel) y lo pasa a la ruta de la tabla.

Las respuestas comunes (_json, _html, _redirigir, _enviar_archivo) y la autorización están acá; lo que hace cada
ruta, en los módulos de su área (casos, edicion, audios, cliente, conocimiento, voces, usuario, panel, acceso,
paginas); la tabla completa, en tabla.py.
Cada sistema configurado tiene su clase de manejador con su `sis` (Manejador.para(sis)): nada se busca en globales.
"""

import json
import mimetypes
import re
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler

from transcripcion.acceso import remoto as R
from transcripcion.acceso import usuarios as U
from transcripcion.base import registro as L
from transcripcion.base.formatos import mensaje_amigable
from transcripcion.casos.repositorio import LOCAL
from transcripcion.http.edicion import caso_ocupado
from transcripcion.http.panel import PAGINAS_ADMIN
from transcripcion.http.rutas import Pedido
from transcripcion.http.tabla import RUTAS
from transcripcion.operacion import app_cliente as A
from transcripcion.procesamiento import cola as CP


class Manejador(BaseHTTPRequestHandler):
    sis = None  # Sistema (transcripcion.http.sistema); lo pone Manejador.para()
    rutas = RUTAS

    @classmethod
    def para(cls, sis):
        """Clase de manejador para este sistema (la que se le pasa al servidor HTTP)."""
        return type(cls.__name__, (cls,), {"sis": sis})

    def log_message(self, *a):
        pass

    def log_error(self, fmt, *args):
        L.debug("SERVIDOR", "HTTP: " + (fmt % args))

    def _json(self, obj, code=200, cookie=None):
        b = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.send_header("Cache-Control", "no-store")
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()
        self.wfile.write(b)

    def end_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        super().end_headers()

    def _body(self, limite=100 * 1024 * 1024):
        if "chunked" in (self.headers.get("Transfer-Encoding") or "").lower():
            partes, total = [], 0
            while True:
                tam = int(self.rfile.readline().split(b";")[0].strip() or b"0", 16)
                if tam == 0:
                    self.rfile.readline()
                    break
                total += tam
                if total > limite:
                    raise ValueError("Archivo demasiado grande")
                partes.append(self.rfile.read(tam))
                self.rfile.readline()
            return b"".join(partes)
        n = int(self.headers.get("Content-Length") or 0)
        if n > limite:
            raise ValueError("Archivo demasiado grande")
        return self.rfile.read(n) if n else b""

    def _nombre_valido(self, n):
        return n and "/" not in n and "\\" not in n and ".." not in n

    # ---------------------------------------------------- acceso remoto
    def _es_remoto(self):
        """Lo que llega por el tunel trae encabezados de Cloudflare; lo local no."""
        return any(self.headers.get(h) for h in ("Cf-Ray", "Cf-Connecting-Ip", "X-Forwarded-For", "Cf-Warp-Tag-Id"))

    def _ip(self):
        return self.headers.get("Cf-Connecting-Ip") or self.client_address[0]

    def _cookie(self, nombre):
        for parte in (self.headers.get("Cookie") or "").split(";"):
            k, _, v = parte.strip().partition("=")
            if k == nombre:
                return v
        return None

    def _llave(self):
        a = self.headers.get("Authorization") or ""
        return a[7:].strip() if a.lower().startswith("bearer ") else None

    # /ingresar: usuario y contraseña cuando la PC ya está identificada. Es otra dirección que /entrar porque la app
    # del trabajo intercepta /entrar (sin código) para volver a entrar sola con la llave de la PC.
    LIBRES = {"/entrar", "/ingresar", "/api/cliente/vincular", "/favicon.ico", "/salir"}
    # lo que la aplicación del trabajo hace sola con la llave de la PC, aunque nadie haya entrado
    SOLO_LLAVE = {
        "/api/cliente/estado",
        "/api/cliente/actualizacion",
        "/api/cliente/archivo",
        "/api/cliente/aviso",
        "/api/cliente/audio",
        "/api/cliente/sesion",
    }

    def _sin_usuario(self, ruta):
        """Rutas que no necesitan un transcriptor con sesión."""
        if ruta in self.LIBRES or (self.con_llave and ruta in self.SOLO_LLAVE):
            return True
        # el panel de administración tiene su propio permiso (acceso/admin.py): así se crean los primeros usuarios
        return ruta in PAGINAS_ADMIN or ruta.startswith("/api/admin/")

    def _autorizar(self, ruta):
        """Pone self.pc, self.remoto y self.usuario (transcriptor con sesión, o None).
        Devuelve False (y responde) si no tiene permiso."""
        self.remoto = self._es_remoto()
        self.usuario = None
        self.con_llave = False
        ses = R.sesion(self._cookie("ts"))
        if not self.remoto:
            self.pc = LOCAL
            # la app de pruebas conectada a http://127.0.0.1 también manda su llave: con ella puede hacer lo suyo
            # (estado, audios, actualización) aunque nadie haya entrado en la página
            self.con_llave = bool(R.pc_de_llave(self._llave()))
            if ses and ses.get("local"):
                self.usuario = ses.get("usuario")
        else:
            llave = R.pc_de_llave(self._llave())
            self.con_llave = bool(llave)
            ses_pc = ses["pc"] if ses and not ses.get("local") else None
            self.pc = llave or ses_pc
            if ses_pc and ses_pc == self.pc:
                self.usuario = ses.get("usuario")
            if self.pc:
                self.sis.visto[self.pc] = time.time()
                R.anotar_visto(self.pc, A.VERSION_PC.get(self.pc))
        if self.usuario and not U.existe(self.usuario):  # lo desactivaron mientras tenía la sesión abierta
            R.cerrar_sesion(self._cookie("ts"))
            self.usuario = None
        if self.remoto and not self.pc and ruta not in self.LIBRES:
            return self._pedir_entrar(ruta, "Pedido sin sesión")
        if self.usuario or not U.hay_usuarios() or self._sin_usuario(ruta):
            return True
        return self._pedir_entrar(ruta, "Pedido sin transcriptor")

    def _pedir_entrar(self, ruta, motivo):
        if ruta not in ("/", "/index.html") and L.una_vez(("sin_sesion", self._ip()), 600):
            L.info("ACCESO", f"{motivo} desde {self.pc or 'la IP ' + self._ip()} ({ruta}): se le pide entrar.")
        if ruta.startswith("/api/") or ruta.startswith("/audio/"):
            self._json({"error": "Sesión vencida: volvé a entrar.", "entrar": True}, 401)
        else:
            self._redirigir("/ingresar" if self.pc and U.hay_usuarios() else "/entrar")
        return False

    @property
    def quien(self):
        """Para el registro: «Ana (info-01)», o solo la PC si no hay transcriptor."""
        return f"{U.nombre_de(self.usuario)} ({self.pc})" if getattr(self, "usuario", None) else self.pc

    def _redirigir(self, a, cookie=None):
        self.send_response(303)
        self.send_header("Location", a)
        self.send_header("Cache-Control", "no-store")
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _html(self, b, code=200):
        b = b.encode("utf-8") if isinstance(b, str) else b
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(b)

    def _enviar_archivo(self, ruta, descarga=None):
        tam = ruta.stat().st_size
        tipo = mimetypes.guess_type(str(ruta))[0] or "application/octet-stream"
        if ruta.suffix.lower() == ".docx":
            tipo = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        rng = self.headers.get("Range")
        ini, fin = 0, tam - 1
        if rng:
            m = re.match(r"bytes=(\d*)-(\d*)", rng)
            if m:
                if m.group(1):
                    ini = int(m.group(1))
                    if m.group(2):
                        fin = min(int(m.group(2)), tam - 1)
                elif m.group(2):
                    ini = max(0, tam - int(m.group(2)))
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {ini}-{fin}/{tam}")
        else:
            self.send_response(200)
        self.send_header("Content-Type", tipo)
        self.send_header("Cache-Control", "no-store")  # que Cloudflare no guarde audios ni Word
        if descarga:
            self.send_header("Content-Disposition", "attachment; filename*=UTF-8''" + urllib.parse.quote(descarga))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(fin - ini + 1))
        self.end_headers()
        try:
            with open(ruta, "rb") as f:
                f.seek(ini)
                falta = fin - ini + 1
                while falta > 0:
                    b = f.read(min(65536, falta))
                    if not b:
                        break
                    self.wfile.write(b)
                    falta -= len(b)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass

    # ------------------------------------------------------------ despacho
    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(u.query)
        if not self._autorizar(u.path):
            return
        r = self.rutas.buscar("GET", u.path)
        if r is None:
            return self.send_error(404)
        r.funcion(self, Pedido(u.path, q))

    def do_POST(self):
        u = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(u.query)
        if not self._autorizar(u.path):
            return
        try:
            r = self.rutas.buscar("POST", u.path)
            p = Pedido(u.path, q)
            if r and r.fase == "cruda":
                return r.funcion(self, p)
            p.datos = json.loads(self._body(20 * 1024 * 1024) or b"{}")
            if r and r.fase == "json":
                return r.funcion(self, p)
            n = p.datos.get("nombre", "")
            if not self._nombre_valido(n):
                return self._json({"error": "nombre inválido"}, 400)
            p.nombre = n
            if r is None:
                return self.send_error(404)
            if r.libre and caso_ocupado(self, n):
                return
            return r.funcion(self, p)
        except CP.ErrorCola:
            L.error("COLA", "No se confirmó la operación en la cola persistente.", exc=True)
            self._json({"error": "No se pudo confirmar la cola del servidor. Conservá el audio y reintentá."}, 503)
        except PermissionError:
            L.aviso(
                "INFORME",
                f"No se pudo guardar ({u.path}, {self.pc}): el Word está abierto. "
                f"Hay que cerrarlo y volver a intentar.",
            )
            self._json({"error": "El Word está abierto: cerralo y volvé a intentar."}, 409)
        except Exception as ex:
            L.error(
                "SERVIDOR", f"Falló {u.path} pedido por {getattr(self, 'pc', '?')}: {mensaje_amigable(ex)}", exc=True
            )
            self._json({"error": str(ex)}, 500)


class ManejadorTunel(Manejador):
    """Pedidos que entran por el puerto propio del túnel de Microsoft: siempre de las PC del trabajo."""

    es_puerto_tunel = True

    def _es_remoto(self):
        return True

    def _ip(self):
        xff = (self.headers.get("X-Forwarded-For") or "").split(",")[0].strip()
        return xff or self.headers.get("Cf-Connecting-Ip") or self.client_address[0]
