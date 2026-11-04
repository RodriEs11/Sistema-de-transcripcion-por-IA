"""Borrado de casos: permisos (quién puede borrar qué), archivos que se apartan antes de borrar para poder
volver atrás si algo falla, y la coordinación con la cola (un caso en espera se saltea; uno en proceso no se borra).

Viene de servidor.py (docs/refactor.md, etapa 6a). Lo crea servidor.configurar()."""

import time

from transcripcion.base import registro as L
from transcripcion.casos.repositorio import EXT_AUDIO, LOCAL, SUFIJOS_CASO


class Borrado:
    """Borra los archivos de un caso (`casos`), su Word (en `informes`) y lo saca de la cola (`proc`).
    `remoto` es el acceso remoto (libera el bloqueo del caso)."""

    def __init__(self, casos, proc, informes, remoto):
        self.casos = casos
        self.proc = proc
        self.informes = informes
        self.remoto = remoto

    def puede_borrar(self, n, pc, remoto):
        """None si se puede borrar; si no, el motivo. Las PC del trabajo solo borran lo que enviaron ellas."""
        if remoto and (self.casos.origen_de(n) != pc or pc == LOCAL):
            return "Solo se pueden borrar los informes que llegaron desde esta PC."
        with self.proc.lock:
            e = self.proc.estado.get(n, {}).get("estado")
        if e in ("transcribiendo", "generando"):
            return "Se está procesando ahora: esperá a que termine para borrarlo."
        otro = self.remoto.bloqueado_por(n, pc)
        if otro:
            return f"Lo está revisando {otro}."
        return None

    def _archivos_audio(self, n):
        """Audios del caso que se pueden borrar: solo los que están en la carpeta de audios nuevos (un audio
        procesado desde el modo consola puede estar en cualquier carpeta de la usuaria: ese no se toca)."""
        base = self.casos.nuevos.resolve()
        out = [self.casos.nuevos / f"{n}{e}" for e in EXT_AUDIO if (self.casos.nuevos / f"{n}{e}").exists()]
        a = self.casos.ruta_audio(n)
        if a is not None and a.resolve().parent == base and a not in out:
            out.append(a)
        return out

    def _apartar(self, p):
        """Renombra el archivo para borrarlo (falla si está abierto, p. ej. el Word). Reintenta un poco por si
        justo se estaba leyendo el audio."""
        tmp = p.with_name(p.name + ".borrando")
        for i in range(6):
            try:
                p.replace(tmp)
                return tmp
            except FileNotFoundError:
                return None
            except PermissionError:
                if i == 5:
                    raise
                time.sleep(0.25)

    def borrar_caso(self, n, quien=LOCAL, remoto=False):
        """Borra el caso: audio, archivos de revisión y Word. Lo aprendido (ejemplos, historial, correcciones)
        se conserva. Devuelve None si salió bien o el motivo por el que no se borró."""
        motivo = self.puede_borrar(n, quien, remoto)
        if motivo:
            return motivo
        hay = (
            any(n == p.stem for p in self.casos.nuevos.iterdir() if p.suffix.lower() in EXT_AUDIO)
            or any((self.casos.datos / f"{n}{s}").exists() for s in SUFIJOS_CASO)
            or (self.informes / f"{n}.docx").exists()
        )
        if not hay:
            if self.proc.duradera is not None and self.proc.duradera.obtener(n) is not None:
                restos = [self.informes / f"{n}.docx.borrando"] + [
                    self.casos.nuevos / f"{n}{e}.borrando" for e in EXT_AUDIO
                ]
                if any(p.exists() for p in restos):
                    return "Hay archivos apartados de un borrado interrumpido. Conserválos y revisá su recuperación."
                with self.proc.lock:
                    if self.proc.estado.get(n, {}).get("estado") in ("transcribiendo", "generando"):
                        return "Se está procesando ahora: esperá a que termine para borrarlo."
                    self.proc.duradera.preparar_borrado(n)
                    self.proc.borrados.add(n)
                self.proc.duradera.cancelar_borrado(n)
                with self.proc.lock:
                    self.proc.estado.pop(n, None)
                with self.proc.pausa_cv:
                    self.proc.pausas.pop(n, None)
                    self.proc.pausa_cv.notify_all()
                self.proc.encolado.pop(n, None)
                return None
            return "Ese informe ya no existe."
        with self.proc.lock:  # que el trabajador no lo empiece justo ahora
            if self.proc.estado.get(n, {}).get("estado") in ("transcribiendo", "generando"):
                return "Se está procesando ahora: esperá a que termine para borrarlo."
            previo_duradero = self.proc.duradera.preparar_borrado(n) if self.proc.duradera is not None else None
            self.proc.borrados.add(n)
            previo = dict(self.proc.estado.get(n, {}))
        nombre_vis, estado = self.casos.visible(n), previo.get("estado")
        if estado in (None, "listo", "nuevo"):
            estado = (
                "revisado"
                if (self.casos.datos / f"{n}.final.txt").exists()
                else ("para revisar" if (self.casos.datos / f"{n}.informe_ia.txt").exists() else "sin procesar")
            )
        # primero se apartan el Word y el audio: si alguno está abierto no se borra nada
        apartados = []
        try:
            for p in [self.informes / f"{n}.docx"] + self._archivos_audio(n):
                if p.exists():
                    t = self._apartar(p)
                    if t:
                        apartados.append((p, t))
        except PermissionError as ex:
            for p, t in apartados:
                try:
                    t.replace(p)
                except OSError:
                    pass
            if self.proc.duradera is not None:
                self.proc.duradera.revertir_borrado(n, previo_duradero)
            with self.proc.lock:
                self.proc.borrados.discard(n)
            if previo.get("estado") in ("en cola", "en pausa"):  # pudo haber sido salteado durante el intento
                self.proc.encolar(n, forzar=True)
            cual = "el Word" if str(getattr(ex, "filename", "")).lower().endswith(".docx") else "el audio"
            L.aviso("CASO", f"{quien} quiso borrar {nombre_vis}, pero {cual} está abierto en otro programa.")
            return f"No se pudo borrar: {cual} está abierto en otro programa. Cerralo y volvé a intentar."
        for _, t in apartados:
            t.unlink(missing_ok=True)
        for s in SUFIJOS_CASO:
            (self.casos.datos / f"{n}{s}").unlink(missing_ok=True)
        (self.informes / "revision" / f"{n}.html").unlink(missing_ok=True)  # revisión del modo consola
        self.remoto.quitar_huellas(self.casos.datos, n)
        self.remoto.BLOQUEOS.pop(n, None)
        if self.proc.duradera is not None:
            self.proc.duradera.cancelar_borrado(n)
        with self.proc.lock:
            self.proc.estado.pop(n, None)
        with self.proc.pausa_cv:  # si estaba en pausa, el trabajador se despierta, ve que se borró y sigue con otro
            self.proc.pausas.pop(n, None)
            self.proc.pausa_cv.notify_all()
        for d in (self.proc.encolado, self.casos.duraciones, self.casos.estudios_cache):
            d.pop(n, None)
        L.estado(cola=self.proc.en_proceso())
        L.info(
            "CASO", f"{quien} borró {nombre_vis} ({estado}): audio, informe y Word. Lo que aprendió la IA se conserva."
        )
        return None
