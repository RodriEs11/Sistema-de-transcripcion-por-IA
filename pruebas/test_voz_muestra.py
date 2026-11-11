"""Muestra de voz al elegir el médico a mano (#51), solo con huellas y casos ficticios."""

import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from transcripcion.http import edicion
from transcripcion.informe.guardado import Guardado
from transcripcion.voz import huellas as VOZ
from transcripcion.voz.servicio import ServicioVoz

H = [0.0625] * 256  # huella ficticia


class Casos:
    """Lo mínimo del repositorio de casos que usa ServicioVoz, sobre una carpeta temporal."""

    def __init__(self, datos):
        self.datos = datos
        self.voz_cache = {}
        self.voz_lock = threading.Lock()

    def voz_de(self, n):
        try:
            return json.loads((self.datos / f"{n}.voz.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def guardar_voz(self, n, v):
        (self.datos / f"{n}.voz.json").write_text(json.dumps(v), encoding="utf-8")
        self.voz_cache.pop(n, None)

    def anotar_voz(self, n, **campos):
        v = self.voz_de(n)
        if v is not None:
            v.update(campos)
            self.guardar_voz(n, v)

    def medico_de(self, n):
        f = self.datos / f"{n}.medico.txt"
        return f.read_text(encoding="utf-8").strip() if f.exists() else ""

    def visible(self, n):
        return n


class Base(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        raiz = Path(tmp.name)
        self.datos = raiz / "datos"
        self.datos.mkdir()
        for nombre, valor in (("DIR_VOCES", raiz / "voces"), ("HUELLAS", raiz / "voces" / "huellas.json")):
            p = patch.object(VOZ, nombre, valor)
            p.start()
            self.addCleanup(p.stop)
        VOZ._CACHE.update(mt=None, d=None)
        self.addCleanup(VOZ._CACHE.update, mt=None, d=None)
        for nombre in ("aviso", "info", "ok", "debug"):
            p = patch(f"transcripcion.voz.servicio.L.{nombre}")
            setattr(self, nombre, p.start())
            self.addCleanup(p.stop)
        listo = patch.object(VOZ, "modelo_listo", return_value=True)
        self.modelo_listo = listo.start()
        self.addCleanup(listo.stop)
        self.casos = Casos(self.datos)
        self.voces = ServicioVoz({}, self.casos, SimpleNamespace(lock=threading.Lock(), estado={}))

    def voz(self, n, h=H, seg=12.0, modelo=VOZ.VERSION_HUELLA, por=""):
        self.casos.guardar_voz(
            n, {"v": 1, "modelo": modelo, "h": h, "seg": seg, "det": {"estado": "sin"}, "medico_por": por}
        )

    def medico(self, n, med):
        (self.datos / f"{n}.medico.txt").write_text(med, encoding="utf-8")


class MuestraPosibleTest(Base):
    def test_con_huella_se_puede(self):
        self.voz("caso")
        self.assertEqual(self.voces.muestra_posible("caso"), (True, ""))

    def test_motivos_cuando_no_se_puede(self):
        casos = {
            "corto": dict(h=None, seg=1.2),
            "sin_huella": dict(h=None, seg=8.0),
            "viejo": dict(modelo="otro-modelo"),
        }
        for n, kw in casos.items():
            self.voz(n, **kw)
        self.assertIn("muy poca voz (1.2 s)", self.voces.muestra_posible("corto")[1])
        self.assertIn("no se pudo sacar la huella", self.voces.muestra_posible("sin_huella")[1])
        self.assertIn("modelo anterior", self.voces.muestra_posible("viejo")[1])
        self.assertIn("todavía no tiene huella", self.voces.muestra_posible("sin_voz_json")[1])
        self.modelo_listo.return_value = False
        self.assertIn("no está listo", self.voces.muestra_posible("sin_voz_json")[1])
        for n in (*casos, "sin_voz_json"):
            self.assertFalse(self.voces.muestra_posible(n)[0], n)

    def test_resumen_de_la_barra_lo_informa(self):
        self.voz("bien")
        self.voz("corto", h=None, seg=1.0)
        self.assertTrue(self.voces.resumen_voz("bien")["muestra_posible"])
        r = self.voces.resumen_voz("corto")
        self.assertFalse(r["muestra_posible"])
        self.assertIn("muy poca voz", r["motivo_muestra"])


class RegistrarMuestraTest(Base):
    def test_al_guardar_con_medico_elegido_a_mano_queda_la_muestra(self):
        self.voz("caso", por="usuaria")
        self.medico("caso", "Dra. Ficticia")
        self.assertTrue(self.voces.muestra_al_guardar("caso"))
        self.assertEqual(VOZ.muestra("caso")["medico"], "Dra. Ficticia")
        self.assertEqual(len(VOZ.muestras("Dra. Ficticia")), 1)

    def test_si_no_se_puede_lo_anota_con_el_motivo(self):
        self.voz("caso", h=None, seg=0.8)
        self.medico("caso", "Dra. Ficticia")
        self.assertFalse(self.voces.muestra_al_guardar("caso"))
        self.assertIsNone(VOZ.muestra("caso"))
        self.aviso.assert_called_once()
        self.assertIn("muy poca voz", self.aviso.call_args[0][1])

    def test_sin_voz_json_tambien_avisa(self):
        self.medico("caso", "Dra. Ficticia")
        self.assertFalse(self.voces.muestra_al_guardar("caso"))
        self.aviso.assert_called_once()

    def test_cambiar_medico_de_un_guardado_corrige_o_quita(self):
        self.voz("caso")
        self.assertTrue(self.voces.actualizar_muestra("caso", "Dr. Uno"))
        self.assertTrue(self.voces.actualizar_muestra("caso", "Dr. Dos"))
        self.assertEqual(VOZ.muestra("caso")["medico"], "Dr. Dos")
        self.assertFalse(self.voces.actualizar_muestra("caso", ""))
        self.assertIsNone(VOZ.muestra("caso"))

    def test_reprocesar_respeta_el_medico_elegido_a_mano(self):
        self.voz("caso", por="usuaria")
        self.medico("caso", "Dra. Ficticia")
        det = {"estado": "seguro", "medico": "Dr. Otro", "puntaje": 0.9, "muestras": 5}
        with (
            patch.object(VOZ, "huella_archivo", return_value=(H, 15.0)),
            patch.object(VOZ, "detectar", return_value=det),
        ):
            self.voces.calcular_voz("caso", Path("ficticio.wav"), [])
        self.assertEqual(self.casos.medico_de("caso"), "Dra. Ficticia")
        self.assertEqual(self.casos.voz_de("caso")["medico_por"], "usuaria")


class GuardadoTest(Base):
    def test_finalizar_registra_la_muestra_sin_esperar_la_cola(self):
        for suf, txt in ((".informe_ia.txt", "Informe ficticio."), (".dictado.txt", "dictado ficticio")):
            (self.datos / f"caso{suf}").write_text(txt, encoding="utf-8")
        self.voz("caso", por="usuaria")
        self.medico("caso", "Dra. Ficticia")
        self.casos.formato_de = lambda n: None
        self.casos.revision_de = lambda n: None
        self.casos.datos_csv = lambda n: {}
        informes = self.datos.parent / "informes"
        informes.mkdir()
        g = Guardado({}, informes, self.casos, self.voces, threading.Lock(), MagicMock(), MagicMock())
        g.aprender.pct_corregido.return_value = 0.0
        g.aprendizaje = MagicMock()  # la cola no se procesa: la muestra no puede depender de ella
        with (
            patch("transcripcion.informe.guardado.escribir_docx"),
            patch("transcripcion.informe.guardado.U.cfg_de", return_value={}),
            patch("transcripcion.informe.guardado.L"),
        ):
            g.finalizar("caso", "Informe ficticio corregido.")
        g.aprendizaje.agregar.assert_called_once()
        self.assertEqual(VOZ.muestra("caso")["medico"], "Dra. Ficticia")


class EndpointMedicoTest(Base):
    def pedir(self, n, med):
        h = SimpleNamespace(sis=SimpleNamespace(datos=self.datos, casos=self.casos, voces=self.voces), pc="PC1")
        h._json = lambda d: d
        with patch("transcripcion.http.edicion.L"):
            return edicion.medico(h, SimpleNamespace(datos={"medico": med}, nombre=n))

    def test_informa_si_la_muestra_se_va_a_poder_registrar(self):
        self.voz("bien")
        self.voz("corto", h=None, seg=1.0)
        self.assertTrue(self.pedir("bien", "Dra. Ficticia")["muestra"]["posible"])
        m = self.pedir("corto", "Dra. Ficticia")["muestra"]
        self.assertFalse(m["posible"])
        self.assertIn("muy poca voz", m["motivo"])
        self.assertFalse(self.pedir("sin_voz_json", "Dra. Ficticia")["muestra"]["posible"])

    def test_en_un_guardado_la_registra_al_momento(self):
        self.voz("caso")
        (self.datos / "caso.final.txt").write_text("Informe ficticio.", encoding="utf-8")
        m = self.pedir("caso", "Dra. Ficticia")["muestra"]
        self.assertTrue(m["guardado"] and m["registrada"])
        self.assertEqual(VOZ.muestra("caso")["medico"], "Dra. Ficticia")


if __name__ == "__main__":
    unittest.main()
