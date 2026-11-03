# -*- coding: utf-8 -*-
"""
REGISTRO DEL SERVIDOR: lo que se ve en la ventana negra y lo que queda guardado.

En la ventana: una linea por evento, alineada en columnas
    22:14:05   OK     AUDIO     Audio recibido de info-01: «tmp7957.wav» · 0:23 · 412 KB
con la hora, el nivel (OK / INFO / AVISO / ERROR), el area (AUDIO, WHISPER, IA, INFORME,
ACCESO, CASO, TUNEL, CONFIG, SERVIDOR) y el mensaje. Colores si la consola los admite.
Los errores muestran una sola linea; el detalle tecnico va al archivo del dia.

Guardado en la carpeta  sistema\\registros\\  (no se borra nada solo):
    servidor_AAAA-MM-DD.log   todo lo que paso ese dia, con el detalle tecnico de los errores
    actividad.csv             una fila por informe generado, guardado o fallido (para Excel)

Uso:   import registro as L
       L.configurar()
       L.ok("AUDIO", "Audio recibido…")      L.info / L.aviso / L.error / L.debug
       L.error("IA", "No se pudo…", exc=True)   (guarda el traceback en el archivo)
"""
import csv
import logging
import os
import re
import shutil
import sys
import textwrap
import threading
import time
from pathlib import Path

AQUI = Path(__file__).resolve().parent
CARPETA = AQUI / "registros"

OK = 25
logging.addLevelName(OK, "OK")
log = logging.getLogger("transcripcion")
log.propagate = False
log.setLevel(logging.DEBUG)

NIVEL_TXT = {logging.DEBUG: "DEBUG", logging.INFO: "INFO", OK: "OK", logging.WARNING: "AVISO",
             logging.ERROR: "ERROR", logging.CRITICAL: "ERROR"}
COL_NIVEL = {logging.DEBUG: "2", logging.INFO: "36", OK: "1;32", logging.WARNING: "1;30;43",
             logging.ERROR: "1;97;41", logging.CRITICAL: "1;97;41"}
COL_AREA = {"AUDIO": "94", "WHISPER": "95", "IA": "96", "INFORME": "92", "ACCESO": "93",
            "CASO": "37", "TÚNEL": "34", "CONFIG": "37", "SERVIDOR": "97",
            "APP": "35", "VOZ": "36"}
DIAS = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")
ANCHO_AREA = 8
_COLOR = False
# RLock: un mismo hilo puede volver a entrar (p. ej. escribir el archivo desde dentro de la consola) sin trabarse
_lock = threading.RLock()


def _out():
    """La ventana real del servidor. Nunca sys.stdout: mientras se carga Whisper, sys.stdout apunta a
    SalidaAlRegistro (que a su vez escribe en el registro con _lock tomado) y escribir ahí desde la consola,
    el encabezado o el título trababa el registro entero y, con él, todos los pedidos (26/10/2026)."""
    return sys.__stdout__ or sys.stdout


# ------------------------------------------------------------------ colores
def _activar_colores():
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("FORZAR_COLOR"):
        return True
    try:
        if not _out().isatty():
            return False
    except Exception:
        return False
    if os.name == "nt":     # Windows 10/11: activar las secuencias de color de la consola
        try:
            import ctypes
            k = ctypes.windll.kernel32
            h = k.GetStdHandle(-11)
            modo = ctypes.c_uint32()
            if not k.GetConsoleMode(h, ctypes.byref(modo)):
                return False
            return bool(k.SetConsoleMode(h, modo.value | 0x0004))
        except Exception:
            return False
    return True


def c(codigo, texto):
    return f"\x1b[{codigo}m{texto}\x1b[0m" if _COLOR and codigo else texto


URL_RE = re.compile(r"https?://\S+")


def _resaltar(t):
    """«nombres» en negrita y direcciones web en negrita subrayada, para encontrarlas de un vistazo."""
    if not _COLOR:
        return t
    t = re.sub(r"«([^»]+)»", "\x1b[1m«\\1»\x1b[22m", t)
    return URL_RE.sub(lambda m: f"\x1b[1;4m{m.group(0)}\x1b[22;24m", t)


def cortar(texto, n):
    """Corta en renglones solo entre palabras: nunca parte una dirección web, una ruta ni un
    nombre con guiones (si no entra, pasa entera al renglón siguiente)."""
    return textwrap.wrap(texto, max(20, n), break_long_words=False, break_on_hyphens=False) or [""]


def ancho():
    return max(80, min(shutil.get_terminal_size((120, 30)).columns, 160))


def fecha_larga(t=None):
    t = time.localtime(t)
    return f"{DIAS[t.tm_wday]} {time.strftime('%d/%m/%Y', t)}"


def archivo_del_dia(t=None):
    return CARPETA / f"servidor_{time.strftime('%Y-%m-%d', time.localtime(t))}.log"


def ruta_corta(p):
    try:
        return str(Path(p).resolve().relative_to(AQUI))
    except ValueError:
        return str(p)


# ------------------------------------------------------------- manejadores
class Consola(logging.Handler):
    def __init__(self):
        super().__init__(logging.INFO)
        self.ultimo_dia = None

    def emit(self, r):
        try:
            nivel = NIVEL_TXT.get(r.levelno, r.levelname)
            area = getattr(r, "area", "SERVIDOR")
            dia = time.strftime("%Y-%m-%d", time.localtime(r.created))
            salida = []
            if self.ultimo_dia and dia != self.ultimo_dia:     # cambio de día con el servidor abierto
                txt = f" {fecha_larga(r.created)} "
                salida.append(c("2", "─" * 4 + txt + "─" * max(4, ancho() - 6 - len(txt))))
            self.ultimo_dia = dia
            hora = time.strftime("%H:%M:%S", time.localtime(r.created))
            pre = f" {c('2', hora)}  {c(COL_NIVEL.get(r.levelno), f' {nivel:<5} ')}  " \
                  f"{c(COL_AREA.get(area, '37'), f'{area:<{ANCHO_AREA}}')}  "
            sangria = " " * (1 + 8 + 2 + 7 + 2 + ANCHO_AREA + 2)
            msg = r.getMessage()
            if r.levelno >= logging.ERROR:
                cod_msg = "91"
            elif r.levelno == logging.WARNING:
                cod_msg = "33"
            else:
                cod_msg = None
            filas = cortar(msg, ancho() - len(sangria) - 1)
            salida.append(pre + c(cod_msg, _resaltar(filas[0])))
            salida += [sangria + c(cod_msg, _resaltar(f)) for f in filas[1:]]
            for d in getattr(r, "det", None) or []:
                if URL_RE.fullmatch(str(d)):      # una dirección sola: entera, en su renglón y resaltada
                    salida.append(sangria + "→ " + _resaltar(str(d)))
                    continue
                for i, f in enumerate(cortar(str(d), ancho() - len(sangria) - 3)):
                    salida.append(sangria + c("2", ("· " if i == 0 else "  ") + f))
            if r.exc_info and r.exc_info[1] is not None:
                ex = r.exc_info[1]
                if str(ex) not in msg:      # el motivo técnico, si el mensaje no lo dice ya
                    tec = f"{type(ex).__name__}: {ex}"
                    lim = ancho() - len(sangria) - 1
                    salida.append(sangria + c("2", tec if len(tec) <= lim else tec[:lim - 1] + "…"))
                salida.append(sangria + c("2", f"detalle técnico en {ruta_corta(archivo_del_dia(r.created))}"))
            with _lock:
                _out().write("\n".join(salida) + "\n")
                _out().flush()
        except Exception:
            self.handleError(r)


class ArchivoDiario(logging.Handler):
    """Un archivo por día (servidor_AAAA-MM-DD.log). Se abre y se cierra en cada línea:
    se puede abrir con el Bloc de notas mientras el servidor corre y no hay que rotar nada."""

    def __init__(self):
        super().__init__(logging.DEBUG)

    def emit(self, r):
        try:
            nivel = NIVEL_TXT.get(r.levelno, r.levelname)
            area = getattr(r, "area", "SERVIDOR")
            t = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(r.created))
            lineas = [f"{t}  {nivel:<5}  {area:<{ANCHO_AREA}}  {r.getMessage()}"]
            for d in getattr(r, "det", None) or []:
                lineas.append(" " * 31 + "· " + str(d))
            if r.exc_info and r.exc_info[1] is not None:
                import traceback
                tb = "".join(traceback.format_exception(*r.exc_info)).rstrip()
                lineas += ["    | " + x for x in tb.splitlines()]
            escribir_archivo("\n".join(lineas) + "\n", r.created)
        except Exception:
            self.handleError(r)


def escribir_archivo(texto, t=None):
    CARPETA.mkdir(exist_ok=True)
    with _lock:
        with open(archivo_del_dia(t), "a", encoding="utf-8") as f:
            f.write(texto)


# ------------------------------------------------------------- configurar
def configurar(consola=True, programa="servidor"):
    global _COLOR
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    if log.handlers:
        return
    _COLOR = consola and _activar_colores()
    log.addHandler(ArchivoDiario())
    if consola:
        log.addHandler(Consola())
    escribir_archivo("\n" + "=" * 100 + f"\n{time.strftime('%Y-%m-%d %H:%M:%S')}  INICIO  {programa}"
                     f" (pid {os.getpid()})\n" + "=" * 100 + "\n")

    def hilo_fallo(a):     # errores no previstos dentro de los hilos del servidor
        if issubclass(a.exc_type, SystemExit):
            return
        log.error(f"Error inesperado en el hilo «{a.thread.name if a.thread else '?'}»",
                  exc_info=(a.exc_type, a.exc_value, a.exc_traceback), extra={"area": "SERVIDOR"})
    threading.excepthook = hilo_fallo


def _ev(nivel, area, msg, det=None, exc=False):
    log.log(nivel, msg, exc_info=exc, extra={"area": area, "det": det}, stacklevel=3)


def debug(area, msg, det=None):
    _ev(logging.DEBUG, area, msg, det)


def info(area, msg, det=None):
    _ev(logging.INFO, area, msg, det)


def ok(area, msg, det=None):
    _ev(OK, area, msg, det)


def aviso(area, msg, det=None, exc=False):
    _ev(logging.WARNING, area, msg, det, exc)


def error(area, msg, det=None, exc=False):
    _ev(logging.ERROR, area, msg, det, exc)
    contar("errores")


_VISTOS = {}


def una_vez(clave, seg=600):
    """True la primera vez y después solo cada 'seg' segundos (para no repetir el mismo aviso)."""
    ahora = time.time()
    with _lock:
        if ahora - _VISTOS.get(clave, 0) < seg:
            return False
        _VISTOS[clave] = ahora
        return True


# --------------------------------------------------------- cartel de inicio
def cartel(titulo, derecha, filas, pie=None, archivo=True):
    """filas: (clave, valor, tono) con tono None / 'ok' / 'aviso' / 'error'.
    Se muestra en la ventana y se copia (sin colores) al archivo del día."""
    w = min(ancho() - 4, 96)
    sub = f"{fecha_larga()} · {time.strftime('%H:%M')}"
    out = [""]
    out.append("  " + c("36", "┌" + "─" * (w - 2) + "┐"))
    izq = f"  {titulo}"
    out.append("  " + c("36", "│") + c("1", izq) + " " * max(1, w - 2 - len(izq) - len(derecha) - 2)
               + c("2", derecha) + "  " + c("36", "│"))
    out.append("  " + c("36", "│") + c("2", f"  {sub}".ljust(w - 2)) + c("36", "│"))
    out.append("  " + c("36", "└" + "─" * (w - 2) + "┘"))
    plano = [f"{titulo}  {derecha}  ({sub})"]
    tonos = {"ok": "32", "aviso": "33", "error": "91"}
    marca = {"ok": "●", "aviso": "▲", "error": "■"}
    for clave, valor, tono in filas:
        m = c(tonos.get(tono, "2"), marca.get(tono, "·"))
        filas_v = cortar(str(valor), w - 22)
        out.append(f"   {m} {c('2', f'{clave:<16}')}{c(tonos.get(tono) if tono in ('aviso', 'error') else None, filas_v[0])}")
        out += [" " * 21 + f for f in filas_v[1:]]
        plano.append(f"    {clave:<16}{valor}")
    if pie:
        out.append("  " + c("2", "─" * w))
        for p in pie:
            out.append("   " + c("2", p))
    out.append("")
    with _lock:
        _out().write("\n".join(out) + "\n")
        _out().flush()
    if archivo:
        escribir_archivo("\n".join(plano) + "\n")


# ----------------------------------------------- encabezado fijo en tiempo real
TONO_COLOR = {"ok": "32", "aviso": "33", "error": "91"}
TONO_MARCA = {"ok": "●", "aviso": "▲", "error": "■"}


def hace(seg_):
    seg_ = int(seg_)
    if seg_ < 60:
        return f"{seg_} s"
    m = seg_ // 60
    if m < 60:
        return f"{m} min"
    h = m // 60
    if h < 24:
        return f"{h} h {m % 60} min"
    return f"{h // 24} d {h % 24} h"


def _linea(segs, w):
    """segs: [(texto, código de color)]. Devuelve (texto plano, texto con color) cortado a w columnas,
    para que el encabezado nunca salte de renglón."""
    plano, color, usado = [], [], 0
    for t, cod in segs:
        if usado + len(t) > w:
            t = t[:max(0, w - usado - 1)] + "…"
        plano.append(t)
        color.append(c(cod, t) if t else "")
        usado += len(t)
        if usado >= w:
            break
    return "".join(plano), "".join(color)


class Panel:
    """Encabezado que queda fijo arriba de la ventana y se redibuja cada segundo (reloj, placa de
    video, casos, IA...). Los eventos corren por debajo, en una "región de desplazamiento"."""

    def __init__(self, titulo, derecha, fn_filas, pie):
        self.titulo, self.derecha, self.fn, self.pie = titulo, derecha, fn_filas, pie
        self.inicio = time.time()
        self.previo, self.tam, self.region, self.vivo, self.primera = None, None, False, True, True

    def construir(self, filas, cols):
        w = min(cols - 4, 96)
        reloj = f"  {fecha_larga()} · {time.strftime('%H:%M:%S')} · encendido hace {hace(time.time() - self.inicio)}"
        izq = f"  {self.titulo}"
        hueco = max(1, w - 2 - len(izq) - len(self.derecha) - 2)
        L = [
            [("  ┌" + "─" * (w - 2) + "┐", "36")],
            [("  │", "36"), (izq, "1"), (" " * hueco, None), (self.derecha, "2"), ("  │", "36")],
            [("  │", "36"), (reloj.ljust(w - 2)[:w - 2], None), ("│", "36")],
            [("  └" + "─" * (w - 2) + "┘", "36")],
        ]
        for clave, valor, tono in filas:
            L.append([("   ", None), (TONO_MARCA.get(tono, "·"), TONO_COLOR.get(tono, "2")), (" ", None),
                      (f"{clave:<16}", "2"), (str(valor), TONO_COLOR.get(tono) if tono in ("aviso", "error") else None)])
        txt = f" {self.pie} "
        L.append([("  ──" + txt + "─" * max(2, w - 2 - len(txt)), "2")])
        return [_linea(s, cols - 1) for s in L]

    def dibujar(self):
        cols, filas_t = shutil.get_terminal_size((120, 30))
        lineas = self.construir(self.fn(), cols)
        alto = len(lineas)
        with _lock:
            if filas_t < alto + 6:          # ventana muy baja: sin encabezado fijo hasta que se agrande
                if self.region:
                    _out().write(f"\x1b[r\x1b[{filas_t};1H")
                    _out().flush()
                self.region, self.previo = False, None
                return
            nuevo = not self.region or (cols, filas_t) != self.tam or len(self.previo or []) != alto
            out = []
            if nuevo:     # fijar la región de eventos debajo del encabezado y dejar el cursor abajo
                out.append(f"\x1b[{alto + 1};{filas_t}r")
                self.previo = [None] * alto
            else:
                out.append("\x1b7")
            for i, (plano, color) in enumerate(lineas):
                if plano != self.previo[i]:
                    out.append(f"\x1b[{i + 1};1H\x1b[2K{color}")
            if self.primera:      # los eventos empiezan justo debajo del encabezado
                out.append(f"\x1b[{alto + 1};1H")
                self.primera = False
            else:
                out.append(f"\x1b[{filas_t};1H" if nuevo else "\x1b8")
            _out().write("".join(out))
            _out().flush()
            self.previo = [p for p, _ in lineas]
            self.tam, self.region = (cols, filas_t), True

    def bucle(self):
        while self.vivo:
            try:
                self.dibujar()
            except Exception:
                debug("SERVIDOR", "No pude dibujar el encabezado", det=[repr(sys.exc_info()[1])])
            time.sleep(1.02 - (time.time() % 1))      # justo después de cada cambio de segundo

    def cerrar(self):
        self.vivo = False
        with _lock:
            filas_t = shutil.get_terminal_size((120, 30)).lines
            _out().write(f"\x1b[r\x1b[?25h\x1b[{filas_t};1H\n")
            _out().flush()


_PANEL = None


def encabezado(titulo, derecha, fn_filas, pie):
    """Muestra el encabezado. Si la consola admite colores queda fijo arriba y se actualiza cada
    segundo; si no, se imprime una vez (como antes). En los dos casos se copia al archivo del día."""
    global _PANEL
    filas = fn_filas()
    escribir_archivo("\n".join([f"{titulo}  {derecha}  ({fecha_larga()} · {time.strftime('%H:%M')})"]
                               + [f"    {k:<16}{v}" for k, v, _ in filas]) + "\n")
    if not _COLOR or os.environ.get("SIN_ENCABEZADO_FIJO"):
        cartel(titulo, derecha, filas, pie=[pie], archivo=False)
        return
    with _lock:
        _out().write("\x1b[?25l\x1b[2J\x1b[3J\x1b[H")     # sin cursor parpadeando, pantalla limpia
        _out().flush()
    _PANEL = Panel(titulo, derecha, fn_filas, pie)
    _PANEL.dibujar()
    threading.Thread(target=_PANEL.bucle, daemon=True, name="encabezado").start()
    import atexit
    atexit.register(cerrar_encabezado)


def cerrar_encabezado():
    global _PANEL
    if _PANEL:
        _PANEL.cerrar()
        _PANEL = None


# ------------------------------------------------------ título de la ventana
_TITULO = {}
_ULTIMO = None


def estado(**campos):
    """Actualiza el título de la ventana: «Transcripción · Servidor · IA lista · 2 en cola…»."""
    with _lock:
        _TITULO.update(campos)
        d = dict(_TITULO)
    partes = ["Transcripción · Servidor (no cerrar)"]
    if "ia" in d:
        partes.append("IA lista" if d["ia"] else "IA NO DISPONIBLE")
    if d.get("cola"):
        partes.append(f"{d['cola']} en proceso")
    if d.get("pausa"):
        partes.append("transcripción EN PAUSA")
    if d.get("tunel"):
        partes.append(f"túnel {d['tunel']}")
    partes.append(f"hoy {HOY['generados']} informes, {HOY['guardados']} guardados")
    if HOY["errores"]:
        partes.append(f"{HOY['errores']} errores")
    texto = " · ".join(partes)
    global _ULTIMO
    if texto == _ULTIMO:
        return
    _ULTIMO = texto
    try:
        if os.name == "nt":
            import ctypes
            ctypes.windll.kernel32.SetConsoleTitleW(texto)
        elif _COLOR:
            _out().write(f"\x1b]0;{texto}\x07")
            _out().flush()
    except Exception:
        pass


# ------------------------------------------------------------ contadores
HOY = {"fecha": time.strftime("%Y-%m-%d"), "recibidos": 0, "generados": 0, "guardados": 0, "errores": 0}


def contar(clave, n=1):
    with _lock:
        hoy = time.strftime("%Y-%m-%d")
        if HOY["fecha"] != hoy:
            HOY.update(fecha=hoy, recibidos=0, generados=0, guardados=0, errores=0)
        HOY[clave] = HOY.get(clave, 0) + n


# ------------------------------------------------------- actividad.csv
COLUMNAS = ["fecha", "hora", "evento", "caso", "audio_original", "pc", "medico", "estudios", "duracion_audio_s",
            "whisper_s", "ia_s", "palabras_dictado", "marcas_rojas", "marcas_amarillas", "marcas_turquesa",
            "marcas_grises", "datos_faltantes", "partes_no_transcritas", "estudios_sin_plantilla",
            "porcentaje_corregido", "palabras_informe", "revision_s", "medico_voz", "voz_estado", "voz_puntaje",
            "detalle", "usuario"]
_COLUMNAS_OK = {"ok": False}      # ya se comprobó que el archivo tiene estas columnas


def _num(v):
    if isinstance(v, float):
        return f"{v:.1f}".replace(".", ",")      # coma decimal para el Excel en español
    return "" if v is None else str(v)


_PENDIENTES = []      # filas que no se pudieron anotar porque el CSV estaba abierto en Excel


def _migrar_columnas(f):
    """Si actividad.csv se creó con columnas de una versión anterior, lo reescribe con las de ahora
    (las filas viejas quedan con esas columnas vacías). Se escribe aparte y se reemplaza de una vez.
    Devuelve las columnas agregadas (o None si ya estaba bien)."""
    with open(f, encoding="utf-8-sig", newline="") as fh:
        filas = list(csv.reader(fh, delimiter=";"))
    if not filas or filas[0] == COLUMNAS:
        return None
    viejas = filas[0]
    tmp = f.with_name(f.name + ".nuevo")
    with open(tmp, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(COLUMNAS)
        for r in filas[1:]:
            d = dict(zip(viejas, r))
            w.writerow([d.get(k, "") for k in COLUMNAS])
    try:
        os.replace(tmp, f)
    except OSError:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise PermissionError("actividad.csv abierto")
    return [k for k in COLUMNAS if k not in viejas]


def actividad(evento, **campos):
    """Agrega una fila a registros\\actividad.csv (separado por ; para abrir con Excel).
    Si el archivo está abierto en Excel, la fila se guarda en memoria y se anota con la próxima."""
    fila = dict(campos, fecha=time.strftime("%Y-%m-%d"), hora=time.strftime("%H:%M:%S"), evento=evento)
    with _lock:
        _PENDIENTES.append([_num(fila.get(k)) for k in COLUMNAS])
    try:
        CARPETA.mkdir(exist_ok=True)
        f = CARPETA / "actividad.csv"
        with _lock:
            agregadas = None
            if not _COLUMNAS_OK["ok"] and f.exists():
                agregadas = _migrar_columnas(f)   # si está abierto en Excel tira PermissionError y la fila queda pendiente
            _COLUMNAS_OK["ok"] = True
            nuevo = not f.exists()
            with open(f, "a", newline="", encoding="utf-8-sig" if nuevo else "utf-8") as fh:
                w = csv.writer(fh, delimiter=";")
                if nuevo:
                    w.writerow(COLUMNAS)
                w.writerows(_PENDIENTES)
            _PENDIENTES.clear()
        if agregadas:
            info("SERVIDOR", "registros\\actividad.csv: se agregaron las columnas " + ", ".join(agregadas) + ".")
    except PermissionError:
        if una_vez("csv_abierto", 600):
            aviso("SERVIDOR", "No pude anotar en registros\\actividad.csv porque está abierto en Excel. "
                              "Las filas se guardan cuando lo cierres.")
    except Exception:
        debug("SERVIDOR", "No pude anotar en actividad.csv", det=[repr(sys.exc_info()[1])])


# ------------------------------------------------------------ utilidades
def seg(s):
    return "" if s is None else f"{s:.1f} s".replace(".", ",")


def mmss(t):
    return f"{int(t // 60)}:{int(t % 60):02d}"


def tamano(n):
    if n < 1024 * 1024:
        return f"{max(1, round(n / 1024))} KB"
    return f"{n / 1024 / 1024:.1f} MB".replace(".", ",")


def plural(n, uno, varios=None):
    return f"{n} {uno if n == 1 else (varios or uno + 's')}"


class SalidaAlRegistro:
    """Para envolver código que usa print (por ejemplo la carga de Whisper):
    lo que imprime queda en el archivo del día en vez de ensuciar la ventana."""

    def __init__(self, area):
        self.area, self.buf = area, ""
        self.hilo = threading.get_ident()      # solo se captura lo que imprime el hilo que la puso
        self.dentro = threading.local()

    def write(self, s):
        # redirect_stdout cambia sys.stdout para TODOS los hilos: lo que imprimen los demás va a la ventana
        if threading.get_ident() != self.hilo or getattr(self.dentro, "si", False):
            try:
                return _out().write(s)
            except Exception:
                return len(s)
        self.dentro.si = True
        try:
            self.buf += s
            while "\n" in self.buf:
                linea, self.buf = self.buf.split("\n", 1)
                if linea.strip():
                    debug(self.area, linea.strip())
        finally:
            self.dentro.si = False
        return len(s)

    def flush(self):
        pass
