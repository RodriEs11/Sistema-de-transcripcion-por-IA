"""Importar cualquier módulo del sistema no escribe nada (docs/refactor.md, etapa 1).

Antes, `import servidor` creaba configuracion.json, ../Audios_nuevos e ../Informes/revision/datos, e
`import nucleo` creaba conocimiento/. Corrido dentro de la instalación en uso, eso tocaba las carpetas reales.
Ahora la configuración se lee y las carpetas se crean solo al arrancar (main / ajustes.cargar).

Cada módulo se importa en un proceso nuevo, sobre una copia del sistema en una carpeta temporal, y se compara
el contenido de la carpeta antes y después.
"""
from pathlib import Path
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

RAIZ = Path(__file__).resolve().parents[1]


def _copiar(destino):
    sistema = destino / "sistema"
    sistema.mkdir()
    for p in RAIZ.glob("*.py"):
        shutil.copy2(p, sistema / p.name)
    for p in RAIZ.iterdir():
        if p.is_dir() and (p / "__init__.py").exists():
            shutil.copytree(p, sistema / p.name, ignore=shutil.ignore_patterns("__pycache__"))
    for nombre in ("configuracion.ejemplo.json", "vocabulario.txt"):
        shutil.copy2(RAIZ / nombre, sistema / nombre)
    for carpeta in ("web", "conocimiento.ejemplo"):
        shutil.copytree(RAIZ / carpeta, sistema / carpeta)
    return sistema


def _modulos(sistema):
    mods = sorted(p.stem for p in sistema.glob("*.py"))
    for p in sorted(sistema.rglob("*.py")):
        rel = p.relative_to(sistema)
        if len(rel.parts) > 1 and (sistema / rel.parts[0] / "__init__.py").exists():
            mods.append(".".join(rel.with_suffix("").parts).removesuffix(".__init__"))
    return mods


def _inventario(base):
    return {str(p.relative_to(base)) for p in base.rglob("*") if "__pycache__" not in p.parts}


class ImportarSinEfectos(unittest.TestCase):
    def test_ningun_modulo_escribe_al_importarse(self):
        (RAIZ / "respaldo").mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="importar_", dir=RAIZ / "respaldo") as tmp:
            base = Path(tmp)
            sistema = _copiar(base)
            locales = set(_modulos(sistema))
            env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8")
            for mod in sorted(locales):
                with self.subTest(modulo=mod):
                    antes = _inventario(base)
                    r = subprocess.run([sys.executable, "-c", f"import {mod}"], cwd=sistema, env=env,
                                       capture_output=True, text=True, encoding="utf-8", errors="replace",
                                       timeout=120)
                    if r.returncode and "ModuleNotFoundError" in r.stderr:
                        falta = r.stderr.rsplit("No module named", 1)[-1].strip(" '\"\n").split(".")[0]
                        if falta not in locales:
                            self.skipTest(f"{mod}: falta la dependencia externa {falta} en este entorno")
                    self.assertEqual(r.returncode, 0, r.stderr[-2000:])
                    nuevos = sorted(_inventario(base) - antes)
                    self.assertEqual(nuevos, [], f"`import {mod}` creó archivos o carpetas")

    def test_prueba_antes_de_reiniciar_valida_la_configuracion(self):
        """Como importar el servidor ya no lee configuracion.json, la prueba previa al reinicio desde el panel
        (mantenimiento.prueba_de_arranque) la lee aparte: una configuración rota no deja reiniciar."""
        (RAIZ / "respaldo").mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="arranque_", dir=RAIZ / "respaldo") as tmp:
            sistema = _copiar(Path(tmp))
            codigo = "from transcripcion.operacion import mantenimiento as M; print('RESULTADO', repr(M.prueba_de_arranque()))"
            env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8")

            def probar():
                r = subprocess.run([sys.executable, "-c", codigo], cwd=sistema, env=env, capture_output=True,
                                   text=True, encoding="utf-8", errors="replace", timeout=180)
                self.assertEqual(r.returncode, 0, r.stderr[-2000:])
                return r.stdout.rsplit("RESULTADO", 1)[-1].strip()
            self.assertEqual(probar(), "None")
            self.assertFalse((sistema / "configuracion.json").exists(), "la prueba no debe crear la configuración")
            (sistema / "configuracion.json").write_text("{roto", encoding="utf-8")
            self.assertIn("JSONDecodeError", probar())


if __name__ == "__main__":
    unittest.main()
