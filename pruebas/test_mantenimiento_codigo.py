"""El panel avisa «código cambiado: hace falta reiniciar» también para los módulos del paquete transcripcion/,
y la prueba previa al reinicio compila el paquete (docs/refactor.md, etapa 2).

Corre en un proceso aparte sobre una copia del sistema (el gancho de import de mantenimiento es global).
"""
from pathlib import Path
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest

RAIZ = Path(__file__).resolve().parents[1]

CODIGO = textwrap.dedent("""
    import json, sys
    from pathlib import Path
    from transcripcion.operacion import mantenimiento as M
    import servidor
    M.empezar()
    cargados = set(M.CARGADO)
    antes = "transcripcion/asr/huecos.py" in M.CARGADO
    from transcripcion.asr import huecos            # se importa tarde: lo anota el gancho de import
    tarde = not antes and "transcripcion/asr/huecos.py" in M.CARGADO
    p = Path("transcripcion/casos/paciente.py")
    p.write_text(p.read_text(encoding="utf-8") + "\\n# cambio ficticio\\n", encoding="utf-8")
    cambios = [c["archivo"] for c in M.cambios_sin_tomar()]
    ajeno = M._archivo_local(Path(sys.executable))
    print("RESULTADO" + json.dumps({"cargados": sorted(cargados), "tarde": tarde, "cambios": cambios,
                                    "ajeno": ajeno}))
""")


def _copiar(destino):
    sistema = destino / "sistema"
    sistema.mkdir()
    for p in RAIZ.glob("*.py"):
        shutil.copy2(p, sistema / p.name)
    shutil.copytree(RAIZ / "transcripcion", sistema / "transcripcion", ignore=shutil.ignore_patterns("__pycache__"))
    for nombre in ("configuracion.ejemplo.json", "vocabulario.txt"):
        shutil.copy2(RAIZ / nombre, sistema / nombre)
    shutil.copytree(RAIZ / "conocimiento.ejemplo", sistema / "conocimiento.ejemplo")
    shutil.copytree(RAIZ / "web", sistema / "web")
    return sistema


class CodigoCambiado(unittest.TestCase):
    def setUp(self):
        (RAIZ / "respaldo").mkdir(exist_ok=True)
        tmp = tempfile.TemporaryDirectory(prefix="mantenimiento_", dir=RAIZ / "respaldo")
        self.addCleanup(tmp.cleanup)
        self.sistema = _copiar(Path(tmp.name))
        self.env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8")

    def correr(self, codigo):
        r = subprocess.run([sys.executable, "-c", codigo], cwd=self.sistema, env=self.env, capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=180)
        self.assertEqual(r.returncode, 0, r.stderr[-3000:])
        return r.stdout

    def test_detecta_cambios_en_el_paquete(self):
        import json
        salida = json.loads(self.correr(CODIGO).rsplit("RESULTADO", 1)[-1])
        self.assertIn("servidor.py", salida["cargados"])
        self.assertIn("transcripcion/base/registro.py", salida["cargados"])
        self.assertIn("transcripcion/casos/paciente.py", salida["cargados"])
        self.assertTrue(salida["tarde"], "no anotó un módulo importado después de arrancar")
        self.assertEqual(salida["cambios"], ["transcripcion/casos/paciente.py"])
        self.assertIsNone(salida["ajeno"], "anotó un archivo que no es del sistema")

    def test_prueba_previa_compila_el_paquete(self):
        codigo = "from transcripcion.operacion import mantenimiento as M; print('RESULTADO', repr(M.prueba_de_arranque()))"
        self.assertEqual(self.correr(codigo).rsplit("RESULTADO", 1)[-1].strip(), "None")
        p = self.sistema / "transcripcion" / "casos" / "paciente.py"
        p.write_text(p.read_text(encoding="utf-8") + "\ndef roto(:\n", encoding="utf-8")
        resultado = self.correr(codigo).rsplit("RESULTADO", 1)[-1]
        self.assertIn("ERROR_SINTAXIS", resultado)
        self.assertIn("paciente.py", resultado)


if __name__ == "__main__":
    unittest.main()
