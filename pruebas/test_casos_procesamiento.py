"""Casos y Procesamiento como objetos (docs/refactor.md, etapa 5): una prueba arma los suyos con carpetas
temporales, sin importar el servidor ni reemplazar variables globales."""
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
import wave
from unittest.mock import patch

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from transcripcion.base import registro as L  # noqa: E402
from transcripcion.casos.repositorio import Casos, LOCAL  # noqa: E402
from transcripcion.procesamiento.estado import Procesamiento, Cancelado  # noqa: E402


def _wav(ruta, segundos):
    with wave.open(str(ruta), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000)
        w.writeframes(b"\x00\x00" * int(16000 * segundos))


class Base(unittest.TestCase):
    def setUp(self):
        (RAIZ / "respaldo").mkdir(exist_ok=True)
        tmp = tempfile.TemporaryDirectory(prefix="casos_", dir=RAIZ / "respaldo")
        self.addCleanup(tmp.cleanup)
        self.datos = Path(tmp.name) / "datos"
        self.nuevos = Path(tmp.name) / "nuevos"
        self.datos.mkdir()
        self.nuevos.mkdir()
        self.casos = Casos(self.datos, self.nuevos)
        for p in (patch.object(L, "estado"), patch.object(L, "info"), patch.object(L, "ok")):
            p.start()
            self.addCleanup(p.stop)


class CasosTest(Base):
    def test_archivos_del_caso(self):
        n = "PC-1_20261103-010000_ficticio"
        self.assertEqual(self.casos.titulo_de(n), n)
        self.assertEqual(self.casos.origen_de(n), LOCAL)
        self.assertEqual(self.casos.medico_de(n), "")
        (self.datos / f"{n}.original.txt").write_text("tmpABCD.wav", encoding="utf-8")
        (self.datos / f"{n}.origen.txt").write_text("info-01", encoding="utf-8")
        (self.datos / f"{n}.medico.txt").write_text("Dr. Ficticio", encoding="utf-8")
        self.assertEqual(self.casos.titulo_de(n), "tmpABCD")
        self.assertEqual(self.casos.visible(n), "«tmpABCD» (info-01)")
        self.assertEqual(self.casos.medico_de(n), "Dr. Ficticio")

    def test_audio_y_duracion(self):
        _wav(self.nuevos / "uno.wav", 2.5)
        self.assertEqual(self.casos.ruta_audio("uno"), self.nuevos / "uno.wav")
        self.assertIsNone(self.casos.ruta_audio("otro"))
        self.assertEqual(self.casos.duracion_de("uno"), 2.5)
        self.assertIsNone(self.casos.duracion_de("otro"))

    def test_tiempo_de_revision_acumulado_y_acotado(self):
        n = "caso"
        self.casos.sumar_revision(n, 30, "info-01")          # sin dictado todavía: no se anota
        self.assertIsNone(self.casos.revision_de(n))
        (self.datos / f"{n}.dictado.txt").write_text("dictado ficticio", encoding="utf-8")
        self.casos.sumar_revision(n, 30, "info-01")
        self.casos.sumar_revision(n, 12, "info-02")
        self.casos.sumar_revision(n, 99999, "info-02")       # más de lo que puede juntar un pedido: se ignora
        self.assertEqual(self.casos.revision_de(n), 42)

    def test_dos_instancias_no_comparten_cache(self):
        _wav(self.nuevos / "uno.wav", 1)
        self.assertEqual(self.casos.duracion_de("uno"), 1.0)
        otro = Casos(self.datos, self.nuevos)
        self.assertIsNot(otro.duraciones, self.casos.duraciones)


class ProcesamientoTest(Base):
    def setUp(self):
        super().setUp()
        self.proc = Procesamiento(self.casos)

    def test_encolar_estado_y_espera(self):
        self.assertTrue(self.proc.encolar("uno"))
        self.assertFalse(self.proc.encolar("uno"))            # ya está en proceso
        self.assertTrue(self.proc.encolar("dos"))
        self.assertEqual(self.proc.cola_pendiente(), ["uno", "dos"])
        self.assertEqual(self.proc.en_proceso(), 2)
        esperas = self.proc.esperas()
        self.assertEqual(esperas["uno"]["adelante"], 0)
        self.assertEqual(esperas["dos"]["adelante"], 1)
        self.assertGreater(esperas["dos"]["eta"], esperas["uno"]["eta"])
        self.proc.poner_estado("uno", "listo")
        self.assertEqual(self.proc.en_proceso(), 1)
        self.assertEqual(self.proc.en_estado("listo"), ["uno"])

    def test_borrado_mientras_espera_no_arranca(self):
        self.proc.encolar("uno")
        self.proc.borrados.add("uno")
        self.assertFalse(self.proc.empezar("uno", "transcribiendo"))

    def test_pausa_y_reanudacion_de_la_transcripcion(self):
        self.proc.encolar("uno")
        self.assertTrue(self.proc.empezar("uno", "transcribiendo"))
        self.assertEqual(self.proc.pausar("uno", "prueba")[1], 200)
        self.assertEqual(self.proc.pausar("uno", "prueba")[1], 409)          # ya pedida
        hilo = threading.Thread(target=self.proc.punto_de_pausa, args=("uno", 3.0, 10.0))
        hilo.start()
        for _ in range(100):
            if self.proc.estado["uno"]["estado"] == "en pausa":
                break
            time.sleep(0.02)
        self.assertEqual(self.proc.estado["uno"]["estado"], "en pausa")
        self.assertEqual(self.proc.trabajo["en_pausa"], "uno")
        self.assertEqual(self.proc.reanudar("uno", "prueba")[1], 200)
        hilo.join(5)
        self.assertFalse(hilo.is_alive())
        self.assertEqual(self.proc.estado["uno"]["estado"], "transcribiendo")
        self.assertIn("uno", self.proc.pausado_s)

    def test_borrar_en_pausa_cancela(self):
        self.proc.encolar("uno")
        self.proc.empezar("uno", "transcribiendo")
        self.proc.pausar("uno", "prueba")
        error = []

        def esperar():
            try:
                self.proc.punto_de_pausa("uno")
            except Cancelado:
                error.append("cancelado")
        hilo = threading.Thread(target=esperar)
        hilo.start()
        time.sleep(0.1)
        with self.proc.pausa_cv:
            self.proc.borrados.add("uno")
            self.proc.pausa_cv.notify_all()
        hilo.join(5)
        self.assertEqual(error, ["cancelado"])

    def test_tiempos_de_referencia(self):
        antes = dict(self.proc.tiempos)
        self.proc.anotar_tiempo(60, 12, 20)
        self.assertEqual(self.proc.tiempos["n"], antes["n"] + 1)
        self.assertNotEqual(self.proc.tiempos["ia"], antes["ia"])
        self.assertEqual(Procesamiento(self.casos).tiempos, antes)          # cada instancia empieza de cero


if __name__ == "__main__":
    unittest.main()
