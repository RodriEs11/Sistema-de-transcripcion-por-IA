"""Regresión de telemetría NVIDIA, sin importar ni iniciar el servidor."""
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from transcripcion.operacion import gpu  # noqa: E402


def cargar_lector():
    return gpu.placa_de_video


class PlacaVideoTest(unittest.TestCase):
    def setUp(self):
        self.leer = cargar_lector()

    def test_temperaturas_y_alertas(self):
        for temperatura, usada, tono in [
            ("51.12", "1449", None), ("51", "1449", None),
            ("84.99", "1449", None), ("85.00", "1449", "aviso"),
            ("85", "1449", "aviso"), ("51.12", "10000", "aviso"),
        ]:
            with self.subTest(temperatura=temperatura, usada=usada):
                salida = f"NVIDIA GeForce RTX 3080, {usada}, 10240, 35, {temperatura}\n"
                with patch("subprocess.run", return_value=Mock(stdout=salida)):
                    texto, aviso = self.leer()
                self.assertIn("RTX 3080", texto)
                self.assertIn("de 10,0 GB", texto)
                self.assertIn("uso 35%", texto)
                self.assertIn(f"{temperatura} °C", texto)
                self.assertEqual(aviso, tono)

    def test_salida_invalida(self):
        for salida in ("", "Error del controlador", "GPU, N/A, N/A, N/A, N/A"):
            with self.subTest(salida=salida), patch("subprocess.run", return_value=Mock(stdout=salida)):
                self.assertIsNone(self.leer())

    def test_comando_ausente_o_sin_respuesta(self):
        for error in (FileNotFoundError(), subprocess.TimeoutExpired("nvidia-smi", 4)):
            with self.subTest(error=type(error).__name__), patch("subprocess.run", side_effect=error):
                self.assertIsNone(self.leer())


if __name__ == "__main__":
    unittest.main()
