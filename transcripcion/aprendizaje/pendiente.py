"""Cola duradera: una última versión por caso, un consumidor y reintentos idempotentes."""
import json
import threading
import uuid
from pathlib import Path
from persistencia import escribir_atomico
import registro as L


class ColaAprendizaje:
    def __init__(self, carpeta, aplicar, analizar):
        self.carpeta = Path(carpeta)
        self.aplicar = aplicar
        self.analizar = analizar
        self.lock = threading.Lock()
        self.despertar = threading.Event()
        self.hilo = None

    def agregar(self, datos):
        # El nombre del caso ya fue validado por la API; no almacenar rutas arbitrarias.
        nombre = datos["nombre"]
        if not nombre or any(c in nombre for c in ("/", "\\")) or ".." in nombre:
            raise ValueError("Nombre de caso inválido")
        with self.lock:
            self.carpeta.mkdir(parents=True, exist_ok=True)
            tarea = dict(datos, v=1, id=uuid.uuid4().hex)
            escribir_atomico(self.carpeta / (nombre + ".json"), json.dumps(tarea, ensure_ascii=False))
        self.despertar.set()

    def procesar(self):
        """Una pasada comprobable sin iniciar hilos. Un fallo no elimina tareas."""
        if not self.carpeta.exists():
            return
        marcador = self.carpeta / "_recalcular"
        for ruta in sorted(self.carpeta.glob("*.json")):
            try:
                with self.lock:
                    tarea = json.loads(ruta.read_text(encoding="utf-8"))
                if tarea.get("v") != 1:
                    raise ValueError("Versión de tarea de aprendizaje desconocida")
                self.aplicar(tarea)
                with self.lock:
                    # Si se guardó una versión nueva durante el trabajo, queda pendiente.
                    escribir_atomico(marcador, "1")
                    actual = json.loads(ruta.read_text(encoding="utf-8"))
                    if actual["id"] == tarea["id"]:
                        ruta.unlink()
            except Exception:
                L.error("APRENDIZAJE", "No se pudo completar una tarea; queda conservada para reintento.", exc=True)
        if marcador.exists():
            try:
                self.analizar()
                marcador.unlink()
            except Exception:
                L.error("APRENDIZAJE", "No se pudieron actualizar las correcciones; se reintentará.", exc=True)

    def iniciar(self):
        if self.hilo is not None:
            return
        def bucle():
            while True:
                self.despertar.clear()
                try:
                    self.procesar()
                except Exception:
                    L.error("APRENDIZAJE", "La cola conserva las tareas y volverá a intentar.", exc=True)
                self.despertar.wait(30)
        self.hilo = threading.Thread(target=bucle, daemon=True, name="aprendizaje")
        self.hilo.start()
