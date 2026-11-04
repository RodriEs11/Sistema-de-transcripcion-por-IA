"""Microbenchmark sintético de listar_casos, aislado de la instalación en uso.

Ejecutar con el Python del servidor. No inicia HTTP, Whisper ni Ollama.
No mide red, concurrencia ni latencia del navegador.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import statistics
import subprocess
import sys
import tempfile
import time


def medir(cantidades, repeticiones):
    from transcripcion import ajustes
    import servidor as S
    aj = ajustes.cargar()           # configuracion.json de la copia (carpetas de la copia)
    S.configurar(aj)
    ajustes.preparar_carpetas(aj)
    S.CON.preparar_conocimiento()

    creados = 0
    resultados = []
    for cantidad in cantidades:
        for i in range(creados, cantidad):
            nombre = f"ficticio_{i:06d}"
            archivos = {
                "informe_ia.txt": "Informe ficticio. Sin datos reales.",
                "original.txt": nombre + ".wav",
                "origen.txt": "PC-Prueba",
                "medico.txt": "Dr. Prueba",
                "paciente.json": json.dumps({"p": "Persona ficticia", "manual": True}),
                "json": json.dumps({"texto": "Prueba", "palabras": [{"p": "Prueba", "ini": 0, "fin": 60, "conf": 1}]}),
                "marcas.json": json.dumps({"v": 2, "total": 0, "lineas": [], "omisiones": []}),
                "borrador.html": "<p>Informe ficticio.</p>",
            }
            for extension, contenido in archivos.items():
                (S.DATOS / f"{nombre}.{extension}").write_text(contenido, encoding="utf-8")
        creados = cantidad
        inicio = time.perf_counter()
        casos = S.VISTA.listar_casos("PC-Prueba")
        primera = (time.perf_counter() - inicio) * 1000
        muestras = []
        for _ in range(repeticiones):
            inicio = time.perf_counter()
            casos = S.VISTA.listar_casos("PC-Prueba")
            muestras.append((time.perf_counter() - inicio) * 1000)
        assert len(casos) == cantidad
        resultados.append({"casos": cantidad, "primera_ms": round(primera, 1),
                           "mediana_ms": round(statistics.median(muestras), 1),
                           "max_ms": round(max(muestras), 1),
                           "json_bytes": len(json.dumps(casos, ensure_ascii=False).encode("utf-8"))})
    print(json.dumps({"repeticiones": repeticiones, "resultados": resultados}, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--casos", type=int, nargs="+", default=[100, 1000])
    parser.add_argument("--repeticiones", type=int, default=5)
    args = parser.parse_args()
    if args.repeticiones < 1 or any(n < 1 for n in args.casos):
        parser.error("Las cantidades deben ser positivas.")
    raiz = Path(__file__).resolve().parents[1]
    respaldo = raiz / "respaldo"
    respaldo.mkdir(exist_ok=True)
    # Copia explícita de fuentes y ejemplos: nunca configuración, registros ni casos reales.
    with tempfile.TemporaryDirectory(prefix="medir_listado_", dir=respaldo) as temporal:
        destino = Path(temporal) / "sistema"
        destino.mkdir()
        for fuente in raiz.glob("*.py"):
            shutil.copy2(fuente, destino / fuente.name)
        shutil.copytree(raiz / "transcripcion", destino / "transcripcion", ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copytree(raiz / "conocimiento.ejemplo", destino / "conocimiento.ejemplo")
        cfg = json.loads((raiz / "configuracion.ejemplo.json").read_text(encoding="utf-8"))
        cfg.update(carpeta_audios_nuevos="../Audios_nuevos", carpeta_informes="../Informes")
        (destino / "configuracion.json").write_text(json.dumps(cfg), encoding="utf-8")
        shutil.copy2(__file__, destino / "medicion.py")
        env = dict(os.environ, SIMULAR_IA="1", PYTHONPATH=str(destino))
        codigo = f"from medicion import medir; medir({sorted(set(args.casos))!r}, {args.repeticiones!r})"
        subprocess.run([sys.executable, "-c", codigo], cwd=destino, env=env, check=True)


if __name__ == "__main__":
    main()
