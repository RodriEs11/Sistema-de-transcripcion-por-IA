"""Índice de metadatos por firma de archivos; nunca cachea permisos ni estado de trabajos."""

import os
import threading


class IndiceCasos:
    def __init__(self):
        self.lock = threading.RLock()
        self.valores = {}

    @staticmethod
    def inventario(carpeta):
        resultado = {}
        with os.scandir(carpeta) as entradas:
            for entrada in entradas:
                try:
                    if entrada.is_file():
                        st = entrada.stat()
                        resultado[entrada.name] = (st.st_size, st.st_mtime_ns)
                except FileNotFoundError:
                    continue  # borrado concurrente
        return resultado

    def obtener(self, clave, firma, calcular):
        with self.lock:
            anterior = self.valores.get(clave)
            if anterior is not None and anterior[0] == firma:
                return anterior[1]
            valor = calcular()
            self.valores[clave] = (firma, valor)
            return valor

    def depurar(self, nombres):
        with self.lock:
            self.valores = {k: v for k, v in self.valores.items() if k[0] in nombres}
