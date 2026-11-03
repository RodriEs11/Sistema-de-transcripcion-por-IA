"""Formación FIFO acotada, sin esperar a que lleguen más audios. Un único consumidor GPU."""
import math
import queue


def limites(cfg):
    def numero(clave, defecto, minimo, maximo):
        valor = cfg.get(clave, defecto)
        if isinstance(valor, bool):
            return defecto
        try:
            valor = float(valor)
            return min(maximo, max(minimo, valor)) if math.isfinite(valor) else defecto
        except (ValueError, TypeError):
            return defecto
    return int(numero('lote_max_audios', 2, 1, 20)), numero('lote_max_segundos', 180, 1, 3600)


def formar(cola, primero, cfg, duracion):
    max_audios, presupuesto = limites(cfg)
    def costo(n):
        try:
            d = float(duracion(n))
            return d if math.isfinite(d) and d > 0 else presupuesto
        except (ValueError, TypeError, OSError):
            return presupuesto
    lote = [primero]
    total = costo(primero)
    while len(lote) < max_audios and total < presupuesto:
        # Solo inspección; los productores pueden agregar al final, nunca se reordena FIFO.
        with cola.mutex:
            siguiente = cola.queue[0] if cola.queue else None
        if siguiente is None:
            break
        d = costo(siguiente)
        if siguiente not in lote and total + d > presupuesto:
            break
        try:
            n = cola.get_nowait()
        except queue.Empty:
            break
        if n not in lote:
            lote.append(n)
            total += d
    return lote
