"""Estado de la IA local (Ollama): si responde y tiene el modelo, la vigilancia periódica y la espera del
trabajador cuando la IA no está lista.

Viene de servidor.py (docs/refactor.md, etapa 6a). Lo crea servidor.configurar()."""
import os
import time

from transcripcion.base import registro as L
from transcripcion.ia import ollama as OLL



class EstadoIA:
    """Último estado visto de Ollama (`ultimo`, para el encabezado y el panel) y una caché de 5 s para la lista."""

    def __init__(self, cfg, simular, raiz, casos, proc):
        self.cfg = cfg
        self.simular = simular
        self.raiz = raiz
        self.casos = casos
        self.proc = proc
        self.ultimo = {"e": "ok"}  # último estado de Ollama visto (para el encabezado)
        self.cache = {"t": 0, "ok": False}

    def ia_simulada(self):
        """Pruebas: SIMULAR_SIN_IA=1 hace de cuenta que Ollama está cerrado hasta que exista el archivo _ia_vuelve."""
        if os.environ.get("SIMULAR_SIN_IA") == "1" and not (self.raiz / "_ia_vuelve").exists():
            return "caida"
        return "ok"

    def ia_lista(self):
        if self.simular:
            return self.ia_simulada() != "caida"
        if time.time() - self.cache["t"] > 5:
            self.cache.update(t=time.time(), ok=OLL.ollama_modelos() is not None)
        return self.cache["ok"]

    def modelo_presente(self, mods):
        m = self.cfg["modelo_ia"]
        return any(x == m or x == f"{m}:latest" or x.startswith(m + "-") for x in mods)

    def estado_ia(self):
        """'ok', 'caida' (Ollama no responde) o 'sin_modelo'."""
        if self.simular:
            return self.ia_simulada()
        mods = OLL.ollama_modelos()
        if mods is None:
            return "caida"
        return "ok" if self.modelo_presente(mods) else "sin_modelo"

    def vigilar_ia(self, previo):
        """Cada 20 s mira si Ollama responde; avisa solo cuando cambia."""
        while True:
            time.sleep(20)
            e = self.estado_ia()
            self.ultimo["e"] = e
            self.cache.update(t=time.time(), ok=e != "caida")
            if e == previo:
                continue
            if e == "ok":
                L.ok("IA", "Ollama responde de nuevo: la IA está lista.")
            elif e == "caida":
                L.aviso("IA", "Ollama dejó de responder. Abrí Ollama: sin él no se pueden generar informes "
                              "(los audios que lleguen quedan con error y se pueden volver a procesar).")
            else:
                L.aviso("IA", f"Ollama está abierto pero no tiene el modelo {self.cfg['modelo_ia']}.")
            L.estado(ia=e == "ok")
            previo = e

    def esperar_ia(self, n, lote):
        """Si Ollama está cerrado (o sin el modelo), el audio ya transcrito espera en la cola en vez de
        terminar con error: se sigue solo cuando la IA vuelve. Revisa cada 5 s."""
        avisado = False
        while True:
            if n in self.proc.borrados:
                return  # el trabajador lo saltea; no esperar a Ollama por un caso eliminado
            e = self.estado_ia()
            if e == "ok":
                self.proc.trabajo["esperando_ia"] = False
                if avisado:
                    L.ok("IA", f"La IA volvió: sigo con {self.casos.visible(n)}.")
                return
            self.proc.trabajo["esperando_ia"] = True       # se puede reiniciar el servidor sin esperar (se retoma al volver)
            self.ultimo["e"] = e
            self.cache.update(t=time.time(), ok=e != "caida")
            motivo = "Ollama no responde" if e == "caida" else f"falta el modelo {self.cfg['modelo_ia']}"
            for x in lote:
                if x in self.proc.borrados:
                    continue
                if self.proc.estado.get(x, {}).get("estado") == "en cola" and not self.proc.estado[x].get("msg", "").startswith("Esperando a la IA ("):
                    self.proc.poner_estado(x, "en cola", f"Esperando a la IA ({motivo})…")
            if not avisado:
                L.aviso("IA", f"{self.casos.visible(n)} ya está transcrito, pero {motivo}: queda esperando en la cola y se "
                              f"termina solo cuando la IA esté lista.")
                avisado = True
            time.sleep(5)
