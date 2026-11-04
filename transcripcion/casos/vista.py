"""Lo que las pantallas muestran de los casos: la lista (con estado, avisos, voz y permisos), un caso abierto
(dictado, informe y marcas para la web) y la forma de onda del audio.

Viene de servidor.py (docs/refactor.md, etapa 6a). Lo crea servidor.configurar()."""

import json
import re

from transcripcion.acceso import usuarios as U
from transcripcion.base.formatos import mmss
from transcripcion.base.persistencia import escribir_atomico
from transcripcion.casos import borradores as BOR
from transcripcion.casos import paciente as PAC
from transcripcion.casos.repositorio import EXT_AUDIO, LOCAL, SUFIJOS_CASO
from transcripcion.controles import avisos as AV
from transcripcion.controles import marcas as MAR
from transcripcion.procesamiento.estado import EN_PROCESO
from transcripcion.texto.normalizacion import normalizar
from transcripcion.voz import huellas as VOZ

VERSION_MARCAS = 2  # 2: motivos detallados ("Dictado: 12 / Informe: 2") e inicio/fin de los huecos


class VistaCasos:
    """Arma las respuestas de la lista y del caso con `casos` (archivos), `proc` (estado en curso) y `voces`
    (resumen del médico por la voz). `inicio` es la hora de arranque del servidor (fecha por defecto)."""

    def __init__(self, casos, proc, voces, inicio, remoto):
        self.casos = casos
        self.proc = proc
        self.voces = voces
        self.inicio = inicio
        self.remoto = remoto  # acceso remoto: quién tiene abierto cada caso (bloqueado_por)

    def listar_casos(self, pc=LOCAL, remoto=False):
        nombres = {p.stem: p for p in self.casos.nuevos.iterdir() if p.suffix.lower() in EXT_AUDIO}
        with self.proc.lock:
            for n, e in self.proc.estado.items():
                if e.get("estado") in EN_PROCESO + ("error",):
                    nombres.setdefault(n, None)
        for f in self.casos.datos.glob("*.informe_ia.txt"):
            nombres.setdefault(f.name[: -len(".informe_ia.txt")], None)
        inventario = self.casos.indice.inventario(self.casos.datos)
        self.casos.indice.depurar(nombres)
        try:
            voz_st = VOZ.HUELLAS.stat()
            firma_voz = (voz_st.st_size, voz_st.st_mtime_ns)
        except FileNotFoundError:
            firma_voz = None
        casos = []
        esp = self.proc.esperas()
        for n in nombres:
            firma = (str(self.casos.datos), tuple(inventario.get(n + sufijo) for sufijo in SUFIJOS_CASO), firma_voz)

            # B023 revisado: dato() y sus lambdas se llaman en esta misma vuelta (IndiceCasos.obtener las usa
            # enseguida), nunca después, así que siempre ven el `n` y la `firma` de este caso (docs/refactor.md).
            def dato(campo, calcular):
                return self.casos.indice.obtener((n, campo), firma, calcular)  # noqa: B023

            with self.proc.lock:
                est = dict(self.proc.estado.get(n, {}))
            listo = (self.casos.datos / f"{n}.informe_ia.txt").exists()
            revisado = (self.casos.datos / f"{n}.final.txt").exists()
            if not est or est.get("estado") == "listo":
                est = {"estado": "revisado" if revisado else ("listo" if listo else "nuevo"), "msg": ""}
            marcas = avisos = None
            mf = self.casos.datos / f"{n}.marcas.json"
            if listo and mf.exists():
                try:
                    m = dato("marcas", lambda: json.loads(mf.read_text(encoding="utf-8")))  # noqa: B023
                    marcas = m.get("total")
                    if not revisado:
                        avisos = dato("avisos", lambda: self.casos.resumen_avisos(n, m))  # noqa: B023
                except (ValueError, OSError):
                    pass
            a = self.casos.ruta_audio(n)
            casos.append(
                {
                    "nombre": n,
                    "estado": est["estado"],
                    "msg": est.get("msg", ""),
                    "marcas": marcas,
                    "medico": dato("medico_de", lambda: self.casos.medico_de(n)),  # noqa: B023
                    "origen": dato("origen_de", lambda: self.casos.origen_de(n)),  # noqa: B023
                    "avisos": avisos,
                    "bloqueado_por": self.remoto.bloqueado_por(n, pc),
                    "titulo": dato("titulo_de", lambda: self.casos.titulo_de(n)),  # noqa: B023
                    "espera": esp.get(n),
                    "paciente": dato("paciente", lambda: PAC.de(self.casos.datos, n)),  # noqa: B023
                    "usuario": dato("usuario_de", lambda: self.casos.usuario_de(n)),  # noqa: B023
                    "estilo": dato("estilo_de", lambda: self.casos.estilo_de(n)),  # noqa: B023
                    "voz": dato("resumen_voz", lambda: self.voces.resumen_voz(n)),  # noqa: B023
                    "estudios": dato("estudios_de", lambda: self.casos.estudios_de(n)) if listo else None,  # noqa: B023
                    "dur": dato("duracion_de", lambda: self.casos.duracion_de(n)),  # noqa: B023
                    "revisado_en": self.casos.revisado_en(n) if revisado else None,
                    "puede_borrar": not (
                        remoto and (dato("origen_de", lambda: self.casos.origen_de(n)) != pc or pc == LOCAL)  # noqa: B023
                    )
                    and est["estado"] not in ("transcribiendo", "generando"),
                    "puede_pausar": not remoto and est["estado"] == "transcribiendo" and n not in self.proc.pausas,
                    "puede_reanudar": not remoto and (est["estado"] == "en pausa" or n in self.proc.pausas),
                    "pausa_pedida": n in self.proc.pausas and est["estado"] != "en pausa",
                    "fecha": self.casos.fecha_caso(n, a, est.get("t", self.inicio)),
                }
            )
        casos.sort(key=lambda c: c["fecha"], reverse=True)
        return casos

    def lineas_para_web(self, salida, dictado, palabras):
        marcado = MAR.marcar(salida, dictado, palabras)
        out = []
        for ln in marcado:
            texto = "".join(t for t, _, _ in ln["segs"])
            segs = []
            for t, tipo, mot in ln["segs"]:
                seg = {"t": t}
                if tipo:
                    seg.update(tipo=tipo, motivo=mot, seg=MAR.buscar_tiempo(t, palabras))
                segs.append(seg)
            out.append(
                {
                    "segs": segs,
                    "linea": ln["linea"],
                    "motivo": (ln.get("motivo") or MAR.MOTIVO_LINEA.get(ln["linea"])) if ln["linea"] else None,
                    "titulo": ln["titulo"],
                    "seg": MAR.buscar_tiempo(texto, palabras) if texto.strip() else None,
                }
            )
        total = sum(1 for linea in out if linea["linea"]) + sum(
            1 for linea in out for s in linea["segs"] if s.get("tipo")
        )
        return out, total

    def guardar_marcas(self, n, salida, dictado, palabras, huecos=None):
        lineas, total = self.lineas_para_web(salida, dictado, palabras)
        om = AV.omisiones(dictado, salida, palabras)
        om += [
            {
                "dato": f"posible parte no transcrita {mmss(h['ini'])}–{mmss(h['fin'])}",
                "seg": h["ini"] + 0.5,
                "hueco": True,
                "ini": h["ini"],
                "fin": h["fin"],
            }
            for h in (huecos or [])
        ]
        nuevos = AV.estudios_sin_plantilla(salida)
        escribir_atomico(
            self.casos.datos / f"{n}.marcas.json",
            json.dumps(
                {
                    "v": VERSION_MARCAS,
                    "lineas": lineas,
                    "omisiones": om,
                    "estudios_nuevos": nuevos,
                    "total": total + len(om),
                },
                ensure_ascii=False,
            ),
        )
        return lineas, om

    def cargar_caso(self, nombre):
        ia = self.casos.datos / f"{nombre}.informe_ia.txt"
        if not ia.exists():
            return None
        trans = json.loads((self.casos.datos / f"{nombre}.json").read_text(encoding="utf-8"))
        mf = self.casos.datos / f"{nombre}.marcas.json"
        m = json.loads(mf.read_text(encoding="utf-8")) if mf.exists() else {}
        if m.get("v") == VERSION_MARCAS:
            lineas, om = m["lineas"], m["omisiones"]
        else:
            lineas, om = self.guardar_marcas(
                nombre, ia.read_text(encoding="utf-8"), trans["texto"], trans["palabras"], trans.get("huecos")
            )
        borrador = BOR.leer(self.casos.datos, nombre)
        om_ok = borrador["omisiones_ok"]
        fin = self.casos.datos / f"{nombre}.final.txt"
        # cada palabra con su forma normalizada ("veintitrés" -> "23"), para ubicar cada línea del informe en el dictado
        palabras = [dict(w, n=re.sub(r"[^a-z0-9.]", "", normalizar(w["p"])).strip(".")) for w in trans["palabras"]]
        return {
            "nombre": nombre,
            "dictado": trans["texto"],
            "palabras": palabras,
            "lineas": lineas,
            "omisiones": om,
            "omisiones_ok": om_ok,
            "medico": self.casos.medico_de(nombre),
            "voz": self.voces.resumen_voz(nombre),
            "paciente": PAC.de(self.casos.datos, nombre),
            "titulo": self.casos.titulo_de(nombre),
            "estudios": self.casos.estudios_de(nombre),
            "dur": self.casos.duracion_de(nombre),
            "estudios_nuevos": AV.estudios_sin_plantilla(ia.read_text(encoding="utf-8")),
            "borrador": borrador["html"],
            "borrador_revision": borrador.get("revision", 0),
            "revisado": fin.exists(),
            "tiene_audio": self.casos.ruta_audio(nombre) is not None,
            "estilo": self._estilo_para_web(nombre),
        }

    def _estilo_para_web(self, n):
        e = self.casos.estilo_de(n)
        if e is None:
            return None
        return {"usuario": e, "nombre": U.nombre_de(e) if e else ""}

    def forma_de_onda(self, nombre, n=1600):
        """Picos del audio en n tramos (0-100) para dibujar la forma de onda. Se guarda en .onda.json."""
        a = self.casos.ruta_audio(nombre)
        if a is None:
            return None
        st = a.stat()
        firma = f"{st.st_size}-{int(st.st_mtime)}-{n}"
        cache = self.casos.datos / f"{nombre}.onda.json"
        if cache.exists():
            try:
                d = json.loads(cache.read_text(encoding="utf-8"))
                if d.get("firma") == firma:
                    return d
            except ValueError:
                pass
        import numpy as np

        from transcripcion.asr import whisper as W

        x = np.abs(W.cargar_audio(a))
        dur = len(x) / 16000.0
        if not len(x):
            return {"firma": firma, "dur": 0, "picos": []}
        k = max(1, len(x) // n)
        tramos = x[: (len(x) // k) * k].reshape(-1, k)
        picos = tramos.max(axis=1)
        ref = float(np.percentile(picos, 98)) or 1.0
        picos = np.clip(picos / ref, 0, 1) ** 0.7
        d = {"firma": firma, "dur": round(dur, 3), "picos": [int(round(v * 100)) for v in picos]}
        cache.write_text(json.dumps(d), encoding="utf-8")
        return d
