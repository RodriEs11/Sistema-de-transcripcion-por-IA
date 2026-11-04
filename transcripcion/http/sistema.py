"""Lo que necesitan las rutas HTTP: ajustes del arranque, servicios y el estado compartido del proceso.

Lo arma servidor.configurar() con los mismos objetos que usa el resto del servidor (CASOS, PROC, VISTA…): una
prueba que parchea un método de S.CASOS lo ve también acá. Las rutas lo leen como `h.sis`.
"""

import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(eq=False)
class Sistema:
    cfg: dict
    datos: Path  # Informes/revision/datos
    nuevos: Path  # audios nuevos
    informes: Path  # carpeta de los Word
    web: Path  # páginas (web/)
    puerto: int  # interfaz local (el panel solo se abre en 127.0.0.1:puerto)
    puerto_tunel: int | None
    simular: bool
    version: str
    inicio: float
    casos: Any  # transcripcion.casos.repositorio.Casos
    proc: Any  # transcripcion.procesamiento.estado.Procesamiento
    ia: Any  # transcripcion.operacion.ia.EstadoIA
    voces: Any  # transcripcion.voz.servicio.ServicioVoz
    vista: Any  # transcripcion.casos.vista.VistaCasos
    borrado: Any  # transcripcion.casos.borrado.Borrado
    oper: Any  # transcripcion.operacion.reinicio.Operacion
    guardado: Any  # transcripcion.informe.guardado.Guardado
    tunel: dict  # {"modo", "http", "error"} del túnel (lo comparte con servidor.abrir_tunel)
    visto: dict  # PC del trabajo -> hora de su último pedido (lo muestra también la consola)
    abrir_tunel: Callable[[], None]
    fmt_lock: Any = field(default_factory=threading.Lock)  # formato de un caso (autocorrección de Word)
    recibir_audio_lock: Any = field(default_factory=threading.RLock)  # un audio repetido no crea dos casos
