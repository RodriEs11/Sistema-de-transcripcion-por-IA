"""CRUD HTTP y concurrencia con médicos ficticios en un directorio temporal."""
import concurrent.futures
import http.client
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import servidor as S
from transcripcion.conocimiento import medicos as MED


class MedicosTest(unittest.TestCase):
    def setUp(self):
        respaldo = Path(__file__).resolve().parents[1] / "respaldo"
        respaldo.mkdir(exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(prefix="test_medicos_", dir=respaldo)
        if not Path(self.tmp.name).resolve().is_relative_to(respaldo.resolve()):
            raise RuntimeError("Las pruebas deben usar una carpeta dentro de respaldo/.")
        self.addCleanup(self.tmp.cleanup)
        self.parche = patch.object(MED, "DIR_MED", Path(self.tmp.name) / "medicos")
        self.parche.start()
        self.addCleanup(self.parche.stop)
        from transcripcion import ajustes
        aj = ajustes.para_pruebas(Path(self.tmp.name))     # las rutas usan el sistema configurado (S.SIS)
        ajustes.preparar_carpetas(aj)
        self.addCleanup(S.configurar, S.configurar(aj))
        self.http = S.ThreadingHTTPServer(("127.0.0.1", 0), S.H)
        self.addCleanup(self.http.server_close)
        self.port = self.http.server_port
        self.puerto = patch.object(S.SIS, "puerto", self.port)
        self.puerto.start()
        self.addCleanup(self.puerto.stop)
        hilo = threading.Thread(target=self.http.serve_forever, daemon=True)
        hilo.start()
        self.addCleanup(hilo.join, 2)
        self.addCleanup(self.http.shutdown)

    def pedir(self, ruta, datos=None, panel=True, extra=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        headers = {"Content-Type": "application/json"}
        if panel:
            headers["X-Panel"] = "1"
        headers.update(extra or {})
        c.request("GET" if datos is None else "POST", ruta,
                  None if datos is None else json.dumps(datos), headers)
        r = c.getresponse()
        cuerpo = r.read().decode("utf-8")
        estado = r.status
        c.close()
        return estado, json.loads(cuerpo) if cuerpo.startswith("{") else cuerpo

    def test_ciclo_completo_y_duplicados(self):
        self.assertEqual(self.pedir("/admin/medicos")[0], 200)
        self.assertEqual(self.pedir("/api/admin/medicos")[1]["medicos"], [])
        ruta = "/api/admin/medicos/"
        self.assertEqual(self.pedir(ruta + "agregar", {"nombre": "Dra. Pérez", "notas": "Nota ficticia"})[0], 200)
        for nombre in ("Dra. Pérez", "DRA. PEREZ", "  dra.   pérez  "):
            self.assertEqual(self.pedir(ruta + "agregar", {"nombre": nombre})[0], 409)
        self.assertEqual(MED.notas_medico("Dra. Pérez"), "Nota ficticia")
        self.assertEqual(self.pedir(ruta + "agregar", {"nombre": "Dr. Prueba"})[0], 200)
        self.assertEqual(self.pedir(ruta + "modificar", {"original": "Dr. Prueba", "nombre": "DRA. PEREZ"})[0], 409)
        self.assertEqual(self.pedir(ruta + "modificar", {"original": "Dra. Pérez", "nombre": "Dra. Ensayo", "notas": "Nueva nota"})[0], 200)
        self.assertNotIn("Dra. Pérez", MED.lista_medicos())
        self.assertEqual(MED.notas_medico("Dra. Ensayo"), "Nueva nota")
        self.assertEqual(self.pedir(ruta + "modificar", {"original": "Dra. Ensayo", "nombre": "DRA. ENSAYO"})[0], 200)
        self.assertEqual(self.pedir(ruta + "eliminar", {"original": "DRA. ENSAYO"})[0], 200)
        self.assertEqual(self.pedir(ruta + "eliminar", {"original": "DRA. ENSAYO"})[0], 404)

    def test_validacion_y_permisos(self):
        ruta = "/api/admin/medicos/agregar"
        for nombre in ("", "../escape", "CON", "A", "Doctor.", "123", "Dr/Prueba", None):
            self.assertEqual(self.pedir(ruta, {"nombre": nombre})[0], 400)
        self.assertEqual(self.pedir(ruta, {"nombre": "Dr. Prueba", "notas": []})[0], 400)
        self.assertEqual(self.pedir(ruta, {"nombre": "Dr. Prueba"}, panel=False)[0], 403)
        self.assertEqual(self.pedir(ruta, {"nombre": "Dr. Prueba"}, extra={"Origin": "https://ajeno.example"})[0], 403)
        self.assertEqual(self.pedir("/api/admin/medicos", extra={"Cf-Ray": "prueba"})[0], 401)
        self.assertEqual(MED.lista_medicos(), [])

    def test_alta_desde_revision_no_pisa_notas(self):
        MED.guardar_medico("Dr. Prueba", "Conservar", crear=True)
        self.assertEqual(self.pedir("/api/medico", {"medico": "Dr. Prueba", "notas": "", "crear": True})[0], 409)
        self.assertEqual(self.pedir("/api/medico", {"medico": "DR. PRUEBA", "notas": ""})[0], 409)
        self.assertEqual(MED.notas_medico("Dr. Prueba"), "Conservar")
        self.assertEqual(self.pedir("/api/medico", {"medico": "Dr. Prueba", "notas": "Edición"})[0], 200)

    def test_altas_simultaneas(self):
        def crear(_):
            try:
                MED.guardar_medico("Dr. Simulado", "Nota", crear=True)
                return "ok"
            except FileExistsError:
                return "duplicado"
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            resultados = list(pool.map(crear, range(8)))
        self.assertEqual(resultados.count("ok"), 1)
        self.assertEqual(resultados.count("duplicado"), 7)


if __name__ == "__main__":
    unittest.main()
