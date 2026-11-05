"""El panel (Mantenimiento) muestra la etiqueta de la entrega junto al commit, con git y leyendo .git a mano.

Se arma un repositorio de prueba dentro de respaldo/ y se apunta mantenimiento a él (GIT y AQUI son globales
del módulo; se restauran al terminar). Ver docs/versiones.md.
"""
import shutil
import subprocess
import tempfile
import unittest
import zlib
from pathlib import Path
from unittest.mock import patch

from transcripcion.operacion import mantenimiento as M

RAIZ = Path(__file__).resolve().parents[1]
SHA = "a" * 40
OTRO = "b" * 40


class EtiquetasGit(unittest.TestCase):
    def setUp(self):
        (RAIZ / "respaldo").mkdir(exist_ok=True)
        tmp = tempfile.TemporaryDirectory(prefix="etiquetas_git_", dir=RAIZ / "respaldo")
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name)

    def apuntar(self, carpeta):
        for nombre, valor in (("AQUI", carpeta), ("GIT", carpeta / ".git")):
            p = patch.object(M, nombre, valor)
            p.start()
            self.addCleanup(p.stop)

    def test_lee_etiquetas_sin_el_programa_git(self):
        git = self.base / ".git"
        (git / "refs" / "tags" / "viejas").mkdir(parents=True)
        (git / "refs" / "tags" / "liviana").write_text(SHA + "\n", encoding="utf-8")
        (git / "refs" / "tags" / "viejas" / "ajena").write_text(OTRO + "\n", encoding="utf-8")
        # etiqueta anotada suelta: apunta a un objeto «tag» que nombra el commit
        anotada = b"object " + SHA.encode() + b"\ntype commit\ntag app-v1.29\n\nApp 1.29\n"
        objeto = "c" * 40
        (git / "objects" / objeto[:2]).mkdir(parents=True)
        (git / "objects" / objeto[:2] / objeto[2:]).write_bytes(
            zlib.compress(b"tag %d\0" % len(anotada) + anotada))
        (git / "refs" / "tags" / "app-v1.29").write_text(objeto + "\n", encoding="utf-8")
        (git / "packed-refs").write_text(
            "# pack-refs with: peeled fully-peeled sorted\n"
            f"{'d' * 40} refs/tags/servidor-v2026.11.16\n^{SHA}\n"
            f"{SHA} refs/tags/empaquetada\n"
            f"{'e' * 40} refs/tags/servidor-v2026.11.15\n^{OTRO}\n"
            f"{SHA} refs/heads/main\n", encoding="utf-8")
        self.apuntar(self.base)
        self.assertEqual(M._etiquetas_archivos(SHA),
                         ["app-v1.29", "empaquetada", "liviana", "servidor-v2026.11.16"])

    @unittest.skipUnless(shutil.which("git"), "git no está instalado")
    def test_info_git_incluye_etiquetas(self):
        repo = self.base / "repo"
        repo.mkdir()
        git = ["git", "-c", "user.name=prueba", "-c", "user.email=prueba@ejemplo.invalid", "-C", str(repo)]
        subprocess.run(git + ["init", "-q"], check=True)
        subprocess.run(git + ["commit", "-q", "--allow-empty", "-m", "entrega"], check=True)
        subprocess.run(git + ["tag", "-a", "servidor-v2026.11.16", "-m", "Servidor 2026.11.16"], check=True)
        subprocess.run(git + ["commit", "-q", "--allow-empty", "-m", "después"], check=True)
        subprocess.run(git + ["tag", "app-v1.29"], check=True)
        self.apuntar(repo)
        self.assertEqual(M._git_cli()["etiquetas"], ["app-v1.29"])
        self.assertEqual(M._git_archivos()["etiquetas"], ["app-v1.29"])
        subprocess.run(git + ["checkout", "-q", "servidor-v2026.11.16"], check=True)
        self.assertEqual(M._git_cli()["etiquetas"], ["servidor-v2026.11.16"])
        subprocess.run(git + ["pack-refs", "--all"], check=True)   # anotada pasa a packed-refs con su «^commit»
        self.assertEqual(M._git_archivos()["etiquetas"], ["servidor-v2026.11.16"])


if __name__ == "__main__":
    unittest.main()
