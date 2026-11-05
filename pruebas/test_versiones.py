"""Casos de versiones desincronizadas, sin tocar los archivos de la instalación."""
import shutil
import re
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "herramientas"))
from verificar_versiones import RAIZ, comprobar, sin_publicar, ultimas_etiquetas  # noqa: E402
import subir_version as S  # noqa: E402

NOTAS_APP = "### App\n\n#### Corregido\n- Algo de la app (#99).\n\n"
NOTAS_SERVIDOR = "### Servidor\n\n#### Agregado\n- Algo del servidor (#98).\n\n"


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

    def leer(self, nombre):
        return (self.raiz / nombre).read_text(encoding="utf-8")

    def escribir(self, nombre, texto):
        (self.raiz / nombre).write_text(texto, encoding="utf-8")

    def con_notas(self, *notas):
        """Deja en «Sin publicar» solo el texto pendiente y las notas indicadas."""
        inicio, pendiente, _, resto = sin_publicar(self.leer("CHANGELOG.md"))
        self.escribir("CHANGELOG.md", inicio + pendiente.rstrip("\n") + "\n\n" + "".join(notas) + resto)

    def versiones(self):
        _, app, servidor = comprobar(self.raiz, sin_binario=True, etiquetas={})
        return {"App": app, "Servidor": servidor}

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

    def test_detecta_version_anterior_a_la_ultima_entrega(self):
        errores, _, _ = comprobar(self.raiz, sin_binario=True, etiquetas={"App": "99.0"})
        self.assertTrue(any("anterior a la última entrega" in e for e in errores), errores)

    def test_detecta_mes_del_servidor_distinto_de_su_fecha(self):
        servidor = self.versiones()["Servidor"]
        texto = re.sub(r"^(## \[Servidor " + re.escape(servidor) + r"\] — )\d{4}-\d{2}-\d{2}",
                       r"\g<1>1999-01-01", self.leer("CHANGELOG.md"), flags=re.M)
        self.escribir("CHANGELOG.md", texto)
        errores, _, _ = comprobar(self.raiz, sin_binario=True, etiquetas={})
        self.assertTrue(any("año y mes" in e for e in errores), errores)

    def test_entrega_sin_versiones_nuevas_ni_notas_pendientes(self):
        self.con_notas(NOTAS_SERVIDOR)
        errores, _, _ = comprobar(self.raiz, sin_binario=True, entrega=True, etiquetas=self.versiones())
        self.assertTrue(any("notas de Servidor" in e for e in errores), errores)
        self.assertTrue(any("no hay nada que entregar" in e for e in errores), errores)

    def test_siguiente_version(self):
        self.assertEqual(S.siguiente_app("1.28", "parche"), "1.28.1")
        self.assertEqual(S.siguiente_app("1.28.1", "parche"), "1.28.2")
        self.assertEqual(S.siguiente_app("1.28.1", "menor"), "1.29")
        self.assertEqual(S.siguiente_app("1.28", "mayor"), "2.0")
        self.assertEqual(S.siguiente_servidor("2026.11.15", date(2026, 11, 30)), "2026.11.16")
        self.assertEqual(S.siguiente_servidor("2026.11.15", date(2026, 12, 1)), "2026.12.1")
        self.assertEqual(S.siguiente_servidor("2026.12.4", date(2027, 1, 2)), "2027.1.1")
        with self.assertRaises(S.ErrorEntrega):
            S.siguiente_servidor("2026.11.15", date(2026, 10, 31))
        self.assertEqual(S.para_ensamblado("1.29"), "1.29.0.0")
        self.assertEqual(S.para_ensamblado("1.28.1"), "1.28.1.0")

    def test_entrega_completa_de_app_y_servidor(self):
        antes = self.versiones()
        self.con_notas(NOTAS_APP, NOTAS_SERVIDOR)
        fecha = date(2099, 12, 2)
        subidas = S.subir(self.raiz, app="menor", servidor=True, fecha=fecha, leeme="Una línea para las PC.")
        app, servidor = subidas["App"][1], subidas["Servidor"][1]
        self.assertEqual(servidor, "2099.12.1")
        self.assertEqual(app, S.siguiente_app(antes["App"], "menor"))
        self.assertEqual(comprobar(self.raiz, sin_binario=True, entrega=True, etiquetas=antes)[0], [])
        codigo = self.leer("cliente_codigo/Programa.cs")
        self.assertIn(f'AssemblyFileVersion("{app}.0.0")', codigo)
        historial = self.leer("CHANGELOG.md")
        self.assertEqual(sin_publicar(historial)[2], {})
        posiciones = [historial.index(f"## [{n}] — 2099-12-02") for n in (f"App {app}", f"Servidor {servidor}")]
        self.assertLess(posiciones[0], posiciones[1])
        self.assertIn(f"Acompaña al Servidor {servidor}.\n\n### Corregido\n- Algo de la app (#99).", historial)
        self.assertIn(f"Versión actual: {app} (2099-12-02).\n{app} / Servidor {servidor}: Una línea para las PC.",
                      self.leer("cliente/LEEME.txt"))

    def test_entrega_exige_notas_y_subir_lo_fusionado(self):
        self.con_notas(NOTAS_APP, NOTAS_SERVIDOR)
        with self.assertRaisesRegex(S.ErrorEntrega, "--servidor"):
            S.subir(self.raiz, app="parche", leeme="x")           # el servidor cambió: también se entrega
        self.con_notas(NOTAS_SERVIDOR)
        original = {n: self.leer(n) for n in ("CHANGELOG.md", "servidor.py", "cliente_codigo/Programa.cs")}
        with self.assertRaisesRegex(S.ErrorEntrega, "notas de App"):
            S.subir(self.raiz, app="parche", servidor=True, leeme="x")   # la app no tiene nada que entregar
        with self.assertRaisesRegex(S.ErrorEntrega, "--leeme"):
            S.subir(self.raiz, app="parche")
        self.assertEqual({n: self.leer(n) for n in original}, original, "un error no debe dejar archivos a medias")
        S.subir(self.raiz, servidor=True, fecha=date(2099, 1, 5), escribir=False)
        self.assertEqual({n: self.leer(n) for n in original}, original, "--sin-escribir no debe cambiar nada")

    @unittest.skipUnless(shutil.which("git"), "git no está instalado")
    def test_ultimas_etiquetas_de_git(self):
        repo = self.raiz / "repo"
        repo.mkdir()
        git = ["git", "-c", "user.name=prueba", "-c", "user.email=prueba@ejemplo.invalid", "-C", str(repo)]
        subprocess.run(git + ["init", "-q"], check=True)
        subprocess.run(git + ["commit", "-q", "--allow-empty", "-m", "inicio"], check=True)
        for etiqueta in ("app-v1.9", "app-v1.10", "app-v1.10.1", "servidor-v2026.9.30", "servidor-v2026.10.2", "otra"):
            subprocess.run(git + ["tag", "-a", etiqueta, "-m", etiqueta], check=True)
        self.assertEqual(ultimas_etiquetas(repo), {"App": "1.10.1", "Servidor": "2026.10.2"})


if __name__ == "__main__":
    unittest.main()
