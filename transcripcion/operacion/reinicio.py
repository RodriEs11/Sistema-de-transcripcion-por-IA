"""Reinicio programado desde el panel (avisa, espera a que no haya trabajo en curso y vuelve a abrir el servidor) y
los mensajes que el panel muestra en la pantalla de todas las PC.

Viene de servidor.py (docs/refactor.md, etapa 6a). Lo crea servidor.configurar()."""
import json
import os
import sys
import threading
import time

from transcripcion.base import registro as L
from transcripcion.base.formatos import mmss
from transcripcion.base.persistencia import escribir_atomico
from transcripcion.casos.repositorio import LOCAL


TEXTO_REINICIO = ("Guardá lo que estés haciendo. El informe abierto se guarda solo; en un minuto el sistema "
                  "vuelve y la pantalla se reconecta sola.")


class Operacion:
    """Estado del reinicio (`reinicio`) y del cartel para las PC (`mensaje`), con sus candados. Usa `proc` para saber si
    hay trabajo en curso, guarda la cola en `cola_al_reiniciar` y apaga el servidor HTTP de `srv`. `tunel` y `fin_lock`
    son los del servidor (estado del túnel y candado de «Guardar Word»)."""

    def __init__(self, casos, proc, cola_al_reiniciar, tunel, srv, fin_lock, mantenimiento):
        self.casos = casos
        self.proc = proc
        self.cola_al_reiniciar = cola_al_reiniciar
        self.tunel = tunel
        self.srv = srv
        self.fin_lock = fin_lock
        self.mantenimiento = mantenimiento    # módulo mantenimiento: prueba del código nuevo, git, código de reinicio
        self.reinicio = {}  # reinicio programado desde el panel: id, cuando, estado (programado|esperando|reiniciando)...
        self.mensaje = {}  # cartel en la pantalla de todas las PC: id, texto, tipo, desde, hasta, por, reinicio
        self.msj_lock = threading.Lock()
        self.rei_lock = threading.Lock()

    def poner_mensaje(self, texto, minutos=0, tipo="info", por=None, reinicio=False):
        ahora = time.time()
        with self.msj_lock:
            self.mensaje.clear()
            self.mensaje.update(id=f"{int(ahora * 1000):x}", texto=texto, tipo=tipo, desde=ahora,
                           hasta=ahora + minutos * 60 if minutos else None, por=por or LOCAL, reinicio=reinicio)

    def quitar_mensaje(self, solo_reinicio=False):
        with self.msj_lock:
            if not self.mensaje or (solo_reinicio and not self.mensaje.get("reinicio")):
                return False
            self.mensaje.clear()
            return True

    def mensaje_actual(self):
        with self.msj_lock:
            if self.mensaje.get("hasta") and time.time() > self.mensaje["hasta"]:
                self.mensaje.clear()
            return dict(self.mensaje) if self.mensaje else None

    def mensaje_para_pcs(self):
        """Lo que ven las páginas de informes (va en /api/casos)."""
        m = self.mensaje_actual()
        if not m:
            return None
        out = {"id": m["id"], "texto": m["texto"], "tipo": m["tipo"], "ahora": time.time(), "reinicio": None}
        if m.get("reinicio"):
            with self.rei_lock:
                if self.reinicio:
                    out["reinicio"] = {"cuando": self.reinicio.get("cuando"), "estado": self.reinicio.get("estado")}
                    out["id"] = f"{m['id']}-{self.reinicio.get('estado')}"     # cambia de etapa: se vuelve a mostrar
        return out

    def estado_reinicio(self):
        with self.rei_lock:
            if not self.reinicio:
                return None
            r = {k: self.reinicio.get(k) for k in ("cuando", "estado", "por", "avisar", "pedido")}
        r["procesando"] = [self.casos.titulo_de(n) for n in self.proc.en_estado("transcribiendo") + self.proc.en_estado("generando")]
        r["en_cola"] = len(self.proc.cola_pendiente())
        return r

    def programar_reinicio(self, seg, avisar, texto, quien):
        """Programa el reinicio: avisa a las PC (si se pide), espera el tiempo elegido y además que no haya nada
        a medio procesar; antes prueba que el código nuevo arranque. Devuelve (respuesta, código)."""
        quien_txt = quien or LOCAL
        if self.reinicio.get("estado") == "reiniciando":
            return {"error": "El servidor ya se está reiniciando."}, 409
        ok, motivo = self.mantenimiento.soporta_reinicio(self.tunel["modo"])
        if not ok:
            return {"error": motivo}, 409
        try:
            seg = max(0, min(int(seg or 0), 3600))
        except (TypeError, ValueError):
            seg = 0
        texto = " ".join(str(texto or "").split())[:300] or TEXTO_REINICIO
        t0 = time.time()
        err = self.mantenimiento.prueba_de_arranque()
        if err:
            L.aviso("SERVIDOR", f"Reinicio pedido desde el panel ({quien_txt}) cancelado: el código de la carpeta tiene "
                                f"un error y el servidor no volvería a abrir.", det=err.splitlines()[-6:])
            return {"error": "No se reinicia: el código que está en la carpeta tiene un error y el servidor no volvería "
                             "a abrir. Corregilo y probá de nuevo.", "detalle": err}, 409
        with self.rei_lock:
            if self.reinicio.get("estado") == "reiniciando":
                return {"error": "El servidor ya se está reiniciando."}, 409
            rid = f"{int(time.time() * 1000):x}"
            self.reinicio.clear()
            self.reinicio.update(id=rid, cuando=time.time() + seg, pedido=time.time(), por=quien_txt, estado="programado",
                            detener=False, forzar=False, avisar=bool(avisar))
        if avisar:
            self.poner_mensaje(texto, tipo="aviso", por=quien, reinicio=True)
        else:
            self.quitar_mensaje(solo_reinicio=True)
        threading.Thread(target=self._hilo_reinicio, args=(rid,), daemon=True, name="reinicio").start()
        cambios = ", ".join(c["archivo"] for c in self.mantenimiento.cambios_sin_tomar()) or "sin cambios en el código"
        L.info("SERVIDOR", f"Reinicio del servidor programado desde el panel ({quien_txt}) "
                           + (f"para dentro de {L.seg(seg)}" if seg else "para ahora")
                           + (", con aviso a las PC" if avisar else "") + f". Toma: {cambios}. "
                           f"(el código nuevo se probó en {L.seg(time.time() - t0)})")
        if seg:
            msg = f"Reinicio programado: en {mmss(seg)} (y cuando termine lo que se esté procesando)."
        else:
            msg = "Reiniciando en cuanto termine lo que se esté procesando…"
        return {"ok": True, "msg": msg + (" Se avisó a las PC." if avisar else "")}, 200

    def cancelar_reinicio(self, quien):
        with self.rei_lock:
            if not self.reinicio:
                return {"error": "No hay ningún reinicio programado."}, 409
            if self.reinicio.get("estado") == "reiniciando":
                return {"error": "Ya se está reiniciando: no se puede cancelar."}, 409
            self.reinicio.clear()
        avisadas = self.quitar_mensaje(solo_reinicio=True)
        L.info("SERVIDOR", f"Reinicio del servidor cancelado desde el panel ({quien or LOCAL}).")
        return {"ok": True, "msg": "Reinicio cancelado." + (" Se quitó el aviso de las PC." if avisadas else "")}, 200

    def reiniciar_ya(self, quien):
        """Durante la espera: reiniciar sin esperar a que termine lo que se está procesando (se retoma al volver)."""
        with self.rei_lock:
            if not self.reinicio:
                return {"error": "No hay ningún reinicio programado."}, 409
            if self.reinicio.get("estado") == "reiniciando":
                return {"error": "Ya se está reiniciando."}, 409
            self.reinicio.update(forzar=True, cuando=min(self.reinicio["cuando"], time.time()))
        L.aviso("SERVIDOR", f"Reinicio sin esperar pedido desde el panel ({quien or LOCAL}): lo que se estaba procesando "
                            f"se vuelve a procesar al volver.")
        return {"ok": True, "msg": "Reiniciando ahora…"}, 200

    def _hilo_reinicio(self, rid):
        avisado = False
        while True:
            time.sleep(0.5)
            with self.rei_lock:
                if self.reinicio.get("id") != rid:
                    return                       # cancelado o vuelto a programar
                if time.time() < self.reinicio["cuando"]:
                    continue
                self.reinicio["detener"] = True       # el trabajador no empieza nada nuevo
                ocupado = self.proc.trabajo["ocupado"] and not self.proc.trabajo["esperando_ia"] and not self.proc.trabajo.get("en_pausa")
                if ocupado and not self.reinicio.get("forzar"):
                    self.reinicio["estado"] = "esperando"
                    if not avisado:
                        avisado = True
                        proc = ", ".join(f"«{self.casos.titulo_de(n)}»" for n in self.proc.en_estado("transcribiendo") + self.proc.en_estado("generando"))
                        L.info("SERVIDOR", "Reinicio: espero a que termine lo que se está procesando"
                                           + (f" ({proc})" if proc else "") + ".")
                    continue
                self.reinicio["estado"] = "reiniciando"
            self._reiniciar_ahora()
            return

    def _reiniciar_ahora(self):
        por = self.reinicio.get("por") or LOCAL
        self.fin_lock.acquire(timeout=60)             # que no quede un «Guardar Word» a medias (no se suelta: se cierra)
        pend = self.proc.cola_pendiente()
        pausados = [n for n in pend if self.proc.estado.get(n, {}).get("estado") == "en pausa"]
        pend = [n for n in pend if n not in pausados]
        for n in pausados:
            L.aviso("SERVIDOR", f"{self.casos.visible(n)} estaba en pausa: " + ('se conserva la pausa; usá Reanudar al volver.' if self.proc.duradera is not None
                    else 'queda sin procesar (botón Procesar en la lista cuando quieras).'))
        if self.proc.duradera is None:
            try:
                escribir_atomico(self.cola_al_reiniciar, json.dumps({"t": time.time(), "nombres": pend}, ensure_ascii=False))
            except OSError:
                L.error("SERVIDOR", "No se pudo anotar la cola antes de reiniciar.", exc=True)
        L.aviso("SERVIDOR", f"Reiniciando el servidor (pedido desde el panel, {por}) para tomar los cambios"
                            + (f"; {L.plural(len(pend), 'audio')} de la cola se retoman al volver." if pend else ".")
                            + " Las PC del trabajo se reconectan solas.")
        time.sleep(1.5)                          # que las páginas alcancen a ver «reiniciando»
        self.srv["salida"] = self.mantenimiento.CODIGO_REINICIO

        def _vigia():                            # si el cierre se traba, salir igual para que el .bat lo vuelva a abrir
            time.sleep(30)
            L.aviso("SERVIDOR", "El cierre para reiniciar se demoró más de 30 s: salgo igual para volver a abrir.")
            self._salir_para_reiniciar()
        threading.Thread(target=_vigia, daemon=True, name="vigia-reinicio").start()
        if self.srv["http"]:
            self.srv["http"].shutdown()

    def _salir_para_reiniciar(self):
        """Termina el proceso con el código de reinicio sin pasar por el cierre normal de Python.
        Con Whisper (CUDA/ctranslate2) y ONNX cargados, ese cierre en Windows puede colgarse o terminar con
        otro código, y entonces el .bat no lo vuelve a abrir."""
        for f in (sys.stdout, sys.stderr, sys.__stdout__, sys.__stderr__):
            try:
                f.flush()
            except Exception:
                pass
        os._exit(self.mantenimiento.CODIGO_REINICIO)

    def estado_mantenimiento(self):
        ok, motivo = self.mantenimiento.soporta_reinicio(self.tunel["modo"])
        return {"cambios": self.mantenimiento.cambios_sin_tomar(), "git": self.mantenimiento.info_git(), "git_inicio": self.mantenimiento.git_al_arrancar(),
                "reiniciable": ok, "motivo_no": motivo, "bat": self.mantenimiento.bat_del_modo(self.tunel["modo"]).name,
                "reinicio": self.estado_reinicio(), "mensaje": self.mensaje_actual()}
