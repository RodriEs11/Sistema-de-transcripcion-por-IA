"""Carpeta del conocimiento (plantillas, reglas, notas de médicos) y lectura de sus archivos.

`CONOC` se lee siempre como atributo del módulo (CON.CONOC): las pruebas lo apuntan a una carpeta temporal.

Viene de nucleo.py (docs/refactor.md, etapa 3).
"""
from transcripcion import RAIZ


AQUI = RAIZ          # carpeta del sistema (no la del paquete)
CONOC = AQUI / "conocimiento"


def preparar_conocimiento():
    """Primera vez (repositorio recién clonado): crea conocimiento/ a partir de conocimiento.ejemplo/.
    Solo copia los archivos que faltan; nunca pisa los que ya existen.
    La llaman los puntos de entrada (servidor, informe, aprender, importar_informes) al arrancar, no la
    importación del módulo (docs/refactor.md, etapa 1)."""
    ejemplo = AQUI / "conocimiento.ejemplo"
    if not ejemplo.is_dir():
        return
    for f in ejemplo.rglob("*"):
        destino = CONOC / f.relative_to(ejemplo)
        if f.is_file() and f.name != "README.md" and not f.name.startswith(".") and not destino.exists():
            destino.parent.mkdir(parents=True, exist_ok=True)
            destino.write_bytes(f.read_bytes())


# ------------------------------------------------------------- conocimiento
def leer(nombre):
    return (CONOC / nombre).read_text(encoding="utf-8-sig")
