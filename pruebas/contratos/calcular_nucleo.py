"""Calcula las salidas del núcleo (texto, marcas, prompt, orden, Word) para los casos de casos_nucleo.json.

Lo ejecuta test_contrato_nucleo.py dentro de una COPIA del sistema en una carpeta temporal, con el
conocimiento de ejemplo y sin ejemplos aprendidos. Imprime un JSON por la salida estándar.

Durante el refactor (docs/refactor.md) este es el ÚNICO archivo que cambia cuando una función se mueve de
módulo: se actualizan los imports y la preparación de acá abajo, y el resultado esperado
(nucleo_esperado.json) debe quedar igual.
"""
import json
from pathlib import Path
import sys

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))

# --- Dónde vive cada función hoy. Al mover código, cambiar solo estas líneas. ---------------------------------
from fase1_transcribir import normalizar, palabras_a_numeros, datos_criticos   # noqa: E402
from nucleo import (marcar, a_html, contar_marcas, omisiones, ordenar_estudios,   # noqa: E402
                    estudios_sin_plantilla, armar_mensajes, elegir_ejemplos, categorias, preparar_conocimiento)
from informe import config, parrafos_docx   # noqa: E402


def preparar():
    """Lo que hace un punto de entrada antes de usar el núcleo (desde la etapa 1, no al importar)."""
    preparar_conocimiento()
# ----------------------------------------------------------------------------------------------------------------


def _json(x):
    """Tuplas -> listas, para comparar con lo guardado."""
    return json.loads(json.dumps(x, ensure_ascii=False))


def main():
    casos = json.loads((AQUI / "casos_nucleo.json").read_text(encoding="utf-8"))
    cfg = config()
    preparar()
    salida = {"normalizar": {}, "informes": {}, "prompt": {}}

    for frase in casos["frases"]:
        salida["normalizar"][frase] = {"normalizar": normalizar(frase),
                                       "palabras_a_numeros": palabras_a_numeros(frase),
                                       "datos_criticos": sorted(datos_criticos(frase))}

    for c in casos["informes"]:
        palabras = c.get("palabras")
        marcado = marcar(c["informe"], c["dictado"], palabras)
        salida["informes"][c["id"]] = {
            "marcado": _json(marcado),
            "html": a_html(marcado, palabras),
            "conteo": contar_marcas(marcado),
            "omisiones": _json(omisiones(c["dictado"], c["informe"], palabras)),
            "ordenado": ordenar_estudios(c["informe"]),
            "sin_plantilla": _json(estudios_sin_plantilla(c["informe"])),
            "categorias": sorted(categorias(c["dictado"])),
            "parrafos_word": _json(parrafos_docx(marcado, cfg)),
        }

    banco = casos["banco"]
    for p in casos["prompts"]:
        ej = elegir_ejemplos(p["dictado"], banco, k=p.get("k", 2), excluir=p.get("excluir"), medico=p.get("medico"))
        salida["prompt"][p["id"]] = {"ejemplos": [e["nombre"] for e in ej],
                                     "mensajes": _json(armar_mensajes(p["dictado"], ej, p.get("medico")))}

    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(salida, ensure_ascii=False, indent=1, sort_keys=True))


if __name__ == "__main__":
    main()
