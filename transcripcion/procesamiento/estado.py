"""Estado del procesamiento de audios en memoria: en qué etapa está cada caso, la cola de trabajo, las pausas
de la transcripción y los tiempos para estimar cuánto falta. La cola duradera (SQLite) vive en `duradera`.

Viene de servidor.py (docs/refactor.md, etapa 5). El servidor crea un `Procesamiento` en configurar(); una
prueba arma el suyo: `Procesamiento(casos)`."""

import csv
import io
import queue
import threading
import time

from transcripcion.base import registro as L
from transcripcion.base.formatos import mmss
from transcripcion.procesamiento import cola as CP

EN_PROCESO = ("en cola", "transcribiendo", "en pausa", "generando")


class Cancelado(Exception):
    """El caso se borró mientras estaba en pausa: el trabajador deja de transcribirlo y sigue con el próximo."""


class Procesamiento:
    """Todo el estado compartido entre el trabajador, las pantallas y el panel, con su candado. Los métodos
    son los únicos que cambian `estado`, `pausas` y la cola; el trabajador y las rutas HTTP los llaman."""

    def __init__(self, casos):
        self.casos = casos  # transcripcion.casos.repositorio.Casos (nombres para el registro, duraciones)
        self.estado = {}  # nombre -> {"estado":..., "msg":...}
        self.lock = threading.Lock()
        self.cola = queue.Queue()
        self.duradera = None  # se abre únicamente en main, después de reservar el puerto
        self.encolado = {}  # nombre -> cuándo entró a la cola (para el orden y la espera estimada)
        self.borrados = set()  # casos borrados mientras esperaban en la cola: el trabajador los saltea
        # Pausa de la transcripción (solo desde la PC del servidor). Whisper se detiene entre tramo y tramo y se queda
        # esperando con lo transcrito hasta ese momento; como todo se procesa de a uno, lo que sigue en la cola espera.
        self.pausas = {}  # nombre -> {"pedida": t, "por": dónde se pidió, "desde": t en que quedó detenida}
        self.pausa_cv = threading.Condition()
        self.pausado_s = {}  # nombre -> segundos que estuvo en pausa (no cuentan como tiempo de Whisper)
        # Tiempos de referencia para estimar cuánto falta. Arrancan con los de actividad.csv y se ajustan con cada
        # informe.
        self.tiempos = {"whisper_x": 0.15, "ia": 25.0, "n": 0}
        self.trabajo = {"ocupado": False, "esperando_ia": False, "desde": None, "en_pausa": None}
        self.encolar_lock = threading.Lock()

    def poner_estado(self, nombre, estado, msg=""):
        with self.lock:
            if nombre in self.borrados:
                return
            if self.duradera is not None and not self.duradera.cambiar(nombre, estado):
                return
            self.estado[nombre] = {"estado": estado, "msg": msg, "t": time.time()}
        L.estado(cola=self.en_proceso())

    def empezar(self, nombre, estado, msg=""):
        """Como poner_estado, pero no arranca la etapa si el caso se borró mientras esperaba en la cola."""
        with self.lock:
            if nombre in self.borrados:
                return False
            if self.duradera is not None and not self.duradera.cambiar(nombre, estado):
                return False
            self.estado[nombre] = {"estado": estado, "msg": msg, "t": time.time()}
        L.estado(cola=self.en_proceso())
        return True

    def en_proceso(self):
        with self.lock:
            return sum(1 for v in self.estado.values() if v.get("estado") in EN_PROCESO)

    def cola_pendiente(self):
        with self.lock:
            nombres = [n for n, v in self.estado.items() if v.get("estado") in EN_PROCESO and n not in self.borrados]
        return sorted(nombres, key=lambda n: self.encolado.get(n, 0))

    def esperas(self):
        """Para cada caso en proceso: desde cuándo está en esa etapa, cuántos tiene adelante y cuánto falta."""
        ahora = time.time()
        with self.lock:
            enp = {n: dict(v) for n, v in self.estado.items() if v.get("estado") in EN_PROCESO}
        orden = sorted(enp, key=lambda n: self.encolado.get(n, enp[n].get("t", 0)))
        out, acum = {}, 0.0
        for i, n in enumerate(orden):
            acum += self.trabajo_pendiente(n, enp[n], ahora)
            out[n] = {"desde": round(ahora - enp[n].get("t", ahora)), "adelante": i, "eta": round(acum)}
        return out

    def trabajo_pendiente(self, n, est, ahora):
        """Segundos de trabajo que le quedan a un caso en proceso (aproximado)."""
        dur = self.casos.duracion_de(n) or 60
        w, ia = self.tiempos["whisper_x"] * dur + 2, self.tiempos["ia"]
        desde = ahora - est.get("t", ahora)
        e, msg = est.get("estado"), est.get("msg", "")
        if e == "generando":
            return max(ia - desde, 3)
        if e == "transcribiendo":
            return max(w - desde, 2) + ia
        if e == "en pausa":
            return w + ia
        if e == "en cola" and msg.startswith("Esperando a la IA"):
            return ia
        return w + ia

    def cargar_tiempos(self):
        """Promedio de los últimos 30 informes generados (actividad.csv)."""
        try:
            f = L.CARPETA / "actividad.csv"
            filas = [
                r
                for r in csv.DictReader(io.StringIO(f.read_text(encoding="utf-8-sig")), delimiter=";")
                if r.get("evento") == "generado"
            ][-30:]
        except (OSError, csv.Error, UnicodeDecodeError):
            return

        def num(v):
            return float(v.replace(",", ".")) if v else None

        for r in filas:
            try:
                self.anotar_tiempo(num(r.get("duracion_audio_s")), num(r.get("whisper_s")), num(r.get("ia_s")))
            except ValueError:
                pass

    def anotar_tiempo(self, dur, whisper_s, ia_s):
        a = 0.3 if self.tiempos["n"] >= 3 else 1.0 / (self.tiempos["n"] + 1)  # promedio móvil
        if dur and whisper_s and dur > 1:
            self.tiempos["whisper_x"] += a * (whisper_s / dur - self.tiempos["whisper_x"])
        if ia_s:
            self.tiempos["ia"] += a * (ia_s - self.tiempos["ia"])
        self.tiempos["n"] += 1

    def encolar(self, nombre, forzar=False):
        with self.encolar_lock:
            with self.lock:
                if not forzar and self.estado.get(nombre, {}).get("estado") in EN_PROCESO:
                    return False
                if self.duradera is not None:
                    self.duradera.solicitar(nombre)
                self.borrados.discard(nombre)
            fila = self.duradera.obtener(nombre) if self.duradera is not None else None
            self.encolado[nombre] = fila["encolado"] if fila else time.time()
            self.casos.duraciones.pop(nombre, None)
            self.poner_estado(nombre, "en cola", "En cola…")
            if fila and fila["pausado"]:
                with self.pausa_cv:
                    self.pausas[nombre] = {"pedida": time.time(), "desde": time.time(), "por": "recuperación"}
            self.cola.put(nombre)
            return True

    def pausar(self, n, desde):
        """Pide la pausa de la transcripción en curso. Devuelve (respuesta, código)."""
        with self.lock:
            e = self.estado.get(n, {}).get("estado")
        if e == "en pausa" or n in self.pausas:
            return {"error": "Ya está en pausa."}, 409
        if e == "generando":
            return {
                "error": "Ya se transcribió y la IA está armando el informe: termina en unos segundos y esa parte "
                "no se puede pausar."
            }, 409
        if e == "en cola":
            return {"error": "Todavía no se está transcribiendo: la pausa es para la transcripción en curso."}, 409
        if e != "transcribiendo":
            return {"error": "Ese audio no se está transcribiendo."}, 409
        with self.pausa_cv:
            if self.duradera is not None and not self.duradera.pausa(n, True):
                return {"error": "El caso ya cambió de estado."}, 409
            self.pausas[n] = {"pedida": time.time(), "por": desde}
        with self.lock:
            if self.estado.get(n, {}).get("estado") == "transcribiendo":
                self.estado[n]["msg"] = "Pausando… (termina el tramo que está transcribiendo)"
        L.info(
            "WHISPER",
            f"Pausa de {self.casos.visible(n)} pedida desde {desde}: se detiene al terminar el tramo que está "
            f"transcribiendo.",
        )
        return {
            "ok": True,
            "msg": "Pausando: se detiene en unos segundos, al terminar el tramo que está transcribiendo. "
            "Lo ya transcrito se conserva.",
        }, 200

    def reanudar(self, n, desde):
        with self.pausa_cv:
            if n in self.pausas and self.duradera is not None:
                self.duradera.pausa(n, False)
            p = self.pausas.pop(n, None)
            if p:
                p["reanudo"] = desde  # el trabajador lo dice en el registro al seguir
            self.pausa_cv.notify_all()
        if not p:
            return {"error": "Ese audio no está en pausa."}, 409
        if not p.get("desde"):  # todavía no se había detenido: se cancela el pedido
            with self.lock:
                e = self.estado.get(n)
                if e and e.get("estado") == "transcribiendo" and (e.get("msg") or "").startswith("Pausando"):
                    e["msg"] = "Transcribiendo el audio…"
            L.info("WHISPER", f"Pausa de {self.casos.visible(n)} cancelada desde {desde} antes de que se detuviera.")
            return {"ok": True, "msg": "Pausa cancelada: sigue transcribiendo."}, 200
        return {"ok": True, "msg": "Reanudado: sigue transcribiendo desde donde quedó."}, 200

    def punto_de_pausa(self, n, pos=None, total=None):
        """Si se pidió pausar este caso, el trabajador se queda acá (Whisper conserva lo transcrito) hasta que se
        reanude. Si mientras tanto se borra el caso, corta con Cancelado."""
        with self.pausa_cv:
            p = self.pausas.get(n)
            if p:
                p["desde"] = time.time()
        if not p:
            return
        t0 = time.time()
        with self.lock:
            prev = dict(self.estado.get(n, {}))
            pos = pos if pos is not None else prev.get("pos")
            total = total or prev.get("total")
            donde = f"iba por {mmss(min(pos, total))} de {mmss(total)}" if pos is not None and total else ""
            self.estado[n] = {
                "estado": "en pausa",
                "msg": "En pausa" + (f" · {donde}" if donde else ""),
                "t": t0,
                "pos": pos,
                "total": total,
                "por": p.get("por"),
            }
        self.trabajo["en_pausa"] = n
        L.estado(cola=self.en_proceso(), pausa=1)
        espera = sum(1 for x in self.cola_pendiente() if x != n)
        L.info(
            "WHISPER",
            f"{self.casos.visible(n)} en pausa" + (f" ({donde})" if donde else "") + ". Whisper queda detenido con lo "
            "transcrito hasta ahora"
            + (f"; {L.plural(espera, 'audio')} de la cola espera" + ("" if espera == 1 else "n") if espera else "")
            + " hasta que se reanude.",
        )
        with self.pausa_cv:
            while n in self.pausas and n not in self.borrados:
                self.pausa_cv.wait(1.0)
        seg_ = time.time() - t0
        self.pausado_s[n] = self.pausado_s.get(n, 0) + seg_
        self.trabajo["en_pausa"] = None
        L.estado(pausa=0)
        if n in self.borrados:
            raise Cancelado()
        msg = prev.get("msg") or ""
        with self.lock:
            self.estado[n] = {
                "estado": "transcribiendo",
                "msg": "Transcribiendo el audio…" if msg.startswith("Pausando") else msg,
                "t": prev.get("t", t0) + seg_,
                "pos": pos,
                "total": total,
            }
        L.estado(cola=self.en_proceso())
        L.ok(
            "WHISPER",
            f"{self.casos.visible(n)} reanudado desde {p.get('reanudo') or 'la PC del servidor'} después de "
            f"{L.seg(seg_)} en pausa: sigue desde donde quedó.",
        )

    def avance(self, n, texto):
        """Función que Whisper llama después de cada tramo: muestra por dónde va y hace de punto de pausa."""

        def f(pos=None, total=None):
            if pos is not None and total and n not in self.pausas:
                with self.lock:
                    e = self.estado.get(n)
                    if e and e.get("estado") == "transcribiendo":
                        e.update(msg=f"{texto} · {mmss(min(pos, total))} de {mmss(total)}", pos=pos, total=total)
            self.punto_de_pausa(n, pos, total)

        return f

    def sincronizar_terminal(self, n):
        """Reconciliar una confirmación de disco cuya respuesta local pudo perderse."""
        if self.duradera is None:
            return False
        fila = self.duradera.obtener(n)
        if fila is None:
            raise CP.ErrorCola("No existe la tarea duradera.")
        e = fila["estado"]
        if e in CP.ACTIVOS:
            return False
        with self.lock:
            if e in ("borrando", "cancelado"):
                self.borrados.add(n)
            if e == "cancelado":
                self.estado.pop(n, None)
            else:
                self.estado[n] = {
                    "estado": "listo" if e == "listo" else "error",
                    "msg": "" if e == "listo" else "Revisar la tarea conservada antes de reintentar.",
                    "t": time.time(),
                }
        return True

    def en_estado(self, estado):
        with self.lock:
            return [n for n, v in self.estado.items() if v.get("estado") == estado]
