"""Compara dos compilaciones de la app de escritorio a nivel IL (reorganizaciones sin cambios de comportamiento).

Uso:  python pruebas/comparar_il.py antes.exe despues.exe
Necesita `ikdasm` (Mono). Desensambla los dos ejecutables y compara el multiconjunto de líneas de IL normalizadas:
números de instrucción, nombres que inventa el compilador (lambdas, máquinas de estado de async: `<Metodo>c__async1A`)
y atributos con esos nombres codificados. Si mover métodos entre archivos (partial class) o cambiarlos de orden no
cambió ninguna instrucción, dice «IL equivalente». La versión de la app no debe cambiar entre las dos compilaciones
(o la diferencia es solo esa). Ver docs/compilacion.md.
"""
import re
import subprocess
import sys
from collections import Counter

_GENERADOS = re.compile(r"(m__|AnonStorey|am\$cache|c__Iterator|c__async|f__mg\$cache|switch\$map|f__ref\$|\$locvar|\$)"
                        r"[0-9A-Fa-f]+")
_BYTES = re.compile(r"([0-9A-F]{2} )*[0-9A-F]{2}( \))?")


def lineas_il(exe):
    texto = subprocess.run(["ikdasm", exe], capture_output=True, text=True, errors="replace", check=True).stdout
    texto = _GENERADOS.sub(r"\1N", texto)
    texto = re.sub(r"IL_[0-9a-f]{4}", "IL", texto)
    texto = re.sub(r"//.*", "", texto)
    out = Counter()
    for linea in texto.splitlines():
        s = " ".join(linea.split())
        if s and not _BYTES.fullmatch(s) and "AsyncStateMachineAttribute" not in s:
            out[s] += 1
    return out


def main(argv):
    if len(argv) != 2:
        print(__doc__)
        return 2
    a, b = lineas_il(argv[0]), lineas_il(argv[1])
    if a == b:
        print(f"IL equivalente ({sum(a.values())} líneas).")
        return 0
    print("El IL cambió. Solo en el primero:")
    for linea, n in list((a - b).items())[:20]:
        print(f"  -{n}× {linea}")
    print("Solo en el segundo:")
    for linea, n in list((b - a).items())[:20]:
        print(f"  +{n}× {linea}")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
