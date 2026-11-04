"""Registro SQLite de tareas GPU. No importa el servidor ni carga modelos."""

import json
import os
import sqlite3
import tempfile
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

ACTIVOS = ("en cola", "transcribiendo", "generando", "en pausa")
ESTADOS = ACTIVOS + ("listo", "error", "borrando", "cancelado")


class ErrorCola(RuntimeError):
    """La persistencia no confirmó la operación; no continuar como si estuviese guardada."""


def validar_nombre(nombre):
    if not isinstance(nombre, str) or not nombre or any(x in nombre for x in ("/", "\\", "..", "\0")):
        raise ValueError("Nombre de tarea inválido")


class ColaProcesamiento:
    def __init__(self, ruta):
        self.ruta = Path(ruta)
        self.lock = threading.RLock()
        self.db = None
        self.dueno = None
        try:
            self.ruta.parent.mkdir(parents=True, exist_ok=True)
            # El lock del SO se libera incluso con os._exit/caída; el archivo no se borra.
            self.dueno = open(str(self.ruta) + ".lock", "a+b")
            self.dueno.seek(0, 2)
            if not self.dueno.tell():
                self.dueno.write(b"0")
                self.dueno.flush()
            self.dueno.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self.dueno.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.dueno.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.db = sqlite3.connect(self.ruta, timeout=5, isolation_level=None, check_same_thread=False)
            self.db.row_factory = sqlite3.Row
            self.db.execute("PRAGMA synchronous=FULL")
            with self.transaccion() as db:
                version = db.execute("PRAGMA user_version").fetchone()[0]
                if version not in (0, 1):
                    raise ErrorCola("Versión de cola desconocida; no se modifica.")
                if version == 0:
                    if db.execute(
                        "SELECT 1 FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                    ).fetchone():
                        raise ErrorCola("Base ajena sin versión; no se reemplaza.")
                    db.execute(
                        "CREATE TABLE tareas (orden INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT NOT NULL UNIQUE, "
                        "token TEXT NOT NULL, estado TEXT NOT NULL CHECK(estado IN ('en cola','transcribiendo',"
                        "'generando','en pausa','listo','error','borrando','cancelado')), "
                        "pausado INTEGER NOT NULL DEFAULT 0 CHECK(pausado IN (0,1)), encolado REAL NOT NULL)"
                    )
                    db.execute("CREATE INDEX tareas_estado_orden ON tareas(estado,orden)")
                    db.execute("CREATE TABLE meta (clave TEXT PRIMARY KEY, valor TEXT NOT NULL)")
                    db.execute("PRAGMA user_version=1")
                if db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                    raise ErrorCola("La cola no pasó la comprobación de integridad. Se conserva para recuperación.")
        except Exception as ex:
            self.cerrar()
            if isinstance(ex, ErrorCola):
                raise
            raise ErrorCola("No se pudo abrir la cola o ya tiene otro propietario.") from ex

    @contextmanager
    def transaccion(self):
        with self.lock:
            try:
                self.db.execute("BEGIN IMMEDIATE")
                yield self.db
                self.db.commit()
            except BaseException as ex:
                try:
                    self.db.rollback()
                except sqlite3.Error:
                    pass
                if isinstance(ex, sqlite3.Error):
                    raise ErrorCola("La cola no confirmó la escritura.") from ex
                raise

    def obtener(self, nombre):
        with self.lock:
            try:
                fila = self.db.execute("SELECT * FROM tareas WHERE nombre=?", (nombre,)).fetchone()
                return dict(fila) if fila else None
            except sqlite3.Error as ex:
                raise ErrorCola("No se pudo consultar la cola.") from ex

    def filas(self):
        with self.lock:
            return [
                dict(r)
                for r in self.db.execute(
                    "SELECT * FROM tareas WHERE estado IN "
                    "('en cola','transcribiendo','generando','en pausa','error','borrando') ORDER BY orden"
                )
            ]

    def _agregar(self, db, nombre, instante):
        db.execute("DELETE FROM tareas WHERE nombre=?", (nombre,))
        db.execute(
            "INSERT INTO tareas(nombre,token,estado,encolado) VALUES (?,?,'en cola',?)",
            (nombre, uuid.uuid4().hex, instante),
        )

    def solicitar(self, nombre, forzar=False):
        validar_nombre(nombre)
        with self.transaccion() as db:
            previo = self.obtener(nombre)
            if previo and previo["estado"] == "borrando":
                raise ErrorCola("El caso tiene un borrado pendiente; no se reactiva.")
            if previo and previo["estado"] in ACTIVOS and not forzar:
                return False
            self._agregar(db, nombre, time.time())
        return True

    def cambiar(self, nombre, estado):
        if estado not in ESTADOS:
            raise ValueError("Estado de cola inválido")
        with self.transaccion() as db:
            fila = self.obtener(nombre)
            if fila is None:
                raise ErrorCola("No existe una tarea duradera para ese caso.")
            if fila["estado"] not in ACTIVOS:
                return False
            db.execute("UPDATE tareas SET estado=? WHERE nombre=?", (estado, nombre))
        return True

    def pausa(self, nombre, valor):
        with self.transaccion() as db:
            fila = self.obtener(nombre)
            if not fila or fila["estado"] not in ACTIVOS or (valor and fila["estado"] == "generando"):
                return False
            db.execute("UPDATE tareas SET pausado=? WHERE nombre=?", (int(valor), nombre))
        return True

    def preparar_borrado(self, nombre):
        validar_nombre(nombre)
        with self.transaccion() as db:
            previo = self.obtener(nombre)
            if previo is None:
                self._agregar(db, nombre, time.time())
            db.execute("UPDATE tareas SET estado='borrando' WHERE nombre=?", (nombre,))
        return previo

    def revertir_borrado(self, nombre, previo):
        with self.transaccion() as db:
            if previo:
                db.execute(
                    "UPDATE tareas SET estado=?,pausado=? WHERE nombre=?", (previo["estado"], previo["pausado"], nombre)
                )
            else:
                db.execute("UPDATE tareas SET estado='cancelado' WHERE nombre=?", (nombre,))

    def cancelar_borrado(self, nombre):
        with self.transaccion() as db:
            db.execute("UPDATE tareas SET estado='cancelado',pausado=0 WHERE nombre=?", (nombre,))

    def importar_legacy(self, ruta, existe):
        ruta = Path(ruta)
        with self.transaccion() as db:
            if db.execute("SELECT 1 FROM meta WHERE clave='legacy_v1'").fetchone():
                return
            if ruta.exists():
                datos = json.loads(ruta.read_text(encoding="utf-8"))
                if not isinstance(datos, dict) or not isinstance(datos.get("nombres"), list):
                    raise ErrorCola("La instantánea anterior es inválida; se conserva para recuperar.")
                for nombre in datos["nombres"]:
                    validar_nombre(nombre)
                for nombre in datos["nombres"]:
                    if not self.obtener(nombre) and existe(nombre):
                        self._agregar(db, nombre, time.time())
            db.execute("INSERT INTO meta VALUES ('legacy_v1','1')")
        # Conservar el original: el marcador transaccional impide volver a importarlo.

    def respaldar(self, destino):
        with self.lock:
            respaldar(self.ruta, destino)

    def cerrar(self):
        if self.db is not None:
            self.db.close()
            self.db = None
        if self.dueno is not None:
            self.dueno.close()
            self.dueno = None


def respaldar(origen, destino):
    """Hot backup de solo lectura, publicable de forma exclusiva sin tomar la cola del servidor."""
    origen, destino = Path(origen).resolve(), Path(destino).resolve()
    if destino.exists():
        raise FileExistsError("El respaldo ya existe.")
    fd, temporal = tempfile.mkstemp(prefix=".cola-respaldo-", suffix=".tmp", dir=destino.parent)
    os.close(fd)
    fuente = copia = None
    try:
        fuente = sqlite3.connect(origen.as_uri() + "?mode=ro", uri=True, timeout=5)
        if fuente.execute("PRAGMA user_version").fetchone()[0] != 1:
            raise ErrorCola("Versión de cola desconocida.")
        copia = sqlite3.connect(temporal)
        fuente.backup(copia)
        if copia.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ErrorCola("Respaldo inválido; no se publica.")
        copia.close()
        copia = None
        with open(temporal, "r+b") as f:
            os.fsync(f.fileno())
        os.link(temporal, destino)  # mismo volumen, publicación exclusiva: no pisa otro respaldo
    finally:
        if copia is not None:
            copia.close()
        if fuente is not None:
            fuente.close()
        Path(temporal).unlink(missing_ok=True)
