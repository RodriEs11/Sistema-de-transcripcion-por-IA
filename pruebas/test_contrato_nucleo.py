"""Contrato del núcleo: el texto normalizado, las marcas, el prompt, el orden de estudios y los párrafos del Word
no cambian durante el refactor (docs/refactor.md, etapa 0).

Corre `pruebas/contratos/calcular_nucleo.py` en una COPIA del sistema (carpeta temporal, conocimiento de ejemplo,
sin ejemplos aprendidos ni datos de la instalación) y compara con `pruebas/contratos/nucleo_esperado.json`.

Si un cambio funcional DELIBERADO cambia el resultado, regenerar el esperado y revisar el diff en el PR:
    ACTUALIZAR_CONTRATOS=1 python -m unittest pruebas.test_contrato_nucleo
Un refactor nunca debería necesitar regenerarlo.
"""
import difflib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

RAIZ = Path(__file__).resolve().parents[1]
CONTRATOS = Path(__file__).resolve().parent / "contratos"
ESPERADO = CONTRATOS / "nucleo_esperado.json"


def calcular():
    (RAIZ / "respaldo").mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="contrato_nucleo_", dir=RAIZ / "respaldo") as tmp:
        sistema = Path(tmp) / "sistema"
        sistema.mkdir()
        for p in RAIZ.glob("*.py"):
            shutil.copy2(p, sistema / p.name)
        for p in RAIZ.iterdir():     # paquetes de Python (estructura destino del refactor)
            if p.is_dir() and (p / "__init__.py").exists():
                shutil.copytree(p, sistema / p.name, ignore=shutil.ignore_patterns("__pycache__"))
        for nombre in ("configuracion.ejemplo.json", "vocabulario.txt"):
            shutil.copy2(RAIZ / nombre, sistema / nombre)
        shutil.copytree(RAIZ / "conocimiento.ejemplo", sistema / "conocimiento.ejemplo")
        for nombre in ("calcular_nucleo.py", "casos_nucleo.json"):
            shutil.copy2(CONTRATOS / nombre, sistema / nombre)
        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        r = subprocess.run([sys.executable, "calcular_nucleo.py"], cwd=sistema, env=env,
                           capture_output=True, text=True, encoding="utf-8", timeout=120)
        if r.returncode:
            raise AssertionError("calcular_nucleo.py falló:\n" + r.stderr[-4000:])
        return json.loads(r.stdout)


class ContratoNucleo(unittest.TestCase):
    maxDiff = None

    def test_salidas_del_nucleo_no_cambian(self):
        obtenido = calcular()
        if os.environ.get("ACTUALIZAR_CONTRATOS") == "1":
            ESPERADO.write_text(json.dumps(obtenido, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
                                encoding="utf-8")
            self.skipTest("Contrato del núcleo regenerado: revisar el diff antes de commitear.")
        self.assertTrue(ESPERADO.exists(), "Falta nucleo_esperado.json: generarlo con ACTUALIZAR_CONTRATOS=1")
        esperado = json.loads(ESPERADO.read_text(encoding="utf-8"))
        if obtenido != esperado:
            a = json.dumps(esperado, ensure_ascii=False, indent=1, sort_keys=True).splitlines()
            b = json.dumps(obtenido, ensure_ascii=False, indent=1, sort_keys=True).splitlines()
            diff = "\n".join(list(difflib.unified_diff(a, b, "esperado", "obtenido", lineterm=""))[:200])
            self.fail("Cambió la salida del núcleo. Si no era un cambio deliberado, el refactor alteró el "
                      "comportamiento:\n" + diff)

    def test_calculo_es_determinista(self):
        self.assertEqual(calcular(), calcular())


if __name__ == "__main__":
    unittest.main()
