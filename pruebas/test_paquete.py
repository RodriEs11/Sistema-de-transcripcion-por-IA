"""Paquete transcripcion/ (docs/refactor.md, etapa 2): los datos de la instalación siguen en la carpeta del
sistema aunque el código esté en subcarpetas, y los módulos movidos no reaparecen sueltos en la raíz."""
from pathlib import Path
import re
import sys
import unittest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

import transcripcion  # noqa: E402
from transcripcion import ajustes  # noqa: E402
from transcripcion.acceso import usuarios  # noqa: E402
from transcripcion.base import plataforma, registro  # noqa: E402

MOVIDOS = ("plataforma", "persistencia", "registro", "ajustes", "borradores", "paciente", "indice_casos",
           "cola_procesamiento", "lotes_ia", "cache_transcripcion", "almacen_aprendizaje", "aprendizaje_pendiente",
           "usuarios")


class Paquete(unittest.TestCase):
    def test_raiz_es_la_carpeta_del_sistema(self):
        self.assertEqual(transcripcion.RAIZ, RAIZ)
        self.assertTrue((transcripcion.RAIZ / "servidor.py").exists())

    def test_datos_de_la_instalacion_en_la_raiz(self):
        for modulo in (plataforma, registro, usuarios, ajustes):
            with self.subTest(modulo=modulo.__name__):
                self.assertEqual(modulo.AQUI, RAIZ)
        self.assertEqual(registro.CARPETA, RAIZ / "registros")
        self.assertEqual(usuarios.ARCH, RAIZ / "usuarios.json")
        self.assertEqual(usuarios.CARPETA, RAIZ / "conocimiento" / "usuarios")

    def test_ningun_modulo_del_paquete_se_ubica_por_su_propia_carpeta(self):
        """Path(__file__).parent dentro del paquete apuntaría a transcripcion/…, no a la instalación."""
        patron = re.compile(r"Path\(__file__\)\.resolve\(\)\.parent(?!\.parent)")
        for p in (RAIZ / "transcripcion").rglob("*.py"):
            if p.name == "__init__.py" and p.parent.name == "transcripcion":
                continue
            with self.subTest(archivo=p.relative_to(RAIZ).as_posix()):
                self.assertIsNone(patron.search(p.read_text(encoding="utf-8")))

    def test_modulos_movidos_no_quedan_en_la_raiz(self):
        for nombre in MOVIDOS:
            with self.subTest(modulo=nombre):
                self.assertFalse((RAIZ / f"{nombre}.py").exists(), f"{nombre}.py volvió a la raíz")


if __name__ == "__main__":
    unittest.main()
