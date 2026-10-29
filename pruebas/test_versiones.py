"""Casos de versiones desincronizadas, sin tocar los archivos de la instalación."""
import shutil
import re
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from verificar_versiones import RAIZ, comprobar


class VersionesTest(unittest.TestCase):
    def setUp(self):
        respaldos = RAIZ / "respaldo"
        respaldos.mkdir(exist_ok=True)
        self.temporal = tempfile.TemporaryDirectory(prefix="test_versiones_", dir=respaldos)
        if not Path(self.temporal.name).resolve().is_relative_to(respaldos.resolve()):
            raise RuntimeError("La carpeta temporal debe estar dentro de respaldo/.")
        self.addCleanup(self.temporal.cleanup)
        self.raiz = Path(self.temporal.name)
        for nombre in ("cliente_codigo/Programa.cs", "servidor.py", "CHANGELOG.md", "cliente/LEEME.txt"):
            destino = self.raiz / nombre
            destino.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(RAIZ / nombre, destino)

    def test_fuentes_coherentes(self):
        errores, _, _ = comprobar(self.raiz, sin_binario=True)
        self.assertEqual(errores, [])

    def test_detecta_metadatos_distintos(self):
        ruta = self.raiz / "cliente_codigo/Programa.cs"
        texto = ruta.read_text(encoding="utf-8")
        texto = re.sub(r'AssemblyFileVersion\("[0-9.]+"\)', 'AssemblyFileVersion("0.0.0.0")', texto)
        ruta.write_text(texto, encoding="utf-8")
        errores, _, _ = comprobar(self.raiz, sin_binario=True)
        self.assertTrue(any("AssemblyFileVersion" in e for e in errores), errores)

    def test_detecta_historial_y_leeme_faltantes(self):
        (self.raiz / "CHANGELOG.md").write_text("", encoding="utf-8")
        (self.raiz / "cliente/LEEME.txt").write_text("", encoding="utf-8")
        errores, _, _ = comprobar(self.raiz, sin_binario=True)
        self.assertEqual(len(errores), 3, errores)

    def test_exige_ejecutable_para_distribucion(self):
        errores, _, _ = comprobar(self.raiz)
        self.assertTrue(any("ejecutable distribuido" in e for e in errores), errores)


if __name__ == "__main__":
    unittest.main()
