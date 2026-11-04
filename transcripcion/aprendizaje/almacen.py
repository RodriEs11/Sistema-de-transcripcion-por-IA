"""Índices SQLite locales: historial por día/caso y contribuciones de correcciones por ejemplo."""

import csv
from contextlib import contextmanager
import io
import sqlite3
from pathlib import Path
from transcripcion.base.persistencia import escribir_atomico


def ruta_base(historial):
    return Path(historial).with_suffix(".sqlite3")


@contextmanager
def abrir(historial):
    ruta = ruta_base(historial)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(ruta, timeout=15)
    try:
        c.execute("BEGIN IMMEDIATE")
        version = c.execute("PRAGMA user_version").fetchone()[0]
        if version not in (0, 1):
            raise ValueError("Versión de base de aprendizaje desconocida")
        if version == 0:
            for sql in (
                "CREATE TABLE meta (k TEXT PRIMARY KEY, v TEXT NOT NULL)",
                "CREATE TABLE historial (dia TEXT, informe TEXT, fecha TEXT, palabras INTEGER, porcentaje_corregido TEXT, PRIMARY KEY(dia,informe))",
                "CREATE INDEX historial_fecha ON historial(fecha,informe)",
                "CREATE TABLE ejemplos (clave TEXT PRIMARY KEY, firma TEXT NOT NULL)",
                "CREATE TABLE contribuciones (clave TEXT, op TEXT, de TEXT, a TEXT, PRIMARY KEY(clave,op,de,a))",
                "CREATE TABLE frecuencias (op TEXT, de TEXT, a TEXT, n INTEGER NOT NULL, PRIMARY KEY(op,de,a))",
                "CREATE INDEX frecuentes ON frecuencias(n DESC,op DESC,de DESC,a DESC)",
                "CREATE TABLE procesados (ruta TEXT PRIMARY KEY, mtime REAL, ejemplo TEXT)",
            ):
                c.execute(sql)
            if Path(historial).exists():
                for r in csv.DictReader(io.StringIO(Path(historial).read_text(encoding="utf-8-sig")), delimiter=";"):
                    c.execute(
                        "INSERT OR REPLACE INTO historial VALUES (?,?,?,?,?)",
                        (r["fecha"][:10], r["informe"], r["fecha"], r["palabras"], r["porcentaje_corregido"]),
                    )
            c.execute("PRAGMA user_version=1")
        # quién revisó cada ejemplo (transcriptor); sin fila = ejemplo general (anterior a los usuarios)
        c.execute("CREATE TABLE IF NOT EXISTS ejemplo_usuario (clave TEXT PRIMARY KEY, usuario TEXT NOT NULL)")
        yield c
        c.commit()
    except BaseException:
        c.rollback()
        raise
    finally:
        c.close()


def anotar_historial(historial, nombre, fecha, palabras, porcentaje):
    with abrir(historial) as c:
        c.execute(
            "INSERT OR REPLACE INTO historial VALUES (?,?,?,?,?)", (fecha[:10], nombre, fecha, palabras, porcentaje)
        )


def leer_historial(historial):
    if not ruta_base(historial).exists():
        if not Path(historial).exists():
            return []
        return list(csv.DictReader(io.StringIO(Path(historial).read_text(encoding="utf-8-sig")), delimiter=";"))
    # Lectura sin inicializar/migrar ni solicitar lock de escritura.
    c = sqlite3.connect(ruta_base(historial).resolve().as_uri() + "?mode=ro", uri=True, timeout=15)
    try:
        c.row_factory = sqlite3.Row
        return [
            dict(r)
            for r in c.execute(
                "SELECT fecha,informe,palabras,porcentaje_corregido FROM historial ORDER BY fecha,informe"
            )
        ]
    finally:
        c.close()


def exportar_historial(historial, destino):
    salida = io.StringIO(newline="")
    w = csv.DictWriter(salida, fieldnames=["fecha", "informe", "palabras", "porcentaje_corregido"], delimiter=";")
    w.writeheader()
    w.writerows(leer_historial(historial))
    escribir_atomico(destino, salida.getvalue().encode("utf-8-sig"))


def actualizar_ejemplo(c, clave, firma, calcular):
    anterior = c.execute("SELECT firma FROM ejemplos WHERE clave=?", (clave,)).fetchone()
    if anterior and anterior[0] == firma:
        return False
    cambios = set(calcular())
    for op, de, a in c.execute("SELECT op,de,a FROM contribuciones WHERE clave=?", (clave,)).fetchall():
        c.execute("UPDATE frecuencias SET n=n-1 WHERE op=? AND de=? AND a=?", (op, de, a))
        c.execute("DELETE FROM frecuencias WHERE op=? AND de=? AND a=? AND n=0", (op, de, a))
    c.execute("DELETE FROM contribuciones WHERE clave=?", (clave,))
    for op, de, a in cambios:
        c.execute("INSERT INTO contribuciones VALUES (?,?,?,?)", (clave, op, de, a))
        c.execute("INSERT INTO frecuencias VALUES (?,?,?,1) ON CONFLICT(op,de,a) DO UPDATE SET n=n+1", (op, de, a))
    c.execute("INSERT OR REPLACE INTO ejemplos VALUES (?,?)", (clave, firma))
    return True


def quitar_ejemplo(c, clave):
    actualizar_ejemplo(c, clave, "", lambda: [])
    c.execute("DELETE FROM ejemplos WHERE clave=?", (clave,))
    c.execute("DELETE FROM ejemplo_usuario WHERE clave=?", (clave,))


def poner_usuario(c, clave, usuario):
    if usuario:
        c.execute("INSERT OR REPLACE INTO ejemplo_usuario VALUES (?,?)", (clave, usuario))
    else:
        c.execute("DELETE FROM ejemplo_usuario WHERE clave=?", (clave,))


def correcciones_por_fuente(c):
    """{(op, de, a): {usuario o '' (general): cantidad de ejemplos}}."""
    out = {}
    for op, de, a, u in c.execute(
        "SELECT co.op, co.de, co.a, COALESCE(eu.usuario, '') FROM contribuciones co "
        "LEFT JOIN ejemplo_usuario eu ON eu.clave = co.clave"
    ):
        d = out.setdefault((op, de, a), {})
        d[u] = d.get(u, 0) + 1
    return out
