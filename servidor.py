# -*- coding: utf-8 -*-
"""
INTERFAZ WEB. Se abre con interfaz.bat o .sh (solo esta PC) o con iniciar_servidor.bat o .sh
(esta PC + las PC del trabajo por un tunel: el rapido de Cloudflare o Microsoft Dev Tunnels).
Todo se procesa en esta PC: las otras solo envian audios y muestran la pagina.
"""
import hashlib
import json
import mimetypes
import os
import re
import sys
import threading
import time
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import admin as ADM
import correcciones as CORR
import estadisticas as EST
import aprender as APRENDER
import app_cliente as A
from transcripcion.casos import borradores as BOR
from transcripcion.procesamiento import cola as CP
from transcripcion.base.persistencia import escribir_atomico
from transcripcion.aprendizaje.pendiente import ColaAprendizaje
import mantenimiento as M
from transcripcion.conocimiento import archivos as CON
from transcripcion.conocimiento import medicos as MED
from transcripcion.conocimiento import plantillas as PL
from transcripcion.informe import formato as FMT
from transcripcion.casos import paciente as PAC
from transcripcion.base import plataforma as P
from transcripcion.base import registro as L
import remoto as R
from transcripcion.acceso import usuarios as U
from transcripcion.voz import huellas as VOZ
from transcripcion import ajustes
from transcripcion.base.formatos import duracion_wav, mensaje_amigable
from transcripcion.casos.repositorio import Casos, EXT_AUDIO, LOCAL
from transcripcion.procesamiento.estado import Procesamiento, EN_PROCESO
from transcripcion.procesamiento.trabajador import Trabajador
from transcripcion.operacion.reinicio import Operacion
from transcripcion.casos.borrado import Borrado
from transcripcion.casos.vista import VistaCasos
from transcripcion.voz.servicio import ServicioVoz
from transcripcion.operacion.ia import EstadoIA
from transcripcion.informe.guardado import Guardado

AQUI = Path(__file__).resolve().parent
WEB = AQUI / "web"
RECIBIR_AUDIO_LOCK = threading.RLock()

# Ajustes del arranque. Importar este módulo no lee la configuración ni crea carpetas: los completa
# configurar(), que llama main() (o una prueba con ajustes.para_pruebas). Ver docs/refactor.md, etapa 1.
AJUSTES = None
CFG = None            # configuracion.json ya leída
NUEVOS = None         # carpeta de audios nuevos
INFORMES = None       # carpeta de los Word
DATOS = None          # Informes/revision/datos: archivos de cada caso
PUERTO = None         # interfaz web local
# Puerto propio del túnel de Microsoft (Dev Tunnels): todo lo que entra por acá es de las PC del trabajo,
# tenga los encabezados que tenga. Solo escucha en 127.0.0.1 y solo con ese túnel elegido.
PUERTO_TUNEL = None
SIMULAR = False       # SIMULAR_IA=1: sin Whisper ni Ollama (solo para pruebas)
COLA_AL_REINICIAR = None
APRENDIZAJE = None    # cola persistente de aprendizaje (se crea en configurar)
CASOS = None          # archivos de los casos (transcripcion.casos.repositorio.Casos, se crea en configurar)
PROC = None           # estado del procesamiento: etapas, cola, pausas (transcripcion.procesamiento.estado)
IA = None     # estado de Ollama (transcripcion.operacion.ia)
VOCES = None  # reconocimiento por la voz (transcripcion.voz.servicio)
VISTA = None  # lista y caso abierto para las pantallas (transcripcion.casos.vista)
BORRADO = None # borrado de casos (transcripcion.casos.borrado)
OPER = None   # reinicio programado y mensajes a las PC (transcripcion.operacion.reinicio)
TRAB = None   # trabajador de la cola (transcripcion.procesamiento.trabajador)
GUARDADO = None  # Guardar Word y aprender, vista previa (transcripcion.informe.guardado)
VERSION = "2026.11.7"
# páginas del panel de administración (solo en esta PC); cada una se abre en su pestaña del navegador
PAGINAS_ADMIN = {"/admin": "admin.html", "/admin/estadisticas": "estadisticas.html",
                 "/admin/correcciones": "correcciones.html", "/admin/medicos": "medicos.html"}
FIN_LOCK = threading.Lock()
INICIO = time.time()
TUNEL = {"modo": False, "http": None, "error": None}     # "modo": se abrió con iniciar_servidor.bat (--tunel)


VISTO = {}              # PC del trabajo -> hora de su último pedido


def origen_local(h):
    """Para los botones solo locales (pausa): que el pedido no venga de una página de otro sitio."""
    o = (h.headers.get("Origin") or "").lower()
    if o and o not in (f"http://127.0.0.1:{PUERTO}", f"http://localhost:{PUERTO}"):
        return False
    return h.headers.get("Sec-Fetch-Site") in (None, "same-origin", "none")


# ------------------------------------------------- cola en vivo y casos abiertos (panel de administración)
def cola_en_vivo():
    """Lo que se está procesando y lo que espera, en orden, con cuánto lleva y cuánto falta (aproximado)."""
    ahora = time.time()
    esp = PROC.esperas()
    with PROC.lock:
        enp = {n: dict(v) for n, v in PROC.estado.items() if v.get("estado") in EN_PROCESO}
        errores = sum(1 for v in PROC.estado.values() if v.get("estado") == "error")
    items = []
    for n in sorted(enp, key=lambda x: (esp.get(x) or {}).get("adelante", 0)):
        e, s_ = enp[n], esp.get(n) or {}
        msg = e.get("msg") or ""
        items.append({"nombre": n, "titulo": CASOS.titulo_de(n), "paciente": PAC.de(DATOS, n), "pc": CASOS.origen_de(n),
                      "medico": CASOS.medico_de(n), "estado": e.get("estado"), "msg": msg,
                      "etapa_desde": s_.get("desde"), "adelante": s_.get("adelante"), "eta": s_.get("eta"),
                      "en_cola": round(ahora - PROC.encolado[n]) if n in PROC.encolado else None, "dur": CASOS.duracion_de(n),
                      "espera_ia": e.get("estado") == "en cola" and msg.startswith("Esperando a la IA ("),
                      "puede_pausar": e.get("estado") == "transcribiendo" and n not in PROC.pausas,
                      "pausa_pedida": n in PROC.pausas and e.get("estado") != "en pausa"})
    return {"items": items, "eta_total": max((i["eta"] or 0 for i in items), default=0), "errores": errores,
            "pausada": bool(OPER.reinicio.get("detener")), "en_pausa": bool(PROC.trabajo.get("en_pausa")),
            "tiempos": {"whisper_x": round(PROC.tiempos["whisper_x"], 3), "ia": round(PROC.tiempos["ia"], 1), "n": PROC.tiempos["n"]}}


def casos_abiertos():
    """Casos que alguna PC tiene abiertos ahora (bloqueados para las demás)."""
    ahora, out = time.time(), []
    for n, b in sorted(list(R.BLOQUEOS.items()), key=lambda x: x[1].get("desde", x[1]["t"])):
        edad = ahora - b["t"]
        if edad >= R.BLOQUEO_SEG:
            continue
        out.append({"nombre": n, "titulo": CASOS.titulo_de(n), "paciente": PAC.de(DATOS, n), "pc": b["pc"],
                    "desde": b.get("desde", b["t"]), "senal": round(edad), "libera_en": round(R.BLOQUEO_SEG - edad),
                    "rev": CASOS.revision_de(n)})
    return out


# ------------------------------------------------- mensajes a las PC y reinicio desde el panel
SRV = {"http": None, "salida": 0}


def abrir_tunel():
    """Abre el túnel elegido (configurar_tunel). Con Microsoft Dev Tunnels, antes abre el puerto propio
    del túnel; si no se puede, no abre el túnel (devtunnel publicaría lo que haya en ese puerto)."""
    if R.URL_TUNEL.get("iniciado"):
        return
    if R.servicio_tunel() == "devtunnel" and not TUNEL["http"]:
        try:
            TUNEL["http"] = Servidor(("127.0.0.1", PUERTO_TUNEL), HTunel)
        except OSError as ex:
            TUNEL["error"] = f"El puerto {PUERTO_TUNEL} está ocupado por otro programa ({ex})."
            L.error("TÚNEL", f"No se pudo abrir el puerto {PUERTO_TUNEL} para el túnel de Microsoft: lo usa otro "
                             f"programa. Cerralo o cambiá PUERTO_TUNEL. Mientras tanto el sistema funciona solo en esta PC.")
            return
        threading.Thread(target=TUNEL["http"].serve_forever, daemon=True, name="puerto-tunel").start()
        L.debug("TÚNEL", f"Puerto propio del túnel abierto: 127.0.0.1:{PUERTO_TUNEL}")
    R.escribir_conexion_cliente()
    R.iniciar_tunel(PUERTO, PUERTO_TUNEL)


# ---------------------------------------------------------------- borrar
# Archivos de un caso en la carpeta datos. Lista explícita: un caso «tmp9177» no debe llevarse
# los de otro llamado «tmp9177.tmp».


FMT_LOCK = threading.Lock()


def configurar(aj):
    """Toma los ajustes (de ajustes.cargar() en main, o de ajustes.para_pruebas en una prueba).
    No crea carpetas ni arranca hilos: eso lo hace main(). Devuelve los ajustes anteriores, para que una
    prueba los restaure con configurar(anteriores); configurar(None) deja todo sin configurar."""
    global AJUSTES, CFG, NUEVOS, INFORMES, DATOS, PUERTO, PUERTO_TUNEL, SIMULAR, COLA_AL_REINICIAR, APRENDIZAJE, CASOS, PROC, IA, VOCES, VISTA, BORRADO, OPER, TRAB, GUARDADO
    anteriores = AJUSTES
    AJUSTES = aj
    if aj is None:
        CFG = NUEVOS = INFORMES = DATOS = PUERTO = PUERTO_TUNEL = COLA_AL_REINICIAR = APRENDIZAJE = CASOS = PROC = IA = VOCES = VISTA = BORRADO = OPER = TRAB = GUARDADO = None
        SIMULAR = False
        return anteriores
    CFG = aj.cfg
    NUEVOS, INFORMES, DATOS = aj.audios_nuevos, aj.informes, aj.datos
    PUERTO, PUERTO_TUNEL, SIMULAR = aj.puerto, aj.puerto_tunel, aj.simular_ia
    COLA_AL_REINICIAR = INFORMES / "revision" / "cola_al_reiniciar.json"
    CASOS = Casos(DATOS, NUEVOS)
    PROC = Procesamiento(CASOS)
    IA = EstadoIA(CFG, SIMULAR, AQUI, CASOS, PROC)
    VOCES = ServicioVoz(CFG, CASOS, PROC)
    VISTA = VistaCasos(CASOS, PROC, VOCES, INICIO, R)
    BORRADO = Borrado(CASOS, PROC, INFORMES, R)
    OPER = Operacion(CASOS, PROC, COLA_AL_REINICIAR, TUNEL, SRV, FIN_LOCK, M)
    TRAB = Trabajador(CFG, SIMULAR, AQUI, INFORMES, COLA_AL_REINICIAR, CASOS, PROC, IA, VOCES, VISTA, OPER)
    GUARDADO = Guardado(CFG, INFORMES, CASOS, VOCES, FIN_LOCK, APRENDER, EST)
    APRENDIZAJE = ColaAprendizaje(DATOS / "_aprendizaje", GUARDADO.aplicar_aprendizaje, GUARDADO.analizar_aprendizaje)
    GUARDADO.aprendizaje = APRENDIZAJE   # la cola llama a métodos de GUARDADO; GUARDADO le encola tareas
    return anteriores


# ------------------------------------------------------------------ HTTP
class H(BaseHTTPRequestHandler):
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
    SOLO_LLAVE = {"/api/cliente/estado", "/api/cliente/actualizacion", "/api/cliente/archivo", "/api/cliente/aviso",
                  "/api/cliente/audio", "/api/cliente/sesion"}

    def _sin_usuario(self, ruta):
        """Rutas que no necesitan un transcriptor con sesión."""
        if ruta in self.LIBRES or (self.con_llave and ruta in self.SOLO_LLAVE):
            return True
        # el panel de administración tiene su propio permiso (admin.py): así se crean los primeros usuarios
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
                VISTO[self.pc] = time.time()
                R.anotar_visto(self.pc, A.VERSION_PC.get(self.pc))
        if self.usuario and not U.existe(self.usuario):        # lo desactivaron mientras tenía la sesión abierta
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

    def _pagina_entrar(self, error="", usuario=""):
        """Formulario para entrar. Con transcriptores creados pide usuario y contraseña (y el nombre de la PC si
        se entra desde un navegador común del trabajo); sin ninguno, como antes: PC y contraseña del sistema."""
        import html as _h
        err = f'<p class="err">{_h.escape(error)}</p>' if error else ""
        hay = U.hay_usuarios()
        pc_conocida = not self.remoto or bool(self.pc)
        if not hay:
            txt = "Para usar el sistema desde esta PC escribí su nombre y la contraseña."
        elif pc_conocida:
            txt = (f"Esta PC: <b>{_h.escape(self.pc)}</b>. " if self.remoto else "") + \
                  "Escribí tu usuario y tu contraseña: la IA arma los informes con tu estilo."
        else:
            txt = "Escribí el nombre de esta PC, tu usuario y tu contraseña."
        campos = ""
        if self.remoto and not pc_conocida:
            campos += ('<label>Nombre de esta PC<input name="pc" placeholder="info-01" required '
                       'autocomplete="organization"></label>')
        if hay:
            campos += (f'<label>Usuario<input name="usuario" value="{_h.escape(usuario)}" required autofocus '
                       f'autocomplete="username"></label>')
        campos += ('<label>Contraseña<input name="contrasena" type="password" required '
                   'autocomplete="current-password"></label>')
        accion = "/ingresar" if hay and pc_conocida else "/entrar"
        self._html(PAGINA_ENTRAR.replace("{{texto}}", txt).replace("{{error}}", err).replace("{{campos}}", campos)
                   .replace("{{accion}}", accion), 401 if error else 200)

    def _entrar(self, f):
        """POST /entrar: transcriptor (o, sin transcriptores, la contraseña del sistema desde el trabajo)."""
        ip = self._ip()
        pc = (self.pc or (f.get("pc", [""])[0]).strip()) if self.remoto else LOCAL
        nombre = (f.get("usuario", [""])[0]).strip()
        clave_fallo = ip if self.remoto else f"local:{nombre.casefold()}"
        if R.demasiados_fallos(clave_fallo):
            L.aviso("ACCESO", f"Intento de entrar como «{(nombre or pc)[:24]}» desde la IP {ip} rechazado: "
                              f"está bloqueada 10 minutos por contraseñas incorrectas.")
            return self._pagina_entrar("Demasiados intentos fallidos. Esperá 10 minutos.", nombre)
        if self.remoto and not R.PC_VALIDA.match(pc):
            return self._pagina_entrar("Escribí el nombre de esta PC (ej. info-01).", nombre)
        contrasena = f.get("contrasena", [""])[0]
        if not U.hay_usuarios():
            if not self.remoto:
                return self._redirigir("/")
            if not R.contrasena_ok(contrasena):
                R.anotar_fallo(ip)
                self._avisar_fallo(pc, ip, "desde el navegador")
                return self._pagina_entrar("Contraseña incorrecta.")
            L.ok("ACCESO", f"{pc} entró desde el navegador (IP {ip}).")
            return self._redirigir("/", R.cookie_sesion(R.nueva_sesion(pc, reemplaza=self._cookie("ts"))))
        usuario = U.verificar(nombre, contrasena)
        if not usuario:
            R.anotar_fallo(clave_fallo)
            k = len(R.FALLOS.get(clave_fallo, []))
            L.aviso("ACCESO", f"Usuario o contraseña incorrectos para «{nombre[:24]}» en {pc} (IP {ip})."
                              + (" Queda bloqueado 10 minutos." if k >= 5 else f" Intento {k} de 5."))
            return self._pagina_entrar("Usuario o contraseña incorrectos.", nombre)
        R.FALLOS.pop(clave_fallo, None)
        U.anotar_entrada(usuario)
        sid = R.nueva_sesion(pc, usuario=usuario, local=not self.remoto, reemplaza=self._cookie("ts"))
        L.ok("ACCESO", f"{U.nombre_de(usuario)} entró en {pc}" + (f" (IP {ip})." if self.remoto else "."))
        return self._redirigir("/", R.cookie_sesion(sid, local=not self.remoto))

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(u.query)
        if not self._autorizar(u.path):
            return
        if u.path == "/entrar":
            cod = q.get("codigo", [""])[0]
            v = R.tomar_codigo(cod) if cod else None
            if v and self.usuario and v.get("usuario") in (None, self.usuario):
                # la app volvió a entrar (p. ej. después de que el servidor se cayó o se reinició) y esta pantalla ya
                # tiene la sesión de un transcriptor: se conserva, no se la cambia por una sesión sin usuario
                L.info("ACCESO", f"{self.quien} volvió a conectarse con su sesión (IP {self._ip()}).")
                return self._redirigir("/")
            sid = R.canjear_codigo(cod, pc_local=None if self.remoto else LOCAL, v=v) if v else None
            if sid:
                v = R.sesion(sid) or {}
                if v.get("usuario"):
                    U.anotar_entrada(v["usuario"])
                L.info("ACCESO", f"{v.get('pc')} abrió la aplicación"
                                 + (f" con {U.nombre_de(v['usuario'])}" if v.get("usuario") else "") + f" (IP {self._ip()}).")
                return self._redirigir("/", R.cookie_sesion(sid, local=not self.remoto))
            if cod:
                L.aviso("ACCESO", f"Código de entrada vencido o inválido desde la IP {self._ip()}.")
            if self.usuario or (not self.remoto and not U.hay_usuarios()):
                return self._redirigir("/")
            return self._pagina_entrar()
        if u.path == "/ingresar":
            if self.usuario or not U.hay_usuarios():
                return self._redirigir("/")
            if self.remoto and not self.pc:
                return self._redirigir("/entrar")
            return self._pagina_entrar()
        if u.path == "/salir":
            v = R.cerrar_sesion(self._cookie("ts"))
            if v:
                L.info("ACCESO", (f"{U.nombre_de(v['usuario'])} salió en {v['pc']}." if v.get("usuario")
                                  else f"{v['pc']} cerró la sesión."))
            if v and v.get("usuario") and not v.get("local"):
                # en el trabajo la PC sigue identificada: el que sigue solo escribe su usuario y contraseña
                return self._redirigir("/ingresar", R.cookie_sesion(R.nueva_sesion(v["pc"])))
            return self._redirigir("/ingresar" if not self.remoto and U.hay_usuarios() else "/entrar",
                                   R.COOKIE_SESION_BORRAR)
        if u.path in ("/", "/index.html"):
            self._html((WEB / "index.html").read_bytes())
        elif u.path == "/editor_word.js":
            self._enviar_archivo(WEB / "editor_word.js")
        elif u.path in PAGINAS_ADMIN or u.path.startswith("/api/admin/"):
            acc = ADM.acceso(self, PUERTO)
            if acc is None:
                return self._panel_sin_permiso(u.path)
            visor = {"remoto": acc == "remoto", "pc": self.pc if acc == "remoto" else None}
            if u.path in PAGINAS_ADMIN:
                self._html((WEB / PAGINAS_ADMIN[u.path]).read_bytes())
            elif u.path == "/api/admin/estado":
                self._json(dict(estado_admin(), visor=visor))
            elif u.path == "/api/admin/medicos":
                self._json({"medicos": [{"nombre": m, "notas": MED.notas_medico(m)}
                                          for m in MED.lista_medicos()], "visor": visor})
            elif u.path == "/api/admin/estadisticas":
                q = urllib.parse.parse_qs(u.query)
                try:
                    dias = int((q.get("dias") or ["30"])[0])
                except ValueError:
                    dias = 30
                self._json(dict(EST.calcular(dias, medico_actual=CASOS.medico_de, estudios_actual=CASOS.estudios_de), visor=visor))
            elif u.path == "/api/admin/correcciones":
                try:
                    dias = int((q.get("dias") or ["0"])[0])
                except ValueError:
                    dias = 0
                self._json(dict(CORR.calcular(dias, (q.get("medico") or [""])[0], medico_actual=CASOS.medico_de,
                                              puntuacion=(q.get("puntuacion") or [""])[0] == "1"), visor=visor))
            else:
                self.send_error(404)
        elif u.path == "/api/mi_pc":
            du = U.datos(self.usuario) if self.usuario else None
            self._json({"pc": self.pc, "remoto": self.remoto, "medico": R.medico_pc(self.pc),
                        "admin": (not self.remoto) or R.admin_configurado(),   # si se muestra el engranaje del panel
                        "con_usuarios": U.hay_usuarios(),
                        "usuario": {"clave": du["clave"], "nombre": du["nombre"], "cambiar": du["cambiar"]} if du else None,
                        # None = nunca guardó preferencias: la página sube las de esta PC
                        "preferencias": U.preferencias(self.usuario)
                        if du and U.archivo(self.usuario, "preferencias.json").exists() else None})
        elif u.path == "/api/usuario/estilo":
            if not self.usuario:
                return self._json({"error": "Entrá con tu usuario."}, 403)
            self._json({"formato": U.formato(self.usuario), "general": {k: CFG.get(k) for k in U.FORMATO},
                        "fuentes": list(U.FUENTES), "reglas": U.leer_archivo(self.usuario, "reglas_dictado.md"),
                        "plantillas_propias": [n for n, _ in PL.secciones_de_usuario(self.usuario)],
                        "medicos_propios": MED.medicos_con_notas_propias(self.usuario)})
        elif u.path == "/api/cliente/estado":
            instantanea = VISTA.listar_casos(self.pc)
            casos = [{"nombre": c["nombre"], "titulo": c["titulo"], "estado": c["estado"], "marcas": c["marcas"],
                      "paciente": c["paciente"]}
                     for c in instantanea if c["origen"] == self.pc][:40]
            cola = sum(1 for c in instantanea if c["estado"] in ("en cola", "transcribiendo", "generando"))
            A.anotar_version(self.pc, self.headers.get("User-Agent"))
            self._json({"ok": True, "pc": self.pc, "ia": IA.ia_lista(), "cola": cola, "casos": casos,
                        "version": VERSION, "app": A.resumen()})
        elif u.path == "/api/cliente/actualizacion":
            # lista de archivos de la app con sus huellas: la app baja solo los que cambiaron
            self._json(A.manifiesto())
        elif u.path == "/api/cliente/archivo":
            rel = q.get("ruta", [""])[0]
            p = A.archivo(rel)
            if not p or not p.exists():
                self.send_error(404); return
            if rel.lower() == "transcripcion.exe" and L.una_vez(("app_baja", self.pc, A.resumen()["huella"]), 3600):
                L.info("APP", f"{self.pc} está bajando la versión {A.resumen()['version'] or 'nueva'} de la app.")
            self._enviar_archivo(p)
        elif u.path == "/api/word":
            n = q.get("nombre", [""])[0]
            p = INFORMES / f"{n}.docx"
            if not self._nombre_valido(n) or not p.exists():
                self.send_error(404); return
            pac = PAC.de(DATOS, n)
            nom = re.sub(r'[\\/:*?"<>|]+', "", f"{pac} - {CASOS.titulo_de(n)}" if pac else CASOS.titulo_de(n)).strip()
            self._enviar_archivo(p, descarga=f"{nom or n}.docx")
        elif u.path == "/api/casos":
            ok = IA.ia_lista()
            self._json({"casos": VISTA.listar_casos(self.pc, self.remoto), "ollama": ok, "pc": self.pc,
                        "ia_estado": "caida" if not ok else ("sin_modelo" if IA.ultimo["e"] == "sin_modelo" else "ok"),
                        "modelo": CFG["modelo_ia"], "mensaje": OPER.mensaje_para_pcs(),
                        "pausa": bool(PROC.trabajo.get("en_pausa"))})
        elif u.path == "/api/formato":
            cfg = U.cfg_de(CFG, self.usuario)
            self._json({"palabras_titulo": sorted(PL.PALABRAS_ESTUDIO),
                        "negrita_titulos": cfg.get("negrita_titulos", True),
                        "fuente": cfg.get("fuente"), "tamano": cfg.get("tamano_fuente"),
                        "prefijos": CFG.get("negrita_si_empieza_con", FMT.NEGRITA_DEF),
                        "exactas": CFG.get("negrita_lineas_exactas", FMT.NEGRITA_EXACTAS)})
        elif u.path == "/api/medicos":
            rv = VOZ.resumen()
            out = []
            for m in MED.lista_medicos():
                propias = MED.notas_propias(m, self.usuario)
                x = {"nombre": m, "notas": MED.notas_medico(m, self.usuario), "voz": rv.get(m, {}).get("n", 0),
                     "propias": propias is not None}
                if propias is not None:
                    x["generales"] = MED.notas_medico(m)
                out.append(x)
            self._json({"medicos": out})
        elif u.path == "/api/voces":
            rv = VOZ.resumen()
            self._json({"modelo": VOZ.estado_modelo(), "error": VOZ._DESCARGA.get("error") or "",
                        "parametros": VOZ.parametros(CFG), "medicos": rv,
                        "sin_etiquetar": len(VOCES.casos_sin_etiquetar())})
        elif u.path == "/api/voces/muestras":
            med = q.get("medico", [""])[0]
            out = []
            for c, m in VOZ.muestras(med or None):
                f = {"caso": c, "medico": m.get("medico"), "fecha": m.get("fecha"), "fuente": m.get("fuente"),
                     "seg": m.get("seg"), "titulo": c, "paciente": "", "audio": False}
                try:
                    f.update(titulo=CASOS.titulo_de(c), paciente=PAC.de(DATOS, c), audio=CASOS.ruta_audio(c) is not None)
                except OSError:
                    pass
                out.append(f)
            self._json({"muestras": out})
        elif u.path == "/api/voces/agrupar":
            self._json(VOCES.grupos_de_voces())
        elif u.path == "/api/plantillas":
            self._json({"secciones": PL.secciones_con_origen(self.usuario), "con_usuario": bool(self.usuario)})
        elif u.path == "/api/caso":
            n = q.get("nombre", [""])[0]
            try:
                c = VISTA.cargar_caso(n) if self._nombre_valido(n) else None
            except (BOR.Corrupto, OSError):
                L.error('CASO', 'No se pudo leer el borrador guardado.', exc=True)
                return self._json({'error': 'No se pudo leer el borrador guardado. Conservá sus archivos y solicitá recuperación.'}, 503)
            self._json(c if c else {"error": "no existe"}, 200 if c else 404)
        elif u.path == "/api/onda":
            n = q.get("nombre", [""])[0]
            try:
                d = VISTA.forma_de_onda(n) if self._nombre_valido(n) else None
            except Exception:
                L.error("CASO", f"No pude dibujar la forma de onda de {CASOS.visible(n)}.", exc=True)
                d = None
            self._json(d if d else {"error": "sin audio"}, 200 if d else 404)
        elif u.path.startswith("/audio/"):
            n = urllib.parse.unquote(u.path[7:])
            a = CASOS.ruta_audio(n) if self._nombre_valido(n) else None
            if not a:
                self.send_error(404); return
            self._enviar_archivo(a)
        else:
            self.send_error(404)

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
        self.send_header("Cache-Control", "no-store")    # que Cloudflare no guarde audios ni Word
        if descarga:
            self.send_header("Content-Disposition",
                             "attachment; filename*=UTF-8''" + urllib.parse.quote(descarga))
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

    def _guardar_audio_nuevo(self, original, cuerpo, huella=None):
        """Guarda un audio llegado de otra PC con nombre único y lo pone en cola."""
        with RECIBIR_AUDIO_LOCK:
            return self._recibir_audio_serializado(original, cuerpo, huella)

    def _recibir_audio_serializado(self, original, cuerpo, huella=None):
        if len(cuerpo) < 44 or cuerpo[:4] != b"RIFF" or cuerpo[8:12] != b"WAVE":
            if Path(original).suffix.lower() == ".wav":
                L.aviso("AUDIO", f"{self.pc} envió «{original}» ({L.tamano(len(cuerpo))}) pero no es un WAV "
                                 f"válido (¿llegó incompleto?). No se procesa.")
                return None, "El archivo no es un WAV válido (¿llegó incompleto?)"
        h = hashlib.sha256(cuerpo).hexdigest()
        if huella and huella.lower() != h:
            L.aviso("AUDIO", f"«{original}» de {self.pc} llegó dañado en el viaje; la aplicación lo vuelve a enviar.")
            return None, "El audio llegó dañado: se vuelve a enviar."
        previo = R.buscar_huella(DATOS, h)
        if previo and CASOS.ruta_audio(previo):
            if previo not in PROC.estado:
                PROC.encolar(previo)  # reintento tras una caída entre recepción duradera y encolado
            L.info("AUDIO", f"{self.pc} envió «{original}», que ya estaba cargado como {CASOS.visible(previo)}. "
                            f"No se procesa de nuevo.")
            return {"ok": True, "nombre": previo, "duplicado": True}, None
        ext = Path(original).suffix.lower()
        nombre = R.nombre_unico(self.pc, original,
                                lambda n: any((NUEVOS / f"{n}{e}").exists() for e in EXT_AUDIO))
        escribir_atomico(DATOS / f"{nombre}.origen.txt", self.pc)
        escribir_atomico(DATOS / f"{nombre}.original.txt", Path(original).name)
        # «Cargar audio» desde la página: el que lo sube; la app sola: el que está usando la página en esa PC
        CASOS.poner_usuario_caso(nombre, getattr(self, "usuario", None)
                           or (R.usuario_activo(self.pc) if U.hay_usuarios() else None))
        med = R.medico_pc(self.pc)
        if med:
            escribir_atomico(DATOS / f"{nombre}.medico.txt", med)
        # Publicar al final: el vigilante no debe leer un WAV parcial o sin metadatos.
        escribir_atomico(NUEVOS / f"{nombre}{ext}", cuerpo)
        R.guardar_huella(DATOS, h, nombre)
        PROC.encolar(nombre)
        anunciar_audio(nombre, cuerpo, f"de {self.pc}")
        return {"ok": True, "nombre": nombre, "duplicado": False}, None

    def do_POST(self):
        u = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(u.query)
        if not self._autorizar(u.path):
            return
        try:
            if u.path in ("/entrar", "/ingresar"):   # usuario y contraseña (o, sin transcriptores, la del sistema)
                return self._entrar(urllib.parse.parse_qs(self._body(64 * 1024).decode("utf-8", "replace")))
            if u.path == "/api/cliente/vincular":
                d = json.loads(self._body(64 * 1024) or b"{}")
                pc_nueva = str(d.get("pc", "")).strip()
                usu = str(d.get("usuario") or "").strip()
                llave, err = R.vincular(pc_nueva, str(d.get("contrasena", "")), self._ip(), usuario=usu or None)
                if err:
                    if err.startswith(("Contraseña", "Usuario")):
                        self._avisar_fallo(pc_nueva, self._ip(), "al vincular la aplicación"
                                           + (f" (usuario «{usu[:24]}»)" if usu else ""))
                    else:
                        L.aviso("ACCESO", f"No se vinculó «{pc_nueva[:24]}» (IP {self._ip()}): {err}")
                    return self._json({"error": err}, 403)
                L.ok("ACCESO", f"PC vinculada: {pc_nueva} (IP {self._ip()})"
                               + (f" con el usuario «{usu[:40]}»" if usu else "")
                               + ". Ya puede enviar audios.")
                r = {"ok": True, "llave": llave, "pc": d["pc"].strip(), "version": VERSION}
                usu_ok = U.verificar(usu, str(d.get("contrasena", ""))) if usu and U.hay_usuarios() else None
                if usu_ok:     # la página abre ya con este transcriptor: no se le pide el usuario dos veces
                    r["codigo"] = R.nuevo_codigo(pc_nueva, usuario=usu_ok, seg=180)
                return self._json(r)
            if u.path == "/api/cliente/sesion":
                if not self._llave() or not R.pc_de_llave(self._llave()):
                    if L.una_vez(("llave", self._ip()), 600):
                        L.aviso("ACCESO", f"Una aplicación con una llave no autorizada (¿PC anulada?) intentó "
                                          f"entrar desde la IP {self._ip()}.")
                    return self._json({"error": "Esta PC no está autorizada"}, 401)
                d = json.loads(self._body(16 * 1024) or b"{}")
                # «reconectar»: la app ya estaba abierta y volvió a conectarse (servidor caído o reiniciado, dirección
                # nueva del túnel): sigue la persona que tenía la sesión abierta en esta PC, sin pedirle el usuario
                usu = R.usuario_de_pc(self.pc) if isinstance(d, dict) and d.get("reconectar") is True else None
                return self._json({"ok": True, "codigo": R.nuevo_codigo(self.pc, usuario=usu)})
            if u.path == "/api/cliente/aviso":
                # la app avisa algo que conviene ver en el servidor (ej. una actualización que no abrió)
                d = json.loads(self._body(16 * 1024) or b"{}")
                texto = " ".join(str(d.get("texto", "")).split())[:400]
                if texto:
                    (L.ok if d.get("tipo") == "ok" else L.aviso)("APP", f"{self.pc}: {texto}")
                return self._json({"ok": True})
            if u.path == "/api/cliente/audio":
                original = urllib.parse.unquote(self.headers.get("X-Archivo") or "audio.wav")
                if Path(original).suffix.lower() not in EXT_AUDIO:
                    L.aviso("AUDIO", f"{self.pc} envió «{original}»: formato de audio no soportado.")
                    return self._json({"error": "Formato de audio no soportado"}, 400)
                r, err = self._guardar_audio_nuevo(original, self._body(), self.headers.get("X-Huella"))
                return self._json(r) if r else self._json({"error": err}, 422)
            if u.path == "/api/plantilla_word":
                arch = q.get("archivo", [""])[0].lower()
                if not arch.endswith(".docx"):
                    return self._json({"error": "Guardalo como .docx (en Word: Archivo → Guardar como → "
                                                "Documento de Word) y volvé a intentar."}, 400)
                from importar_informes import plantilla_desde_word
                L.info("CONFIG", f"{self.pc} armó una plantilla desde el Word «{Path(arch).name}».")
                return self._json(plantilla_desde_word(self._body()))
            if u.path == "/api/subir":
                nombre_arch = Path(q.get("archivo", [""])[0]).name
                if Path(nombre_arch).suffix.lower() not in EXT_AUDIO:
                    return self._json({"error": "Formato de audio no soportado"}, 400)
                if self.remoto:     # desde otra PC: nombre único y se anota de qué PC vino
                    r, err = self._guardar_audio_nuevo(nombre_arch, self._body())
                    return self._json(r) if r else self._json({"error": err}, 422)
                destino = NUEVOS / nombre_arch
                cuerpo = self._body()
                escribir_atomico(DATOS / f"{destino.stem}.origen.txt", LOCAL)
                CASOS.poner_usuario_caso(destino.stem, self.usuario)
                med = q.get("medico", [""])[0].strip()
                if med:
                    escribir_atomico(DATOS / f"{destino.stem}.medico.txt", med)
                escribir_atomico(destino, cuerpo)
                PROC.encolar(destino.stem)
                anunciar_audio(destino.stem, cuerpo, "en esta PC")
                return self._json({"ok": True, "nombre": destino.stem})
            datos = json.loads(self._body(20 * 1024 * 1024) or b"{}")
            if u.path == "/api/vista_previa":
                nv = datos.get("nombre") or None
                return self._json(GUARDADO.vista_previa(str(datos.get("texto", "")),
                                               nv if nv and self._nombre_valido(nv) else None, self.usuario))
            if u.path == "/api/admin/entrar":
                return self._panel_entrar(datos)
            if u.path == "/api/admin/salir":
                if self.remoto and R.cerrar_sesion_admin(self._cookie("ta")):
                    L.info("ACCESO", f"{self.pc} salió del panel de administración.")
                return self._json({"ok": True}, cookie=R.COOKIE_ADMIN_BORRAR if self.remoto else None)
            if u.path.startswith("/api/admin/"):
                acc = ADM.acceso(self, PUERTO)
                if acc is None or not ADM.mismo_origen(self, PUERTO):
                    if acc is None and self.remoto and R.admin_configurado() and ADM.mismo_origen(self, PUERTO):
                        return self._json({"error": "La sesión del panel venció: volvé a escribir su contraseña.",
                                           "entrar_panel": True}, 401)
                    L.aviso("ACCESO", f"Pedido al panel de administración rechazado ({u.path}, {self.pc}, "
                                      f"IP {self._ip()}).")
                    return self._json({"error": "No tenés permiso para usar el panel de administración."}, 403)
                return self._json(*accion_admin(u.path[len("/api/admin/"):], datos,
                                                quien=self.pc if acc == "remoto" else None))
            if u.path.startswith("/api/usuario/"):
                if not self.usuario:
                    return self._json({"error": "Entrá con tu usuario."}, 403)
                return self._json(*accion_usuario(u.path[len("/api/usuario/"):], datos, self.usuario, self.pc))
            if u.path == "/api/mi_medico":
                med = datos.get("medico", "").strip()
                if med != R.medico_pc(self.pc):
                    L.info("CONFIG", f"{self.pc} eligió médico para sus audios: {med or 'ninguno'}.")
                R.poner_medico_pc(self.pc, med)
                return self._json({"ok": True})
            if u.path == "/api/medico":
                # destino: "todos" (notas generales, como siempre), "mio" (solo para este transcriptor) o
                # "general" (dejar de usar las propias). Sin destino = "todos" (compatibilidad).
                destino = datos.get("destino") or "todos"
                try:
                    if destino in ("mio", "general") and not datos.get("crear"):
                        if not self.usuario:
                            return self._json({"error": "Para guardar notas solo para vos tenés que entrar con tu usuario."}, 403)
                        nom = str(datos.get("medico", ""))
                        MED.guardar_notas_propias(nom, self.usuario, datos.get("notas", "") if destino == "mio" else None)
                        L.ok("CONFIG", f"Notas propias de {self.quien} sobre {nom} "
                                       + ("guardadas." if destino == "mio" else "quitadas: vuelve a usar las generales."))
                        return self._json({"ok": True, "medico": nom, "destino": destino})
                    nom = MED.guardar_medico(datos.get("medico", ""), datos.get("notas", ""),
                                           crear=datos.get("crear") is True)
                    if self.usuario and not datos.get("crear"):
                        MED.guardar_notas_propias(nom, self.usuario, None)   # pasan a ser las de todos
                except FileExistsError as ex:
                    return self._json({"error": str(ex)}, 409)
                except FileNotFoundError as ex:
                    return self._json({"error": str(ex)}, 404)
                except ValueError as ex:
                    return self._json({"error": str(ex)}, 400)
                L.ok("CONFIG", f"Notas del médico {nom} guardadas para todos ({self.quien}).")
                return self._json({"ok": True, "medico": nom, "destino": "todos"})
            if u.path == "/api/voces/etiquetar":     # {"nombres": [...], "medico": "..."} desde «Agrupar voces»
                med = str(datos.get("medico") or "").strip()
                nombres = datos.get("nombres") or []
                if not med or not isinstance(nombres, list) or not nombres or len(nombres) > 500:
                    return self._json({"error": "Elegí el médico y al menos un audio."}, 400)
                ok, salteados = [], []
                for x in dict.fromkeys(str(v) for v in nombres):
                    v = CASOS.voz_de(x) if self._nombre_valido(x) else None
                    otro = R.bloqueado_por(x, self.pc) if v else None
                    if not v or not v.get("h") or otro:
                        salteados.append({"nombre": x, "motivo": f"lo está revisando {otro}" if otro else "sin huella de voz"})
                        continue
                    (DATOS / f"{x}.medico.txt").write_text(med, encoding="utf-8")
                    CASOS.anotar_voz(x, medico_por="usuaria")
                    VOZ.agregar(x, med, v["h"], "etiquetado", v.get("seg"))
                    ok.append(x)
                k = VOZ.resumen().get(med, {}).get("n", 0)
                L.ok("VOZ", f"{self.pc} etiquetó {L.plural(len(ok), 'audio')} como de «{med}» (ahora tiene "
                            f"{L.plural(k, 'muestra')} de voz)" + (f"; {len(salteados)} salteado(s)" if salteados else "") + ".")
                return self._json({"ok": True, "etiquetados": ok, "salteados": salteados, "muestras": k})
            if u.path == "/api/voces/quitar":       # {"caso": "..."}: sacar una muestra mal etiquetada
                c = str(datos.get("caso") or "")
                viejo = VOZ.quitar(c) if self._nombre_valido(c) else None
                if viejo:
                    if (DATOS / f"{c}.voz.json").exists() and CASOS.medico_de(c) == viejo and not (DATOS / f"{c}.final.txt").exists():
                        CASOS.anotar_voz(c, medico_por="")
                    L.info("VOZ", f"{self.pc} quitó la muestra de voz de {CASOS.visible(c)} de «{viejo}».")
                return self._json({"ok": bool(viejo)})
            if u.path == "/api/importar":
                from importar_informes import importar
                ok, mal = importar()
                L.ok("CONFIG", f"Importados {L.plural(len(ok), 'informe')} Word como referencia ({self.pc}).",
                     [f"No se pudieron leer: {', '.join(mal)}"] if mal else None)
                return self._json({"ok": ok, "mal": mal})
            if u.path == "/api/plantillas":
                secs = [(x.get("nombre", ""), x.get("cuerpo", "")) for x in datos.get("secciones", [])
                        if isinstance(x, dict)]
                if not secs:
                    return self._json({"error": "No hay plantillas para guardar"}, 400)
                destino = datos.get("destino") or ("mio" if self.usuario else "todos")
                try:
                    r = PL.aplicar_plantillas(secs, self.usuario, destino)
                except ValueError as ex:
                    return self._json({"error": str(ex)}, 400)
                if r["sin_cambios"]:
                    return self._json({"ok": True, **r})
                if destino == "todos":
                    L.ok("CONFIG", f"Plantillas guardadas para todos por {self.quien} ({L.plural(r['generales'], 'cambio')}); "
                                   f"la versión anterior quedó en conocimiento\\copias.")
                else:
                    L.ok("CONFIG", f"Plantillas propias de {self.quien} guardadas ({L.plural(r['propias'], 'cambio')}).")
                return self._json({"ok": True, **r})
            if u.path == "/api/plantillas/general":     # quitar la versión propia de una plantilla
                if not self.usuario:
                    return self._json({"error": "Entrá con tu usuario."}, 403)
                nom = str(datos.get("nombre") or "")
                ok = PL.volver_a_general(self.usuario, nom)
                if ok:
                    L.info("CONFIG", f"{self.quien} volvió a la plantilla general de «{nom}».")
                return self._json({"ok": ok})
            if u.path == "/api/borrar":      # uno o varios casos: {"nombres": [...]}
                nombres = datos.get("nombres") or ([datos["nombre"]] if datos.get("nombre") else [])
                if not isinstance(nombres, list) or not nombres or len(nombres) > 500:
                    return self._json({"error": "No hay informes para borrar"}, 400)
                ok, mal = [], []
                for x in dict.fromkeys(str(v) for v in nombres):
                    if not self._nombre_valido(x):
                        mal.append({"nombre": x, "error": "nombre inválido"})
                        continue
                    err = BORRADO.borrar_caso(x, self.pc, self.remoto)
                    (mal.append({"nombre": x, "error": err}) if err else ok.append(x))
                if len(ok) > 1:
                    L.ok("CASO", f"{self.pc} borró {L.plural(len(ok), 'informe')}"
                                 + (f" ({len(mal)} no se {'pudo' if len(mal) == 1 else 'pudieron'} borrar)" if mal else "") + ".")
                if mal and not ok and len(mal) == 1:
                    code = 403 if mal[0]["error"].startswith("Solo se pueden") else 409
                    return self._json({"error": mal[0]["error"], "borrados": ok, "fallidos": mal}, code)
                return self._json({"ok": True, "borrados": ok, "fallidos": mal})
            n = datos.get("nombre", "")
            if not self._nombre_valido(n):
                return self._json({"error": "nombre inválido"}, 400)
            if u.path in ("/api/caso/pausar", "/api/caso/reanudar"):
                accion = "pausar" if u.path.endswith("/pausar") else "reanudar"
                if self.remoto:
                    if L.una_vez(("pausa_remota", self.pc), 600):
                        L.aviso("ACCESO", f"{self.pc} intentó {accion} la transcripción de {CASOS.visible(n)}: solo se "
                                          f"puede desde la PC del servidor.")
                    return self._json({"error": "Pausar o reanudar una transcripción solo se puede en la PC del "
                                                "servidor."}, 403)
                if not origen_local(self):
                    return self._json({"error": "Pedido rechazado: no viene de esta página."}, 403)
                r, code = (PROC.pausar if accion == "pausar" else PROC.reanudar)(n, "la lista de informes")
                return self._json(r, code)
            if u.path == "/api/caso/bloquear":
                previo = R.BLOQUEOS.get(n)
                # la página que ya lo tenía abierto avisa cada 15 s que sigue ahí (manda el tiempo de revisión)
                r = R.bloquear(n, self.pc, renovar="rev" in datos or bool(datos.get("renovar")))
                if r is R.LIBERADO:
                    return self._json({"ok": False, "liberado": True, "por": "el panel de administración"})
                if r is True:
                    CASOS.sumar_revision(n, datos.get("rev"), self.pc)
                    if not previo or previo["pc"] != self.pc or time.time() - previo["t"] > R.BLOQUEO_SEG:
                        L.info("CASO", f"{self.pc} abrió {CASOS.visible(n)} para revisar.")
                elif L.una_vez(("ocupado", n, self.pc), 120):
                    L.info("CASO", f"{self.pc} quiso abrir {CASOS.visible(n)}, pero lo está revisando {r}.")
                return self._json({"ok": True} if r is True else {"ok": False, "por": r})
            if u.path == "/api/caso/soltar":
                if R.bloqueado_por(n, self.pc) is None:
                    CASOS.sumar_revision(n, datos.get("rev"), self.pc)
                R.soltar(n, self.pc)
                L.debug("CASO", f"{self.pc} cerró {CASOS.visible(n)}.")
                return self._json({"ok": True})
            otro = R.bloqueado_por(n, self.pc) or (R.liberado_para(n, self.pc) and "el panel de administración")
            if otro and u.path in ("/api/borrador", "/api/finalizar", "/api/procesar", "/api/caso_medico", "/api/paciente",
                                       "/api/formato_caso", "/api/formato_caso/agregar"):
                if L.una_vez(("conflicto", n, self.pc), 120):
                    L.aviso("CASO", f"{self.pc} intentó modificar {CASOS.visible(n)} " + (
                        "después de que se lo liberaron desde el panel" if otro == "el panel de administración"
                        else f"mientras lo revisa {otro}") + "; no se guardó su cambio.")
                if otro == "el panel de administración":
                    return self._json({"error": "Desde el panel de administración se liberó este caso: cerralo y "
                                                "volvé a abrirlo desde la lista para seguir.", "liberado": True}, 409)
                return self._json({"error": f"Este caso lo está revisando {otro}."}, 409)
            if u.path == "/api/caso_medico":
                med = datos.get("medico", "").strip()
                f = DATOS / f"{n}.medico.txt"
                if med:
                    f.write_text(med, encoding="utf-8")
                else:
                    f.unlink(missing_ok=True)
                CASOS.anotar_voz(n, medico_por="usuaria" if med else "")
                if (DATOS / f"{n}.final.txt").exists():
                    VOCES.actualizar_muestra(n, med)       # ya guardado: la muestra de voz se corrige al momento
                L.info("CASO", f"{CASOS.visible(n)}: médico cambiado a {med or 'ninguno'} ({self.pc}).")
                vz = VOCES.resumen_voz(n) or {}
                return self._json({"ok": True, "voz": vz,
                                   "regenerar": bool(vz) and (vz.get("medico_ia") or "") != med
                                   and not (DATOS / f"{n}.final.txt").exists()})
            if u.path == "/api/paciente":
                p = PAC.corregir(DATOS, n, datos.get("paciente", ""))
                L.info("CASO", f"{CASOS.visible(n)}: nombre del paciente " + ("corregido a mano" if datos.get("paciente", "").strip()
                                                                       else "vuelto a sacar del dictado") + f" ({self.pc}).")
                return self._json({"ok": True, "paciente": p})
            if u.path == "/api/procesar":
                if n in PROC.pausas or PROC.estado.get(n, {}).get("estado") == "en pausa":
                    return self._json({"error": "Está en pausa: reanudalo desde la lista."}, 409)
                L.info("IA", f"{self.quien} pidió volver a generar {CASOS.visible(n)}"
                             + (" con su estilo." if self.usuario else "."))
                if self.usuario:
                    CASOS.poner_usuario_caso(n, self.usuario)     # volver a generar = con el estilo de quien lo pide
                PROC.encolar(n)
                return self._json({"ok": True})
            if u.path == "/api/borrador":
                try:
                    revision = BOR.guardar(DATOS, n, datos)
                except BOR.Conflicto as ex:
                    return self._json({"error": str(ex)}, 409)
                except BOR.Corrupto as ex:
                    return self._json({'error': str(ex)}, 503)
                except ValueError as ex:
                    return self._json({"error": str(ex)}, 400)
                except OSError:
                    L.error("CASO", "No se pudo guardar el borrador en disco.", exc=True)
                    return self._json({"error": "No se pudo guardar el borrador en el servidor. Conservá el caso abierto y reintentá."}, 503)
                return self._json({"ok": True, "revision": revision})
            if u.path == "/api/formato_caso":     # formato elegido a mano en la vista previa
                f = DATOS / f"{n}.formato.json"
                fm = datos.get("formato")
                if isinstance(fm, dict) and fm.get("parrafos"):
                    escribir_atomico(f, json.dumps(fm, ensure_ascii=False))
                else:
                    f.unlink(missing_ok=True)
                L.debug("CASO", f"{CASOS.visible(n)}: formato de la vista previa guardado ({self.pc}).")
                return self._json({"ok": True})
            if u.path == "/api/formato_caso/agregar":     # formato de una autocorrección de Word (app del trabajo)
                nuevos = []
                for x in (datos.get("parrafos") or [])[:200]:
                    if not isinstance(x, dict) or not isinstance(x.get("t"), str) or not x["t"].strip():
                        continue
                    r = [y for y in (x.get("r") or []) if isinstance(y, dict) and isinstance(y.get("t"), str)]
                    nuevos.append({"t": x["t"], "a": x.get("a") if isinstance(x.get("a"), str) else "",
                                   "r": r or [{"t": x["t"]}]})
                if nuevos:
                    with FMT_LOCK:
                        fm = CASOS.formato_de(n)
                        if not isinstance(fm, dict) or not isinstance(fm.get("parrafos"), list):
                            fm = {"v": 1, "parrafos": []}
                        fm["parrafos"].extend(nuevos)
                        (DATOS / f"{n}.formato.json").write_text(json.dumps(fm, ensure_ascii=False), encoding="utf-8")
                    L.debug("CASO", f"{CASOS.visible(n)}: formato de una autocorrección de Word agregado ({self.pc}).")
                return self._json({"ok": True})
            if u.path == "/api/finalizar":
                CASOS.sumar_revision(n, datos.get("rev"), self.pc)
                return self._json(GUARDADO.finalizar(n, datos.get("texto", ""), self.pc, self.usuario))
            if u.path == "/api/abrir":
                p = INFORMES / f"{n}.docx"
                if p.exists() and not self.remoto:
                    try:
                        P.abrir(p)
                    except OSError:
                        pass
                return self._json({"ok": p.exists()})
            self.send_error(404)
        except CP.ErrorCola:
            L.error('COLA', 'No se confirmó la operación en la cola persistente.', exc=True)
            self._json({'error': 'No se pudo confirmar la cola del servidor. Conservá el audio y reintentá.'}, 503)
        except PermissionError:
            L.aviso("INFORME", f"No se pudo guardar ({u.path}, {self.pc}): el Word está abierto. "
                               f"Hay que cerrarlo y volver a intentar.")
            self._json({"error": "El Word está abierto: cerralo y volvé a intentar."}, 409)
        except Exception as ex:
            L.error("SERVIDOR", f"Falló {u.path} pedido por {getattr(self, 'pc', '?')}: {mensaje_amigable(ex)}",
                    exc=True)
            self._json({"error": str(ex)}, 500)

    # ------------------------------------------- panel de administración desde el trabajo
    def _panel_sin_permiso(self, ruta):
        """Pedido al panel sin permiso. Desde el trabajo: si el panel está habilitado, se pide su contraseña."""
        es_pagina = ruta in PAGINAS_ADMIN
        if self.remoto:
            if R.admin_configurado():
                if es_pagina:
                    return self._html(pagina_panel_entrar(self.pc, ruta))
                return self._json({"error": "La sesión del panel venció: volvé a escribir su contraseña.",
                                   "entrar_panel": True}, 401)
            if L.una_vez(("admin_remoto", self.pc), 600):
                L.aviso("ACCESO", f"{self.pc} intentó abrir el panel de administración, pero no está habilitado para "
                                  f"las PC del trabajo (falta configurar su contraseña en el panel del servidor).")
            if es_pagina:
                return self._html(PAGINA_PANEL_NO_HABILITADO)
            return self._json({"error": "El panel de administración no está habilitado para las PC del trabajo."}, 403)
        if L.una_vez(("admin_host", self.headers.get("Host")), 600):
            L.aviso("ACCESO", f"Pedido al panel de administración con la dirección «{(self.headers.get('Host') or '')[:60]}» "
                              f"rechazado: en esta PC el panel se abre como http://127.0.0.1:{PUERTO}/admin.")
        if es_pagina:
            return self._html(PAGINA_SOLO_LOCAL, 403)
        return self._json({"error": "El panel de administración se abre como http://127.0.0.1:%d/admin." % PUERTO}, 403)

    def _panel_entrar(self, datos):
        if not self.remoto:
            return self._json({"ok": True})          # en la PC del servidor no hace falta contraseña
        ip = self._ip()
        motivo = ADM.motivo_origen(self, PUERTO)
        if motivo:
            L.aviso("ACCESO", f"Pedido para entrar al panel desde {self.pc} rechazado: no vino de la página del panel "
                              f"(IP {ip}; {motivo}).")
            return self._json({"error": "Pedido rechazado."}, 403)
        if not R.admin_configurado():
            return self._json({"error": "El panel de administración no está habilitado para las PC del trabajo."}, 403)
        clave = f"admin:{self.pc}"
        if R.demasiados_fallos(clave):
            if L.una_vez(("admin_bloq", self.pc), 120):
                L.aviso("ACCESO", f"{self.pc} sigue intentando entrar al panel de administración: bloqueado 10 minutos "
                                  f"por contraseñas incorrectas (IP {ip}).")
            return self._json({"error": "Demasiados intentos fallidos. Esperá 10 minutos."}, 429)
        if not R.contrasena_admin_ok(str(datos.get("contrasena", ""))):
            R.anotar_fallo(clave)
            k = len(R.FALLOS.get(clave, []))
            L.aviso("ACCESO", f"Contraseña del panel de administración incorrecta desde {self.pc} (IP {ip}). "
                              + ("Esa PC queda bloqueada 10 minutos para el panel." if k >= 5 else f"Intento {k} de 5."))
            return self._json({"error": "Contraseña incorrecta." + ("" if k >= 5 else
                                         f" Te quedan {5 - k} {'intento' if 5 - k == 1 else 'intentos'}.")}, 401)
        R.FALLOS.pop(clave, None)
        tok = R.nueva_sesion_admin(self.pc, ip)
        L.ok("ACCESO", f"{self.pc} entró al panel de administración desde el trabajo (IP {ip}).")
        return self._json({"ok": True}, cookie=R.cookie_admin(tok))

    def _avisar_fallo(self, pc, ip, donde):
        k = len(R.FALLOS.get(ip, []))
        extra = " La IP queda bloqueada 10 minutos." if k >= 5 else f" Intento {k} de 5."
        L.aviso("ACCESO", f"Contraseña incorrecta para «{pc[:24]}» {donde} (IP {ip}).{extra}")


# ------------------------------------------------------- panel de administración
def estado_tunel():
    t = R.URL_TUNEL
    if not TUNEL["modo"]:
        e = "apagado"
    elif not R.configurado():
        e = "sin_contrasena"
    elif TUNEL["error"]:
        e = "puerto_ocupado"
    elif not t.get("iniciado"):
        e = "detenido"
    else:
        e = {"activo": "activo", "abriendo": "abriendo", "reconectando": "reconectando",
             "sin cloudflared": "sin_cloudflared", "sin devtunnel": "sin_devtunnel",
             "sin sesion": "sin_sesion", "sin configurar": "sin_configurar",
             "error": "reconectando"}.get(t.get("estado") or "", "abriendo")
        if e == "abriendo" and t.get("url") and t.get("servicio") != "devtunnel":
            e = "conectando"           # ya tiene dirección, falta que Cloudflare confirme la conexión
    servicio = t.get("servicio") or R.servicio_tunel()
    return {"modo": TUNEL["modo"], "estado": e, "url": t.get("url"), "desde": t.get("desde"),
            "servicio": servicio, "nombre_servicio": R.nombre_servicio(servicio), "error": TUNEL["error"],
            "puerto_tunel": PUERTO_TUNEL if servicio == "devtunnel" else None,
            "cambio": t.get("cambio"), "publicada": t.get("publicada"), "error_pub": t.get("error_pub"),
            "reinicios": t.get("reinicios", 0), "centro": t.get("centro")}


def estado_admin():
    ahora = time.time()
    try:
        cs = VISTA.listar_casos()
    except Exception:
        cs = []
    k = {e: sum(1 for c in cs if c["estado"] == e) for e in ("listo", "nuevo", "error", "revisado")}
    if not SIMULAR and ahora - _PANEL["gpu_t"] > 3:
        _PANEL["gpu"], _PANEL["gpu_t"] = placa_de_video(), ahora
    gpu = _PANEL["gpu"]
    man = A.manifiesto()
    oficial = man.get("version") or ""
    vinc = R.pcs_vinculadas()
    nombres = set(vinc) | set(VISTO) | {v["pc"] for v in list(R.SESIONES.values())}
    con_panel = {x["pc"] for x in R.sesiones_admin()}
    pcs = []
    for pc in sorted(nombres, key=str.lower):
        v = vinc.get(pc, {})
        ultima = max(VISTO.get(pc, 0), v.get("ultima") or 0) or None
        version = A.VERSION_PC.get(pc) or v.get("version")
        pcs.append({"pc": pc, "llaves": v.get("llaves", 0), "vinculada": v.get("vinculada"),
                    "ultima_vinculacion": v.get("ultima_vinculacion"), "ultima": ultima,
                    "conectada": bool(ultima and ahora - ultima < 60), "version": version,
                    "desactualizada": bool(version and oficial and version != oficial),
                    "medico": R.medico_pc(pc), "sesiones": R.sesiones_de(pc), "panel": pc in con_panel,
                    "revisando": sorted(CASOS.visible(c) for c, b in list(R.BLOQUEOS.items())
                                        if b["pc"] == pc and ahora - b["t"] < R.BLOQUEO_SEG)})
    gen, tr = PROC.en_estado("generando"), PROC.en_estado("transcribiendo")
    return {
        "ahora": ahora,
        "servidor": {"version": VERSION, "desde": INICIO, "simulado": SIMULAR, "url": f"http://127.0.0.1:{PUERTO}",
                     "registros": str(L.CARPETA),
                     "sistema": P.NOMBRE, "puede_abrir": P.puede_abrir()},
        "ia": {"estado": IA.ultimo["e"], "modelo": CFG["modelo_ia"],
               "trabajando": f"armando el informe de «{CASOS.titulo_de(gen[0])}»" if gen else None},
        "whisper": {"modelo": CFG["modelo_whisper"],
                    "trabajando": f"transcribiendo «{CASOS.titulo_de(tr[0])}»" if tr else None},
        "gpu": gpu[0] if gpu else ("simulada (modo prueba)" if SIMULAR else None), "gpu_tono": gpu[1] if gpu else None,
        "casos": {**k, "en_proceso": PROC.en_proceso()},
        "hoy": dict(L.HOY),
        "tunel": estado_tunel(),
        "contrasena": R.configurado(),
        "usuarios": estado_usuarios(),
        "admin_remoto": {"configurada": R.admin_configurado(), "desde": R.admin_desde(), "sesiones": R.sesiones_admin()},
        "app": {"version": oficial, "archivos": len(man.get("archivos", []))},
        "pcs": pcs,
        "registro": ADM.ultimos_eventos(),
        "mantenimiento": OPER.estado_mantenimiento(),
        "cola": cola_en_vivo(),
        "abiertos": casos_abiertos(),
    }


def estado_usuarios():
    ses = R.sesiones_de_usuarios()
    out = []
    for u in U.lista():
        prop = {"plantillas": len(PL.secciones_de_usuario(u["clave"])),
                "medicos": len(MED.medicos_con_notas_propias(u["clave"])),
                "reglas": bool(U.leer_archivo(u["clave"], "reglas_dictado.md").strip()),
                "formato": bool(U.formato(u["clave"]))}
        out.append({**u, "en": sorted(set(ses.get(u["clave"], []))), "propio": prop})
    return out


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
        L.info("CONFIG", f"{nombre} cambió el formato de su Word ({pc}): "
                         + (", ".join(f"{k}={v}" for k, v in f.items()) or "vuelve al general") + ".")
        return {"ok": True, "formato": f}, 200
    if accion == "reglas":
        texto = d.get("reglas")
        if not isinstance(texto, str) or len(texto) > 50_000:
            return {"error": "Las reglas tienen que ser texto (como mucho 50.000 caracteres)."}, 400
        U.escribir_archivo(usuario, "reglas_dictado.md", texto.strip() + "\n" if texto.strip() else "")
        L.ok("CONFIG", f"{nombre} guardó sus reglas de dictado propias ({pc}).")
        return {"ok": True}, 200
    return {"error": "Acción desconocida"}, 404


def accion_admin(accion, d, quien=None):
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
                nombre = MED.guardar_medico(d.get("nombre", ""), d.get("notas", ""),
                                          crear=accion == "medicos/agregar",
                                          original=d.get("original") if accion == "medicos/modificar" else None)
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
                L.ok("ACCESO", f"Transcriptor creado: {U.nombre_de(clave)} {desde}. Entra con la contraseña inicial "
                               f"y la cambia la primera vez.")
                return {"ok": True, "usuario": clave, "msg": f"Listo: {U.nombre_de(clave)} ya puede entrar."}, 200
            if accion == "usuarios/contrasena":
                U.poner_contrasena(clave, str(d.get("contrasena") or ""), cambiar=True)
                n = R.cerrar_sesiones_usuario(clave)
                L.ok("ACCESO", f"Contraseña de {U.nombre_de(clave)} restablecida {desde}"
                               + (f"; se cerraron {L.plural(n, 'sesión abierta', 'sesiones abiertas')}." if n else "."))
                return {"ok": True, "msg": "Contraseña restablecida: la cambia la próxima vez que entre."}, 200
            if accion == "usuarios/activo":
                activo = d.get("activo") is True
                U.activar(clave, activo)
                if not activo:
                    R.cerrar_sesiones_usuario(clave)
                L.ok("ACCESO", f"Transcriptor {U.nombre_de(clave)} {'reactivado' if activo else 'desactivado'} {desde}.")
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
        L.aviso("ACCESO", f"{quien} intentó «{accion}» en el panel de administración: solo se puede en la PC del servidor.")
        return {"error": "Eso solo se puede hacer en la PC del servidor."}, 403
    if accion == "tunel/reiniciar":
        err = R.reiniciar_tunel()
        if err:
            return {"error": err}, 409
        L.info("TÚNEL", f"Reinicio del túnel pedido {desde}.")
        if R.URL_TUNEL.get("servicio") == "devtunnel":
            return {"ok": True, "msg": "Túnel reiniciándose: en unos segundos vuelve, con la misma dirección."}, 200
        return {"ok": True, "msg": "Túnel reiniciándose: en unos segundos tiene dirección nueva y se publica sola."}, 200
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
        VISTO.pop(pc, None)
        L.aviso("ACCESO", f"PC anulada {desde}: {pc} ({L.plural(n, 'llave')}, "
                          f"{L.plural(tenia_sesion, 'sesión abierta', 'sesiones abiertas')}). "
                          f"Para volver a usarla hay que vincularla de nuevo con la contraseña.")
        return {"ok": True, "msg": f"{pc} anulada. Para volver a usarla hay que vincularla con la contraseña."}, 200
    if accion == "contrasena":
        c = str(d.get("contrasena", ""))
        if len(c) < 8:
            return {"error": "Usá al menos 8 caracteres."}, 400
        if R.contrasena_admin_ok(c):
            return {"error": "Usá una contraseña distinta de la del panel de administración."}, 400
        ya = R.configurado()
        R.poner_contrasena(c)
        L.ok("ACCESO", "Contraseña del acceso remoto " + ("cambiada" if ya else "configurada")
             + f" {desde}. Las PC ya vinculadas siguen funcionando.")
        msg = "Contraseña " + ("cambiada" if ya else "guardada") + ". Las PC ya vinculadas siguen funcionando."
        if TUNEL["modo"] and not R.URL_TUNEL.get("iniciado"):
            abrir_tunel()
            msg += " Abriendo el túnel para las PC del trabajo…"
        return {"ok": True, "msg": msg}, 200
    if accion == "contrasena_admin":
        c = str(d.get("contrasena", ""))
        if len(c) < 10:
            return {"error": "Usá al menos 10 caracteres: con esta contraseña se maneja todo el servidor."}, 400
        if R.contrasena_ok(c):
            return {"error": "Usá una contraseña distinta de la del acceso remoto (esa la conocen todas las PC del trabajo)."}, 400
        ya = R.admin_configurado()
        n = R.poner_contrasena_admin(c)
        L.ok("ACCESO", "Contraseña del panel de administración desde el trabajo " + ("cambiada" if ya else "configurada")
             + ": desde ahora se puede abrir el panel en las PC del trabajo con esa contraseña."
             + (f" Se cerraron {L.plural(n, 'sesión abierta', 'sesiones abiertas')} del panel." if n else ""))
        return {"ok": True, "msg": ("Contraseña cambiada." if ya else "Listo: el panel ya se puede abrir desde las PC del trabajo.")
                + (f" {_cerradas(n)} del panel abiertas con la anterior." if n else "")}, 200
    if accion == "contrasena_admin/quitar":
        if not R.admin_configurado():
            return {"error": "El panel ya no se puede abrir desde el trabajo."}, 409
        n = R.quitar_contrasena_admin()
        L.aviso("ACCESO", "Acceso al panel de administración desde el trabajo desactivado"
                + (f"; se cerraron {L.plural(n, 'sesión abierta', 'sesiones abiertas')}." if n else "."))
        return {"ok": True, "msg": "Listo: el panel ya no se puede abrir desde las PC del trabajo."
                + (f" {_cerradas(n)}." if n else "")}, 200
    if accion == "sesiones_admin/cerrar":
        n = R.cerrar_sesiones_admin()
        L.info("ACCESO", f"Sesiones del panel de administración cerradas desde esta PC: {n}.")
        return {"ok": True, "msg": f"{_cerradas(n)} del panel." if n else "No había sesiones abiertas."}, 200
    if accion == "reinicio":
        return OPER.programar_reinicio(d.get("en"), d.get("avisar", True), d.get("texto"), quien)
    if accion == "reinicio/cancelar":
        return OPER.cancelar_reinicio(quien)
    if accion == "reinicio/ya":
        return OPER.reiniciar_ya(quien)
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
        if OPER.reinicio and OPER.reinicio.get("avisar"):
            return {"error": "Hay un reinicio programado con su aviso en pantalla: cancelalo o esperá a que termine."}, 409
        OPER.poner_mensaje(texto, minutos, tipo, por=quien)
        L.info("SERVIDOR", f"Mensaje para las PC {desde}" + (f" (por {minutos} min)" if minutos else "") + f": «{texto}»")
        return {"ok": True, "msg": "Mensaje publicado: aparece en todas las PC en unos segundos."}, 200
    if accion == "mensaje/quitar":
        if OPER.reinicio and OPER.mensaje.get("reinicio"):
            return {"error": "Ese aviso es del reinicio programado: para quitarlo, cancelá el reinicio."}, 409
        if not OPER.quitar_mensaje():
            return {"error": "No hay ningún mensaje en pantalla."}, 409
        L.info("SERVIDOR", f"Mensaje para las PC quitado {desde}.")
        return {"ok": True, "msg": "Mensaje quitado."}, 200
    if accion in ("caso/pausar", "caso/reanudar"):
        n = str(d.get("nombre", ""))
        if not n or "/" in n or "\\" in n or ".." in n:
            return {"error": "Caso inválido."}, 400
        return (PROC.pausar if accion == "caso/pausar" else PROC.reanudar)(n, "el panel de administración")
    if accion == "caso/liberar":
        n = str(d.get("nombre", ""))
        if not n or "/" in n or "\\" in n or ".." in n:
            return {"error": "Caso inválido."}, 400
        pc = R.liberar(n)
        if not pc:
            return {"error": "Ese caso ya no está abierto en ninguna PC."}, 409
        L.aviso("CASO", f"{CASOS.visible(n)} liberado {desde}: lo tenía abierto {pc}. Lo que escribió hasta su último "
                        f"guardado automático quedó como borrador; ya se puede abrir desde otra PC.")
        return {"ok": True, "msg": f"Caso liberado. {pc} deja de poder guardar cambios en él; ya se puede abrir desde otra PC."}, 200
    if accion == "correcciones/regla":
        r = CORR.agregar_regla(str(d.get("texto", "")))
        if r.get("error"):
            return r, 400
        L.ok("CONFIG", f"Regla agregada a reglas_dictado.md {desde}: «{r['linea']}» (copia anterior en conocimiento\\copias).")
        return {"ok": True, "msg": "Regla agregada: la IA la usa desde el próximo informe.", "linea": r["linea"]}, 200
    if accion == "abrir":
        que = d.get("que")
        rutas = {"registros": L.CARPETA, "registro_hoy": L.archivo_del_dia(), "cliente": AQUI / "cliente"}
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


# Lo que desde una PC del trabajo no se puede hacer aunque se tenga la contraseña del panel: abrir carpetas o
# archivos (se abrirían en la pantalla del servidor) y tocar la contraseña del propio panel o sus sesiones.
SOLO_EN_EL_SERVIDOR = {"abrir", "contrasena_admin", "contrasena_admin/quitar", "sesiones_admin/cerrar",
                       "correcciones/regla", "caso/pausar", "caso/reanudar"}

PAGINA_PANEL_NO_HABILITADO = """<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Administración · Transcripción</title>
<style>:root{color-scheme:light dark}body{margin:0;min-height:100vh;display:grid;place-items:center;
font:15px/1.5 "Segoe UI",system-ui,sans-serif;background:Canvas;color:CanvasText}
div{max-width:440px;padding:24px}h1{font-size:19px;margin:0 0 8px}a.volver{display:inline-block;margin-top:6px;font-weight:600;text-decoration:none;color:CanvasText;border:1px solid GrayText;border-radius:7px;padding:7px 14px}a.volver:hover{border-color:#1f5fbf}a.volver:focus-visible{outline:2px solid #1f5fbf;outline-offset:2px}</style></head>
<body><div><h1>Panel no habilitado en el trabajo</h1><p>El panel de administración todavía no se puede abrir desde
las PC del trabajo. Para habilitarlo, en la PC del servidor abrí <b>http://127.0.0.1:8765/admin</b> y configurá
la <b>contraseña del panel desde el trabajo</b>.</p>
<p><a class="volver" href="/">Volver a los informes</a></p></div></body></html>"""


def pagina_panel_entrar(pc, volver):
    import html as _h
    return (PAGINA_PANEL_ENTRAR.replace("{{pc}}", _h.escape(pc or ""))
            .replace("{{volver}}", json.dumps(volver if volver in PAGINAS_ADMIN else "/admin")))


PAGINA_PANEL_ENTRAR = """<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Panel de administración · Transcripción</title>
<style>:root{color-scheme:light;--bg:#f3f2ef;--p:#fbfbfa;--tx:#1d1d1b;--mu:#5c5b55;--bd:#cfcdc6;--ac:#1f5fbf;--err:#b3261e}
@media (prefers-color-scheme:dark){:root{color-scheme:dark;--bg:#141413;--p:#1b1b1a;--tx:#ebeae5;--mu:#a19f98;--bd:#45443f;--ac:#7aa7f0;--err:#ff8a80}}
body{margin:0;min-height:100vh;display:grid;place-items:center;background:var(--bg);color:var(--tx);font:15px/1.45 "Segoe UI",system-ui,sans-serif}
form{background:var(--p);border:1px solid var(--bd);border-radius:12px;padding:28px;width:min(380px,calc(100vw - 32px));box-sizing:border-box;display:flex;flex-direction:column;gap:14px}
h1{font-size:20px;margin:0}p{margin:0;color:var(--mu);font-size:13.5px}label{display:flex;flex-direction:column;gap:4px;font-weight:600}
input{font:inherit;font-weight:400;color:var(--tx);background:var(--bg);border:1px solid var(--bd);border-radius:7px;padding:8px 10px}
input:focus-visible,button:focus-visible,a:focus-visible{outline:2px solid var(--ac);outline-offset:2px}
button{font:inherit;font-weight:600;background:var(--ac);color:#fff;border:0;border-radius:7px;padding:9px;cursor:pointer}
button:disabled{opacity:.6;cursor:default}.err{color:var(--err);font-weight:600;font-size:13.5px;min-height:1em}
a.volver{display:block;text-align:center;font-weight:600;text-decoration:none;color:var(--tx);background:var(--p);
border:1px solid var(--bd);border-radius:7px;padding:8px}
a.volver:hover{border-color:var(--ac)}</style>
</head><body><form id="f" autocomplete="off"><h1>Panel de administración</h1>
<p>Estás en <b>{{pc}}</b>. Escribí la contraseña del panel: es distinta de la del acceso remoto y la configura
quien administra el servidor.</p>
<label>Contraseña del panel<input id="c" type="password" required autocomplete="off" autofocus></label>
<div class="err" id="err" role="alert"></div>
<button id="b">Entrar al panel</button><a class="volver" href="/">Volver a los informes</a></form>
<script>
const VOLVER = {{volver}};
document.getElementById('f').onsubmit = async ev => {
  ev.preventDefault();
  const b = document.getElementById('b'), c = document.getElementById('c'), err = document.getElementById('err');
  b.disabled = true; err.textContent = '';
  try {
    const r = await fetch('/api/admin/entrar', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Panel': '1'},
                                                 body: JSON.stringify({contrasena: c.value})});
    const j = await r.json().catch(() => ({}));
    if(r.ok){ location.replace(VOLVER); return; }
    if(j.entrar){ location.replace('/'); return; }
    err.textContent = j.error || ('No se pudo entrar (error ' + r.status + ').');
  } catch(e){ err.textContent = 'No hay conexión con el servidor. Probá de nuevo en unos segundos.'; }
  b.disabled = false; c.value = ''; c.focus();
};
</script></body></html>"""


PAGINA_SOLO_LOCAL = """<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Administración · Transcripción</title>
<style>:root{color-scheme:light dark}body{margin:0;min-height:100vh;display:grid;place-items:center;
font:15px/1.5 "Segoe UI",system-ui,sans-serif;background:Canvas;color:CanvasText}
div{max-width:420px;padding:24px}h1{font-size:19px;margin:0 0 8px}a.volver{display:inline-block;margin-top:6px;font-weight:600;text-decoration:none;color:CanvasText;border:1px solid GrayText;border-radius:7px;padding:7px 14px}a.volver:hover{border-color:#1f5fbf}a.volver:focus-visible{outline:2px solid #1f5fbf;outline-offset:2px}</style></head>
<body><div><h1>Solo en la PC del servidor</h1><p>El panel de administración se abre únicamente en la PC donde
corre el servidor, en <b>http://127.0.0.1:8765/admin</b> (escribí exactamente esa dirección). Desde las PC del
trabajo se abre con el engranaje de la lista, si se habilitó con su contraseña.</p>
<p><a class="volver" href="/">Volver a los informes</a></p></div></body></html>"""


def anunciar_audio(nombre, cuerpo, desde):
    """Línea de «audio recibido» con duración, tamaño, médico y lugar en la cola."""
    L.contar("recibidos")
    dur = duracion_wav(datos=cuerpo)
    med = CASOS.medico_de(nombre)
    partes = [f"«{CASOS.titulo_de(nombre)}»", L.mmss(dur) if dur else None, L.tamano(len(cuerpo)),
              f"médico {med}" if med else "sin médico elegido"]
    pos = PROC.en_proceso()
    L.ok("AUDIO", f"Audio recibido {desde}: " + " · ".join(x for x in partes if x)
         + (f" · en cola ({pos} en proceso)" if pos > 1 else ""))


PAGINA_ENTRAR = """<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Entrar · Transcripción</title>
<style>:root{color-scheme:light;--bg:#f3f2ef;--p:#fbfbfa;--tx:#1d1d1b;--mu:#5c5b55;--bd:#cfcdc6;--ac:#1f5fbf;--err:#b3261e}
@media (prefers-color-scheme:dark){:root{color-scheme:dark;--bg:#141413;--p:#1b1b1a;--tx:#ebeae5;--mu:#a19f98;--bd:#45443f;--ac:#7aa7f0;--err:#ff8a80}}
body{margin:0;min-height:100vh;display:grid;place-items:center;background:var(--bg);color:var(--tx);font:15px/1.45 "Segoe UI",system-ui,sans-serif}
form{background:var(--p);border:1px solid var(--bd);border-radius:12px;padding:28px;width:min(360px,calc(100vw - 32px));box-sizing:border-box;display:flex;flex-direction:column;gap:14px}
h1{font-size:20px;margin:0}p{margin:0;color:var(--mu);font-size:13.5px}label{display:flex;flex-direction:column;gap:4px;font-weight:600}
input{font:inherit;font-weight:400;color:var(--tx);background:var(--bg);border:1px solid var(--bd);border-radius:7px;padding:8px 10px}
button{font:inherit;font-weight:600;background:var(--ac);color:#fff;border:0;border-radius:7px;padding:9px}.err{color:var(--err);font-weight:600}</style>
</head><body><form method="post" action="{{accion}}"><h1>Transcripción</h1>
<p>{{texto}}</p>{{error}}
{{campos}}
<button>Entrar</button></form></body></html>"""


class HTunel(H):
    """Pedidos que entran por el puerto propio del túnel de Microsoft: siempre de las PC del trabajo."""
    es_puerto_tunel = True

    def _es_remoto(self):
        return True

    def _ip(self):
        xff = (self.headers.get("X-Forwarded-For") or "").split(",")[0].strip()
        return xff or self.headers.get("Cf-Connecting-Ip") or self.client_address[0]


class Servidor(ThreadingHTTPServer):
    daemon_threads = True

    def handle_error(self, request, client_address):
        """Una PC que corta la conexión a mitad de camino es normal: no ensuciar la ventana."""
        ex = sys.exc_info()[1]
        if isinstance(ex, (ConnectionError, TimeoutError, BrokenPipeError)):
            L.debug("SERVIDOR", f"Conexión cortada por el otro lado: {ex!r}")
        else:
            L.error("SERVIDOR", "Error atendiendo un pedido.", exc=True)


def placa_de_video():
    """(texto, tono) con memoria en uso, carga y temperatura de la placa, o None."""
    try:
        import subprocess
        r = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.used,memory.total,utilization.gpu,temperature.gpu",
                            "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=4,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        nombre, usada, total, uso, temp = [x.strip() for x in r.stdout.strip().splitlines()[0].split(",")]
        gb = lambda m: f"{int(m) / 1024:.1f}".replace(".", ",")
        nombre = nombre.replace("NVIDIA ", "").replace("GeForce ", "")
        # Algunos drivers informan la temperatura con decimales (p. ej. 51.12).
        tono = "aviso" if float(temp) >= 85 or int(usada) >= 0.97 * int(total) else None
        return f"{nombre} · memoria {gb(usada)} de {gb(total)} GB · uso {uso}% · {temp} °C", tono
    except Exception:
        return None


_PANEL = {"casos_t": 0, "casos": None, "gpu_t": 0, "gpu": None}


def filas_encabezado(url, tunel):
    """Lo que muestra el encabezado fijo; se llama cada segundo (lo pesado se refresca cada 3 s)."""
    ahora = time.time()
    if ahora - _PANEL["casos_t"] > 3:
        try:
            cs = VISTA.listar_casos()
            _PANEL["casos"] = {k: sum(1 for x in cs if x["estado"] == k) for k in ("listo", "nuevo", "error")}
        except Exception:
            pass
        _PANEL["casos_t"] = ahora
    if ahora - _PANEL["gpu_t"] > 3 and not SIMULAR:
        _PANEL["gpu"], _PANEL["gpu_t"] = placa_de_video(), ahora
    filas = [("Interfaz", url, None), ("Administración", f"{url}/admin (PC vinculadas, túnel, errores)", None)]
    if SIMULAR:
        filas.append(("Modo", "PRUEBA: Whisper y la IA están simulados", "aviso"))
    # acceso remoto
    if not tunel:
        filas.append(("Acceso remoto", f"apagado: solo esta PC (para el trabajo usá {P.script('iniciar_servidor')})", None))
    elif not R.configurado():
        filas.append(("Acceso remoto", f"falta la contraseña: ejecutá {P.script('configurar_acceso')}", "aviso"))
    elif R.URL_TUNEL.get("url") and R.URL_TUNEL.get("estado") == "activo":
        desde = R.URL_TUNEL.get("desde")
        filas.append(("Acceso remoto", f"túnel de {R.nombre_servicio(R.URL_TUNEL.get('servicio'))} activo"
                      + (f" desde hace {L.hace(ahora - desde)}" if desde else ""), "ok"))
    elif R.URL_TUNEL.get("estado") in ("sin sesion", "sin configurar", "sin devtunnel") or TUNEL["error"]:
        filas.append(("Acceso remoto", TUNEL["error"] or f"Microsoft Dev Tunnels no está listo: ejecutá "
                                                         f"{P.script('configurar_tunel')}", "error"))
    else:
        filas.append(("Acceso remoto", "túnel abriéndose o reconectando…", "aviso"))
    if tunel and R.configurado():      # en su propio renglón, para que la dirección entre entera
        filas.append(("Dirección", R.URL_TUNEL.get("url") or f"esperando a {R.nombre_servicio()}…", None))
    if tunel:
        activas = sorted((p, t) for p, t in VISTO.items() if ahora - t < 60)
        filas.append(("PC conectadas", ", ".join(p if ahora - t < 10 else f"{p} (hace {L.hace(ahora - t)})"
                                                 for p, t in activas) or "ninguna en este momento",
                      "ok" if activas else None))
    if tunel:
        try:
            t = A.texto_panel()
        except Exception:
            t = None
        if t:
            filas.append(("App del trabajo", t, None))
    # IA y Whisper
    gen = PROC.en_estado("generando")
    e = IA.ultimo["e"]
    if e == "caida":
        filas.append(("IA", "Ollama no responde: abrilo para poder generar informes", "error"))
    elif e == "sin_modelo":
        filas.append(("IA", f"Ollama no tiene el modelo {CFG['modelo_ia']}", "error"))
    else:
        filas.append(("IA", f"{CFG['modelo_ia']} · " + (f"armando el informe de «{CASOS.titulo_de(gen[0])}»" if gen
                                                       else "lista, esperando"), "ok"))
    tr = PROC.en_estado("transcribiendo")
    filas.append(("Whisper", f"{CFG['modelo_whisper']} · " + (f"transcribiendo «{CASOS.titulo_de(tr[0])}»" if tr
                                                              else "en espera (se carga cuando llega un audio)"),
                  "ok" if tr else None))
    g = _PANEL["gpu"]
    filas.append(("Placa de video", g[0] if g else ("simulada" if SIMULAR else "sin datos (nvidia-smi no responde)"),
                  g[1] if g else None))
    # casos
    k = _PANEL["casos"] or {}
    proc = PROC.en_proceso()
    partes = [f"{k.get('listo', 0)} para revisar", f"{k.get('nuevo', 0)} sin procesar", f"{proc} en proceso"]
    if k.get("error"):
        partes.append(f"{k['error']} con error")
    filas.append(("Casos", " · ".join(partes), "error" if k.get("error") else ("aviso" if k.get("nuevo") else None)))
    h = L.HOY
    filas.append(("Hoy", f"{L.plural(h['recibidos'], 'audio recibido', 'audios recibidos')} · "
                         f"{L.plural(h['generados'], 'informe', 'informes')} · "
                         f"{L.plural(h['guardados'], 'guardado')} · {L.plural(h['errores'], 'error', 'errores')}",
                  "aviso" if h["errores"] else None))
    filas.append(("Registro", f"{L.ruta_corta(L.CARPETA)}{os.sep} (un archivo por día + actividad.csv)", None))
    return filas


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    titulo = M.titulo_consola()          # antes de que el servidor cambie el título de la ventana
    configurar(ajustes.cargar(AQUI))
    ajustes.preparar_carpetas(AJUSTES)
    CON.preparar_conocimiento()
    L.configurar()
    srv = None
    for intento in range(6):             # al reiniciar desde el panel, Windows puede tardar un instante en soltar el puerto
        try:
            srv = Servidor(("127.0.0.1", PUERTO), H)
            break
        except OSError:
            if intento == 5:
                L.error("SERVIDOR", f"No se pudo abrir el puerto {PUERTO}: seguramente el servidor ya está abierto en "
                                    f"otra ventana. Usá esa ventana o cerrala y volvé a abrir esta.", exc=True)
                sys.exit(1)
            time.sleep(1)
    SRV["http"] = srv
    R.cargar_sesiones()
    try:
        TRAB.reanudar_cola()
    except Exception:
        L.error('COLA', 'No se pudo recuperar la cola. No se inicia procesamiento ni se aceptan audios; conservá la base y los archivos.', exc=True)
        srv.server_close()
        return 1
    M.empezar(titulo)
    url = f"http://127.0.0.1:{PUERTO}"
    tunel = "--tunel" in sys.argv
    TUNEL["modo"] = tunel
    e_ia = IA.estado_ia()
    IA.ultimo["e"] = e_ia
    IA.cache.update(t=time.time(), ok=e_ia != "caida")
    L.encabezado("TRANSCRIPCIÓN DE INFORMES  ·  SERVIDOR", f"versión {VERSION}",
                 lambda: filas_encabezado(url, tunel),
                 "Eventos · no cierres esta ventana · Ctrl+C apaga · historial completo en registros")
    L.estado(ia=e_ia == "ok", cola=0)
    PROC.cargar_tiempos()
    APRENDIZAJE.iniciar()
    threading.Thread(target=TRAB.trabajador, daemon=True, name="procesamiento").start()
    threading.Thread(target=IA.vigilar_ia, args=(e_ia,), daemon=True, name="vigilancia-ia").start()
    threading.Thread(target=VOCES.hilo_voces, daemon=True, name="voces").start()
    g = M.git_al_arrancar() or {}
    L.ok("SERVIDOR", f"Servidor iniciado en {url}" + ("" if e_ia == "ok" else " (sin IA hasta que se abra Ollama)")
         + (f" · código {g['commit']}" + (f" + {L.plural(len(g['sucios']), 'cambio')} sin commitear" if g.get("sucios") else "")
            if g.get("commit") else ""))
    if tunel:
        if not R.configurado():
            L.aviso("TÚNEL", f"Todavía no hay contraseña para el acceso remoto: ejecutá {P.script('configurar_acceso')}. "
                             "Por ahora el sistema funciona solo en esta PC.")
        else:
            abrir_tunel()
    if "--sin-navegador" not in sys.argv:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    if not P.ES_WINDOWS:     # Linux: "kill" o "systemctl stop" apagan en orden, igual que Ctrl+C
        import signal

        def _apagar(*_):
            raise KeyboardInterrupt
        signal.signal(signal.SIGTERM, _apagar)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    L.cerrar_encabezado()
    R.cerrar_tunel()
    if TUNEL["http"]:
        try:
            TUNEL["http"].shutdown()         # primero que deje de atender; si no, server_close tira WinError 10038
            TUNEL["http"].server_close()
        except Exception:
            pass
    try:
        srv.server_close()
    except Exception:
        pass
    h = L.HOY
    if SRV["salida"] == M.CODIGO_REINICIO:
        L.info("SERVIDOR", "Servidor cerrado para reiniciarse: se vuelve a abrir solo en esta misma ventana.")
        OPER._salir_para_reiniciar()
    L.info("SERVIDOR", f"Servidor apagado. Hoy: {L.plural(h['recibidos'], 'audio recibido', 'audios recibidos')}, "
                       f"{L.plural(h['generados'], 'informe generado', 'informes generados')}, "
                       f"{L.plural(h['guardados'], 'guardado')}, {L.plural(h['errores'], 'error', 'errores')}.")


if __name__ == "__main__":
    sys.exit(main() or 0)
