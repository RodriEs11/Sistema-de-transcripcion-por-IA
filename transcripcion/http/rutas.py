"""Tabla de rutas: (método, ruta) → función que atiende el pedido.

Cada función recibe el manejador del pedido (`h`: responde con h._json, h._html…, y trae h.sis, h.pc, h.usuario,
h.remoto) y un `Pedido` con lo ya leído. Las rutas exactas se buscan antes que los prefijos.

Un POST pasa por fases, en el mismo orden que antes tenía la cadena de `if` de servidor.py:
  - "cruda": la función lee el cuerpo como quiere (audios, Word, formularios); no se lee como JSON.
  - "json":  el cuerpo ya se leyó como JSON (pedido.datos).
  - "caso":  además, pedido.datos["nombre"] es un nombre de caso válido (pedido.nombre); si no, 400.
             Con `libre=True`, si otra PC tiene el caso abierto (o el panel se lo liberó) se responde 409.
Un POST a una ruta desconocida igual se lee como JSON y se valida el nombre antes del 404, como antes.
"""

from collections.abc import Callable
from dataclasses import dataclass

FASES = ("cruda", "json", "caso")


@dataclass
class Pedido:
    ruta: str
    q: dict  # parámetros de la dirección (parse_qs)
    datos: dict | None = None  # cuerpo JSON (POST desde la fase "json")
    nombre: str | None = None  # caso validado (POST en la fase "caso")


@dataclass(frozen=True)
class Ruta:
    funcion: Callable
    fase: str = "caso"
    libre: bool = False


class Rutas:
    def __init__(self):
        self._exactas = {}  # (método, ruta) -> Ruta
        self._prefijos = []  # (método, prefijo, Ruta), en el orden en que se agregaron

    def _nueva(self, funcion, fase, libre):
        if fase not in FASES:
            raise ValueError(f"fase desconocida: {fase}")
        return Ruta(funcion, fase, libre)

    def get(self, rutas, funcion):
        for r in (rutas,) if isinstance(rutas, str) else rutas:
            self._agregar("GET", r, Ruta(funcion))

    def post(self, rutas, funcion, fase, libre=False):
        for r in (rutas,) if isinstance(rutas, str) else rutas:
            self._agregar("POST", r, self._nueva(funcion, fase, libre))

    def prefijo(self, metodo, prefijo, funcion, fase="caso"):
        self._prefijos.append(
            (metodo, prefijo, Ruta(funcion) if metodo == "GET" else self._nueva(funcion, fase, False))
        )

    def _agregar(self, metodo, ruta, r):
        if (metodo, ruta) in self._exactas:
            raise ValueError(f"ruta repetida: {metodo} {ruta}")
        self._exactas[(metodo, ruta)] = r

    def buscar(self, metodo, ruta):
        """La Ruta que atiende el pedido, o None."""
        r = self._exactas.get((metodo, ruta))
        if r:
            return r
        for m, prefijo, r in self._prefijos:
            if m == metodo and ruta.startswith(prefijo):
                return r
        return None

    def listado(self):
        """[(método, ruta o prefijo…, función)] para la documentación y las pruebas."""
        out = [(m, ruta, r.funcion) for (m, ruta), r in self._exactas.items()]
        out += [(m, p + "…", r.funcion) for m, p, r in self._prefijos]
        return out
