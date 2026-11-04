"""Placa de video (NVIDIA): memoria, carga y temperatura para el panel y la consola del servidor."""

import time

_CACHE = {"t": 0, "v": None}


def placa_de_video():
    """(texto, tono) con memoria en uso, carga y temperatura de la placa, o None."""
    try:
        import subprocess

        r = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.used,memory.total,utilization.gpu,temperature.gpu",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=4,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        nombre, usada, total, uso, temp = [x.strip() for x in r.stdout.strip().splitlines()[0].split(",")]

        def gb(m):
            return f"{int(m) / 1024:.1f}".replace(".", ",")

        nombre = nombre.replace("NVIDIA ", "").replace("GeForce ", "")
        # Algunos drivers informan la temperatura con decimales (p. ej. 51.12).
        tono = "aviso" if float(temp) >= 85 or int(usada) >= 0.97 * int(total) else None
        return f"{nombre} · memoria {gb(usada)} de {gb(total)} GB · uso {uso}% · {temp} °C", tono
    except Exception:
        return None


def lectura(simular=False, cada=3):
    """Última lectura de placa_de_video(), renovada cada `cada` segundos (la consulta tarda). En modo simulado no
    se consulta. La comparten el panel y el encabezado de la consola."""
    ahora = time.time()
    if not simular and ahora - _CACHE["t"] > cada:
        _CACHE["v"], _CACHE["t"] = placa_de_video(), ahora
    return _CACHE["v"]
