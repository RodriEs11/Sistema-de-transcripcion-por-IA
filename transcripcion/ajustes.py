"""Ajustes del sistema: se leen UNA vez al arrancar y se pasan a quien los necesita.

Ningún módulo lee `configuracion.json` ni crea carpetas al importarse (docs/refactor.md, etapa 1).
El arranque hace, en este orden:

    aj = ajustes.cargar()            # lee configuracion.json (la crea desde el ejemplo si falta) y el entorno
    ajustes.preparar_carpetas(aj)    # crea Audios_nuevos e Informes/revision/datos si faltan

Una prueba arma los suyos con `ajustes.para_pruebas(carpeta)`, que no toca la instalación.
"""

from dataclasses import dataclass, field
import json
import os
from pathlib import Path

from transcripcion.base import plataforma as P
from transcripcion import RAIZ

AQUI = RAIZ  # carpeta del sistema (no la del paquete)

# Opciones que pueden faltar en una configuracion.json vieja (mismos valores que configuracion.ejemplo.json).
PREDETERMINADOS = {
    "lote_max_audios": 2,
    "lote_max_segundos": 180,
    "reusar_transcripcion": True,
}


def leer_config(raiz=AQUI, crear=True):
    """configuracion.json de `raiz` como dict, con las carpetas como rutas absolutas.

    Si falta (repositorio recién clonado) y `crear` es True, la crea copiando configuracion.ejemplo.json;
    con `crear=False` usa el ejemplo sin escribir nada (sirve para validar sin efectos)."""
    raiz = Path(raiz)
    archivo = raiz / "configuracion.json"
    ejemplo = raiz / "configuracion.ejemplo.json"
    if archivo.exists():
        texto = archivo.read_text(encoding="utf-8-sig")
    elif ejemplo.exists():
        texto = ejemplo.read_text(encoding="utf-8-sig")
        if crear:
            archivo.write_text(texto, encoding="utf-8")
    else:
        raise FileNotFoundError(f"No encuentro {archivo} ni {ejemplo}")
    c = json.loads(texto)
    for k, v in PREDETERMINADOS.items():
        c.setdefault(k, v)
    for k in ("carpeta_audios_nuevos", "carpeta_informes"):
        p = P.ruta_config(c[k])
        c[k] = p if p.is_absolute() else (raiz / p).resolve()
    return c


@dataclass(frozen=True)
class Ajustes:
    raiz: Path  # carpeta del sistema (la de servidor.py)
    cfg: dict = field(repr=False)  # configuracion.json ya leída (carpetas como rutas absolutas)
    puerto: int  # interfaz web local (PUERTO_INTERFAZ, 8765)
    puerto_tunel: int  # túnel de Microsoft: todo lo que entra por acá es remoto (PUERTO_TUNEL, puerto + 1)
    simular_ia: bool  # SIMULAR_IA=1: sin Whisper ni Ollama (pruebas)

    @property
    def audios_nuevos(self) -> Path:
        return self.cfg["carpeta_audios_nuevos"]

    @property
    def informes(self) -> Path:
        return self.cfg["carpeta_informes"]

    @property
    def datos(self) -> Path:
        """Archivos de revisión de cada caso (dictado, informe de la IA, marcas, borrador…)."""
        return self.informes / "revision" / "datos"


def cargar(raiz=AQUI, entorno=None, crear_config=True):
    """Ajustes del arranque: configuracion.json + variables de entorno. No crea carpetas."""
    entorno = os.environ if entorno is None else entorno
    puerto = int(entorno.get("PUERTO_INTERFAZ", "8765"))
    return Ajustes(
        raiz=Path(raiz),
        cfg=leer_config(raiz, crear=crear_config),
        puerto=puerto,
        puerto_tunel=int(entorno.get("PUERTO_TUNEL", str(puerto + 1))),
        simular_ia=entorno.get("SIMULAR_IA") == "1",
    )


def preparar_carpetas(aj):
    """Crea las carpetas de trabajo si faltan. Solo en el arranque real (o en la carpeta de una prueba)."""
    for d in (aj.audios_nuevos, aj.datos):
        d.mkdir(parents=True, exist_ok=True)


def para_pruebas(carpeta, raiz=AQUI, **cambios):
    """Ajustes que apuntan a `carpeta` (Audios_nuevos e Informes adentro), con el resto del ejemplo.
    `cambios` reemplaza opciones de configuración (por ejemplo lote_max_audios=1, o carpeta_informes=… para usar
    otra carpeta de informes; los datos de los casos quedan en <carpeta_informes>/revision/datos)."""
    carpeta = Path(carpeta)
    ejemplo = Path(raiz) / "configuracion.ejemplo.json"  # nunca la configuración de la instalación
    cfg = json.loads(ejemplo.read_text(encoding="utf-8-sig")) if ejemplo.exists() else {}
    cfg = {
        **PREDETERMINADOS,
        **cfg,
        "carpeta_audios_nuevos": carpeta / "Audios_nuevos",
        "carpeta_informes": carpeta / "Informes",
        **cambios,
    }
    return Ajustes(raiz=Path(raiz), cfg=cfg, puerto=0, puerto_tunel=0, simular_ia=True)
