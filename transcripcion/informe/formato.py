"""Formato del informe: qué líneas van en negrita en el Word y en la vista previa.

Viene de nucleo.py (docs/refactor.md, etapa 3).
"""


def debe_ir_en_negrita(linea, titulo, cfg):
    if not linea.strip():
        return False
    if titulo and cfg.get("negrita_titulos", True):
        return True
    if linea.strip().rstrip(":") in cfg.get("negrita_lineas_exactas", NEGRITA_EXACTAS):
        return True
    return linea.strip().startswith(tuple(cfg.get("negrita_si_empieza_con", NEGRITA_DEF)))


NEGRITA_EXACTAS = ["Tórax", "Abdomen", "Pelvis", "CONCLUSIÓN"]
NEGRITA_DEF = [
    "Categorización conjunta",
    "Se efectuó el estudio en",
    "Se efectuó en un equipo PET/CT",
    "Hallazgos PET/CT",
    "Hallazgos CT",
    "SERVICIO DE",
]
