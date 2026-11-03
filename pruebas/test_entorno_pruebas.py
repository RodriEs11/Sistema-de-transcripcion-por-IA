"""Entorno de pruebas aislado: la instalación de origen no cambia y la copia no comparte datos ni puertos."""
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import crear_entorno_pruebas as E  # noqa: E402

GIT = shutil.which("git")


def git(*args, cwd):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def foto(carpeta):
    """Contenido de todos los archivos fuera de .git, para comprobar que el origen no cambia."""
    return {str(p.relative_to(carpeta)): p.read_bytes() for p in sorted(carpeta.rglob("*"))
            if p.is_file() and ".git" not in p.relative_to(carpeta).parts}


@unittest.skipUnless(GIT, "git no está instalado")
class EntornoPruebas(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        # "GitHub" ficticio y una instalación en uso clonada de él
        remoto = self.tmp / "remoto.git"
        semilla = self.tmp / "semilla"
        semilla.mkdir()
        git("init", "-q", "-b", "main", cwd=semilla)
        git("config", "user.email", "prueba@ejemplo.invalid", cwd=semilla)
        git("config", "user.name", "Prueba", cwd=semilla)
        (semilla / "servidor.py").write_text("VERSION = 'x'\n", encoding="utf-8")
        (semilla / "configuracion.ejemplo.json").write_text(json.dumps(
            {"carpeta_audios_nuevos": "..\\Audios_nuevos", "carpeta_informes": "..\\Informes"}), encoding="utf-8")
        (semilla / ".gitignore").write_text("configuracion.json\nacceso_remoto.json\nconocimiento/\nvoces/\n"
                                            "registros/\nresultados/\n", encoding="utf-8")
        (semilla / "linux").mkdir()
        (semilla / "linux" / "comun.sh").write_text("", encoding="utf-8")
        git("add", ".", cwd=semilla)
        git("commit", "-q", "-m", "inicial", cwd=semilla)
        git("branch", "experimental", cwd=semilla)
        git("clone", "-q", "--bare", str(semilla), str(remoto), cwd=self.tmp)
        self.prod = self.tmp / "sistema"
        git("clone", "-q", str(remoto), str(self.prod), cwd=self.tmp)
        # datos locales de la instalación en uso (no versionados)
        (self.prod / "configuracion.json").write_text(json.dumps(
            {"modelo_ia": "propio", "carpeta_audios_nuevos": "..\\Audios_nuevos",
             "carpeta_informes": "E:\\Informes"}), encoding="utf-8")
        (self.prod / "acceso_remoto.json").write_text("{\"secreto\": 1}", encoding="utf-8")
        for carpeta, archivo in (("conocimiento", "plantilla.md"), ("voces", "huellas.json"),
                                 ("registros", "log.txt"), ("resultados", "r.json")):
            (self.prod / carpeta).mkdir()
            (self.prod / carpeta / archivo).write_text("dato", encoding="utf-8")
        self.antes = foto(self.prod)
        self.rama_prod = git("rev-parse", "--abbrev-ref", "HEAD", cwd=self.prod)
        self.destino = self.tmp / "sistema_pruebas"

    def crear(self, **kw):
        return E.crear(self.prod, self.destino, avisar=lambda *_: None, **kw)

    def test_copia_aislada_sin_tocar_origen(self):
        r = self.crear()
        d = self.destino
        self.assertEqual(git("rev-parse", "--abbrev-ref", "HEAD", cwd=d), "experimental")
        self.assertEqual(git("rev-parse", "--abbrev-ref", "experimental@{upstream}", cwd=d), "origin/experimental")
        self.assertEqual(git("remote", "get-url", "origin", cwd=d), str(self.tmp / "remoto.git"))
        self.assertTrue((d / ".git").is_dir(), "debe ser un repositorio independiente, no un worktree")
        cfg = json.loads((d / "configuracion.json").read_text(encoding="utf-8"))
        self.assertEqual(cfg["modelo_ia"], "propio")
        self.assertEqual((cfg["carpeta_audios_nuevos"], cfg["carpeta_informes"]), ("Audios_nuevos", "Informes"))
        self.assertTrue((d / "Audios_nuevos").is_dir() and (d / "Informes").is_dir())
        self.assertTrue((d / "conocimiento" / "plantilla.md").exists())
        for privado in ("acceso_remoto.json", "voces", "registros", "resultados"):
            self.assertFalse((d / privado).exists(), privado)
        self.assertEqual(r["copiados"], ["conocimiento"])
        bat = (d / "iniciar_pruebas.bat").read_text(encoding="utf-8")
        self.assertIn("PUERTO_INTERFAZ=8865", bat)
        self.assertIn("SIMULAR_IA=1", bat)
        self.assertNotIn("--tunel", bat + (d / "iniciar_pruebas.sh").read_text(encoding="utf-8"))
        self.assertTrue((d / E.MARCA).exists())
        self.assertEqual(git("status", "--porcelain", cwd=d), "", "los archivos propios del entorno no se versionan")
        # la instalación en uso queda idéntica y en su rama
        self.assertEqual(foto(self.prod), self.antes)
        self.assertEqual(git("rev-parse", "--abbrev-ref", "HEAD", cwd=self.prod), self.rama_prod)
        self.assertEqual(git("status", "--porcelain", "--ignored=no", "--untracked-files=no", cwd=self.prod), "")

    def test_app_de_prueba_aislada(self):
        cli = self.prod / "cliente"
        (cli / "runtimes" / "win-x64" / "native").mkdir(parents=True)
        for nombre in E.BIBLIOTECAS_APP + ("Transcripcion.exe", "conexion.json", "runtimes/win-x64/native/WebView2Loader.dll"):
            (cli / nombre).write_text("binario ficticio", encoding="utf-8")
        antes = foto(self.prod)
        r = self.crear()
        d = self.destino / "cliente"
        self.assertEqual(r["app"], list(E.BIBLIOTECAS_APP) + ["runtimes"])
        self.assertTrue((d / E.PERFIL_APP).exists())
        self.assertTrue((d / "runtimes" / "win-x64" / "native" / "WebView2Loader.dll").exists())
        # nunca el ejecutable de producción ni el canal secreto que lleva a producción
        self.assertFalse((d / "Transcripcion.exe").exists())
        self.assertFalse((d / "conexion.json").exists())
        self.assertEqual(foto(self.prod), antes)
        # en un entorno ya creado: se encuentra la instalación en uso y se vuelve a preparar
        (d / E.PERFIL_APP).unlink()
        self.assertEqual(E.origen_del_entorno(self.destino).resolve(), self.prod.resolve())
        E.preparar_app(E.origen_del_entorno(self.destino), self.destino)
        self.assertTrue((d / E.PERFIL_APP).exists())
        with self.assertRaises(E.ErrorEntorno):
            E.origen_del_entorno(self.prod)

    def test_rama_nueva_sale_de_main(self):
        self.crear(rama="exp/idea", copiar=False)
        self.assertEqual(git("rev-parse", "--abbrev-ref", "HEAD", cwd=self.destino), "exp/idea")
        self.assertFalse((self.destino / "conocimiento").exists())

    def test_rechazos(self):
        with self.assertRaises(E.ErrorEntorno):
            self.crear(puerto=8765)
        with self.assertRaises(E.ErrorEntorno):
            self.crear(rama="mal nombre")
        with self.assertRaises(E.ErrorEntorno):
            E.crear(self.prod, self.prod / "adentro", avisar=lambda *_: None)
        self.assertFalse(self.destino.exists())
        self.crear()
        with self.assertRaises(E.ErrorEntorno):          # destino existente
            self.crear()
        with self.assertRaises(E.ErrorEntorno):          # desde un entorno de pruebas
            E.crear(self.destino, self.tmp / "otra", avisar=lambda *_: None)
        self.assertEqual(foto(self.prod), self.antes)


if __name__ == "__main__":
    unittest.main()
