"""Persistencia de borradores exclusivamente con datos ficticios y fallos inyectados."""
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
from transcripcion.casos import borradores as B


class BorradoresTest(unittest.TestCase):
    def setUp(self):
        respaldo = Path(__file__).resolve().parents[1] / "respaldo"
        respaldo.mkdir(exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(prefix="borradores_", dir=respaldo)
        self.addCleanup(self.tmp.cleanup)
        self.carpeta = Path(self.tmp.name)

    def test_compatibilidad_y_omisiones_no_enviadas(self):
        (self.carpeta / "caso.borrador.html").write_text("Anterior", encoding="utf-8")
        (self.carpeta / "caso.omisiones_ok.json").write_text('["dato ficticio"]', encoding="utf-8")
        self.assertEqual(B.leer(self.carpeta, "caso")["html"], "Anterior")
        B.guardar(self.carpeta, "caso", {"html": "Nuevo"})
        self.assertEqual(B.leer(self.carpeta, "caso"), {"v": 1, "html": "Nuevo", "omisiones_ok": ["dato ficticio"], "revision": 1})

    def test_conflicto_y_reintento_tras_respuesta_perdida(self):
        d = {"html": "Primero", "revision": 0, "omisiones_ok": ["A"]}
        self.assertEqual(B.guardar(self.carpeta, "caso", d), 1)
        self.assertEqual(B.guardar(self.carpeta, "caso", d), 1)
        self.assertEqual(B.guardar(self.carpeta, "caso", dict(d, html="Segundo", revision=1)), 2)
        with self.assertRaises(B.Conflicto):
            B.guardar(self.carpeta, "caso", d)
        self.assertEqual(B.leer(self.carpeta, "caso")["html"], "Segundo")

    def test_fallo_replace_conserva_confirmado(self):
        B.guardar(self.carpeta, "caso", {"html": "Confirmado", "omisiones_ok": ["A"]})
        with patch.object(B.os, "replace", side_effect=PermissionError("fallo ficticio")):
            with self.assertRaises(PermissionError):
                B.guardar(self.carpeta, "caso", {"html": "No confirmado", "omisiones_ok": ["B"]})
        self.assertEqual(B.leer(self.carpeta, "caso")["html"], "Confirmado")
        self.assertEqual(B.leer(self.carpeta, "caso")["omisiones_ok"], ["A"])
        self.assertEqual(list(self.carpeta.glob("*.tmp")), [])

    def test_fallo_flush_no_publica(self):
        with patch.object(B.os, "fsync", side_effect=OSError("disco lleno ficticio")):
            with self.assertRaises(OSError):
                B.guardar(self.carpeta, "caso", {"html": "No confirmado"})
        self.assertIsNone(B.leer(self.carpeta, "caso")["html"])
        self.assertEqual(list(self.carpeta.iterdir()), [])

    def test_escrituras_concurrentes_no_mezclan_texto_y_omisiones(self):
        def guardar(i):
            B.guardar(self.carpeta, "caso", {"html": str(i), "omisiones_ok": [str(i)]})
            d = B.leer(self.carpeta, "caso")
            self.assertEqual(d["omisiones_ok"], [d["html"]])
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(guardar, range(30)))

    def test_validacion_no_destruye_borrador(self):
        B.guardar(self.carpeta, "caso", {"html": "Anterior"})
        for d in ({"html": None}, {"html": "X", "omisiones_ok": "incorrecto"}, {"html": "X", "omisiones_ok": [{}]}):
            with self.assertRaises(ValueError):
                B.guardar(self.carpeta, "caso", d)
        self.assertEqual(B.leer(self.carpeta, "caso")["html"], "Anterior")

    def test_archivo_corrupto_no_se_oculta_ni_se_pisa(self):
        f = self.carpeta / "caso.borrador.json"
        f.write_text("incompleto", encoding="utf-8")
        with self.assertRaises(B.Corrupto):
            B.guardar(self.carpeta, "caso", {"html": "Nuevo"})
        self.assertEqual(f.read_text(encoding="utf-8"), "incompleto")

    def test_json_valido_con_campos_corruptos_no_se_pisa(self):
        f = self.carpeta / 'caso.borrador.json'
        correcto = {'v': 1, 'html': '', 'omisiones_ok': [], 'revision': 1}
        for cambio in ({'html': None}, {'omisiones_ok': {}}, {'omisiones_ok': [3]}, {'revision': True},
                       {'revision': -1}, {'v': True}, {'v': 2}):
            with self.subTest(cambio=cambio):
                contenido = json.dumps(dict(correcto, **cambio)); f.write_text(contenido, encoding='utf-8')
                with self.assertRaises(B.Corrupto): B.guardar(self.carpeta, 'caso', {'html': 'Nuevo'})
                self.assertEqual(f.read_text(encoding='utf-8'), contenido)

    def test_vacio_persiste_y_falta_de_contenido_no_lo_reemplaza(self):
        B.guardar(self.carpeta, 'caso', {'html': '', 'omisiones_ok': [], 'revision': 0})
        self.assertEqual(B.leer(self.carpeta, 'caso')['html'], '')
        with self.assertRaises(ValueError): B.guardar(self.carpeta, 'caso', {'revision': 1})
        self.assertEqual(B.leer(self.carpeta, 'caso')['revision'], 1)

    def test_omisiones_anteriores_corruptas_no_se_ocultan(self):
        f = self.carpeta / 'caso.omisiones_ok.json'; f.write_text('{}',encoding='utf-8')
        with self.assertRaises(B.Corrupto): B.guardar(self.carpeta, 'caso', {'html': 'Nuevo'})
        self.assertFalse((self.carpeta / 'caso.borrador.json').exists())


class BorradoresHttpTest(unittest.TestCase):
    def setUp(self):
        import servidor as S
        self.S = S
        respaldo = Path(__file__).resolve().parents[1] / "respaldo"
        respaldo.mkdir(exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(prefix="borradores_http_", dir=respaldo)
        self.addCleanup(self.tmp.cleanup)
        self.carpeta = Path(self.tmp.name)
        self.parche = patch.object(S, "DATOS", self.carpeta)
        self.parche.start()
        self.addCleanup(self.parche.stop)
        self.http = S.ThreadingHTTPServer(("127.0.0.1", 0), S.H)
        self.addCleanup(self.http.server_close)
        self.puerto = patch.object(S, "PUERTO", self.http.server_port)
        self.puerto.start()
        self.addCleanup(self.puerto.stop)
        hilo = threading.Thread(target=self.http.serve_forever, daemon=True)
        hilo.start()
        self.addCleanup(hilo.join, 2)
        self.addCleanup(self.http.shutdown)

    def pedir(self, datos):
        c = http.client.HTTPConnection("127.0.0.1", self.http.server_port, timeout=5)
        try:
            c.request("POST", "/api/borrador", json.dumps(dict(nombre="caso-ficticio", **datos)), {"Content-Type": "application/json"})
            r = c.getresponse()
            return r.status, json.loads(r.read())
        finally:
            c.close()

    def test_contrato_revision_y_cliente_anterior(self):
        self.assertEqual(self.pedir({"html": "Uno", "omisiones_ok": ["Dato"], "revision": 0}), (200, {"ok": True, "revision": 1}))
        self.assertEqual(self.pedir({"html": "Viejo", "revision": 0})[0], 409)
        # Un cliente anterior sin revisión conserva contrato y omisiones.
        self.assertEqual(self.pedir({"html": "Cliente anterior"})[0], 200)
        self.assertEqual(B.leer(self.carpeta, "caso-ficticio")["omisiones_ok"], ["Dato"])

    def test_error_de_disco_no_confirma(self):
        with patch.object(B.os, "replace", side_effect=OSError("disco ficticio lleno")):
            estado, d = self.pedir({"html": "Sin confirmar"})
        self.assertEqual(estado, 503)
        self.assertNotIn("ok", d)
        self.assertIsNone(B.leer(self.carpeta, "caso-ficticio")["html"])

    def test_permiso_y_validacion(self):
        self.assertEqual(self.pedir({"html": {}})[0], 400)
        with patch.object(self.S.R, "bloqueado_por", return_value="Otra PC"):
            self.assertEqual(self.pedir({"html": "No autorizado"})[0], 409)
        self.assertIsNone(B.leer(self.carpeta, "caso-ficticio")["html"])

    def test_corrupto_devuelve_error_recuperable_sin_confirmar(self):
        (self.carpeta / 'caso-ficticio.borrador.json').write_text('{}',encoding='utf-8')
        estado, d = self.pedir({'html':'No reemplazar'})
        self.assertEqual(estado,503); self.assertNotIn('ok',d)
        with patch.object(self.S,'cargar_caso',side_effect=B.Corrupto('Fallo ficticio')):
            c = http.client.HTTPConnection('127.0.0.1',self.http.server_port,timeout=5)
            try:
                c.request('GET','/api/caso?nombre=caso-ficticio'); r=c.getresponse()
                self.assertEqual(r.status,503); self.assertIn('recuperación',json.loads(r.read())['error'])
            finally:c.close()


if __name__ == "__main__":
    unittest.main()
