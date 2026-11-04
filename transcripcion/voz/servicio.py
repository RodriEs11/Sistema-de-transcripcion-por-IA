"""Reconocimiento del médico por la voz en los casos: huella de cada audio, médico detectado, muestras al guardar,
agrupamiento de voces sin etiquetar y el hilo que completa lo pendiente al arrancar (ver docs/voz.md).

Viene de servidor.py (docs/refactor.md, etapa 6a). Lo crea servidor.configurar()."""

import json
import sys
import time

from transcripcion.base import registro as L
from transcripcion.base.formatos import mensaje_amigable, pct_voz
from transcripcion.casos import paciente as PAC
from transcripcion.procesamiento.estado import EN_PROCESO
from transcripcion.voz import huellas as VOZ


class ServicioVoz:
    """Usa las huellas de transcripcion.voz.huellas sobre los archivos de los casos (`casos`) y no toca casos en proceso
    (`proc`)."""

    def __init__(self, cfg, casos, proc):
        self.cfg = cfg
        self.casos = casos
        self.proc = proc

    def resumen_voz(self, n):
        """Lo que la lista y la barra del caso muestran del reconocimiento de voz (sin la huella)."""
        f = self.casos.datos / f"{n}.voz.json"
        try:
            mt = f.stat().st_mtime_ns
        except OSError:
            return None
        c = self.casos.voz_cache.get(n)
        if not c or c[0] != mt:
            v = self.casos.voz_de(n)
            if not v:
                return None
            d = v.get("det") or {}
            c = (
                mt,
                {
                    "estado": d.get("estado"),
                    "medico": d.get("medico"),
                    "puntaje": d.get("puntaje"),
                    "segundo": d.get("segundo"),
                    "puntaje2": d.get("puntaje2"),
                    "motivo": d.get("motivo"),
                    "muestras": d.get("muestras"),
                    "seg": v.get("seg"),
                    "por": v.get("medico_por") or "",
                    "medico_ia": v.get("medico_ia"),
                },
            )
            self.casos.voz_cache[n] = c
        r = dict(c[1])
        m = VOZ.muestra(n)
        r["muestra"] = m.get("medico") if m else None  # su voz ya cuenta como muestra de ese médico
        return r

    def calcular_voz(self, n, a, palabras, al_procesar=True):
        """Huella de voz del audio y detección del médico. Si el resultado es «seguro» y el caso no tiene médico
        elegido, lo asigna. Nunca frena el procesamiento: si algo falla, se anota y el caso sigue sin médico."""
        if not VOZ.modelo_listo():
            if L.una_vez("voz_sin_modelo", 3600):
                err = VOZ._DESCARGA.get("error")
                L.aviso(
                    "VOZ",
                    "El reconocimiento de voz todavía no está listo (falta el modelo"
                    + (f": {err}" if err else ", se está bajando")
                    + "). Este audio queda sin médico automático.",
                )
            return None
        t0 = time.time()
        try:
            h, seg = VOZ.huella_archivo(a, palabras, self.cfg)
        except Exception as ex:
            L.aviso(
                "VOZ",
                f"{self.casos.visible(n)}: no se pudo calcular la huella de voz ({mensaje_amigable(ex)}).",
                exc=True,
            )
            return None
        det = VOZ.detectar(h, excluir=n, cfg=self.cfg)
        with self.casos.voz_lock:
            prev = self.casos.voz_de(n) or {}
            med = self.casos.medico_de(n)
            por = prev.get("medico_por") or ""
            if med and por == "voz" and al_procesar:  # lo había puesto la voz: se vuelve a decidir
                (self.casos.datos / f"{n}.medico.txt").unlink(missing_ok=True)
                med = ""
            if med:
                por = por or "pc"
            elif det.get("estado") == "seguro":
                (self.casos.datos / f"{n}.medico.txt").write_text(det["medico"], encoding="utf-8")
                por = "voz"
            else:
                por = ""
            self.casos.guardar_voz(
                n,
                {
                    "v": 1,
                    "modelo": VOZ.VERSION_HUELLA,
                    "h": h,
                    "seg": seg,
                    "det": det,
                    "fecha": time.time(),
                    "medico_por": por,
                    "medico_ia": prev.get("medico_ia"),
                },
            )
        e = det.get("estado")
        if det.get("ranking"):
            L.debug(
                "VOZ",
                f"{self.casos.visible(n)}: huella en {L.seg(time.time() - t0)} con {seg} s de voz · "
                + ", ".join(f"{m} {pct_voz(p)}" for m, p in det["ranking"]),
            )
        if med and por != "voz":
            L.info(
                "VOZ",
                f"{self.casos.visible(n)}: médico ya elegido «{med}»"
                + (
                    f"; la voz se parece más a «{det['medico']}» ({pct_voz(det['puntaje'])})"
                    if det.get("medico") and det["medico"] != med
                    else f"; la voz coincide ({pct_voz(det.get('puntaje'))})"
                    if det.get("medico") == med
                    else ""
                )
                + ".",
            )
        elif e == "seguro":
            L.ok(
                "VOZ",
                f"{self.casos.visible(n)}: médico reconocido por la voz: «{det['medico']}» (parecido {pct_voz(det['puntaje'])}, "
                f"{L.plural(det['muestras'], 'muestra')}).",
            )
        elif e == "dudoso":
            L.info(
                "VOZ",
                f"{self.casos.visible(n)}: voz dudosa, ¿«{det['medico']}»? ({pct_voz(det['puntaje'])}; {det.get('motivo')}). "
                f"La IA usa la plantilla general; el médico se confirma al revisar.",
            )
        elif e == "corto":
            L.info("VOZ", f"{self.casos.visible(n)}: muy poca voz ({seg} s) para reconocer al médico.")
        else:
            L.info(
                "VOZ",
                f"{self.casos.visible(n)}: voz sin reconocer ({det.get('motivo')}). Elegí el médico al revisar: al "
                f"guardar, su voz queda registrada.",
            )
        return det

    def muestra_al_guardar(self, n):
        """Al guardar el Word: la voz del caso pasa a ser muestra del médico elegido (o deja de serlo si se quitó)."""
        v = self.casos.voz_de(n)
        if not v or not v.get("h") or v.get("modelo") != VOZ.VERSION_HUELLA:
            return v
        med = self.casos.medico_de(n)
        antes = VOZ.muestra(n)
        if not med:
            if antes:
                VOZ.quitar(n)
                L.info(
                    "VOZ",
                    f"{self.casos.visible(n)} se guardó sin médico: su voz ya no cuenta como muestra de «{antes['medico']}».",
                )
            return v
        k = VOZ.agregar(n, med, v["h"], "guardado", v.get("seg"))
        if not antes or antes.get("medico") != med:
            minimo = int(VOZ.parametros(self.cfg)["min_muestras"])
            L.ok(
                "VOZ",
                f"Voz de «{med}» registrada con {self.casos.visible(n)}: tiene {L.plural(k, 'muestra')}"
                + (
                    " (desde ahora se puede reconocer solo)"
                    if k == minimo
                    else f" (con {minimo} se reconoce solo)"
                    if k < minimo
                    else ""
                )
                + ".",
            )
        return v

    def actualizar_muestra(self, n, med):
        """El médico de un caso ya guardado se cambió a mano: se corrige su muestra de voz al momento."""
        v = self.casos.voz_de(n)
        if not v or not v.get("h") or v.get("modelo") != VOZ.VERSION_HUELLA:
            return
        if med:
            VOZ.agregar(n, med, v["h"], "guardado", v.get("seg"))
        else:
            VOZ.quitar(n)

    def casos_sin_etiquetar(self):
        """Casos sin médico cuya huella de voz todavía no es muestra de nadie (para «Agrupar voces»). Los que ya
        tienen médico no aparecen: su voz se registra sola al guardar el informe."""
        out = []
        with self.proc.lock:
            ocupados = {k for k, e in self.proc.estado.items() if e.get("estado") in EN_PROCESO}
        for f in self.casos.datos.glob("*.voz.json"):
            n = f.name[: -len(".voz.json")]
            if n in ocupados or VOZ.muestra(n) or self.casos.medico_de(n):
                continue
            v = self.casos.voz_de(n)
            if v and v.get("h") and v.get("modelo") == VOZ.VERSION_HUELLA:
                out.append((n, v))
        return out

    def ficha_caso(self, n):
        return {
            "nombre": n,
            "titulo": self.casos.titulo_de(n),
            "paciente": PAC.de(self.casos.datos, n),
            "medico": self.casos.medico_de(n),
            "audio": self.casos.ruta_audio(n) is not None,
            "origen": self.casos.origen_de(n),
            "revisado": (self.casos.datos / f"{n}.final.txt").exists(),
            "fecha": (lambda a: a.stat().st_mtime if a else None)(self.casos.ruta_audio(n)),
            "dur": self.casos.duracion_de(n),
        }

    def grupos_de_voces(self):
        items = self.casos_sin_etiquetar()
        hs = {n: v["h"] for n, v in items}
        grupos = []
        for g in VOZ.agrupar(list(hs.items()), self.cfg):
            det = VOZ.detectar(VOZ.centro([hs[x] for x in g]), cfg=self.cfg)
            fichas = []
            for x in g:
                try:
                    fichas.append(dict(self.ficha_caso(x), voz=self.resumen_voz(x)))
                except OSError:
                    pass
            fichas.sort(key=lambda c: c.get("fecha") or 0, reverse=True)
            grupos.append(
                {
                    "casos": fichas,
                    "sugerencia": {k: det.get(k) for k in ("estado", "medico", "puntaje", "segundo", "puntaje2")},
                }
            )
        return {"grupos": grupos, "total": len(items)}

    def hilo_voces(self):
        """Al arrancar: baja el modelo de voz si falta y calcula la huella de los casos que todavía no la tienen
        (sin cambiarles el médico). Los ya guardados con médico suman su voz como muestra."""
        if not VOZ.modelo_listo():
            L.info("VOZ", "Bajando el modelo de reconocimiento de voz (unos 26 MB, una sola vez)…")
            if not VOZ.descargar_modelo():
                L.aviso(
                    "VOZ",
                    f"No se pudo bajar el modelo de reconocimiento de voz ({VOZ._DESCARGA['error']}). Se vuelve "
                    f"a intentar al reiniciar el servidor; mientras tanto los audios quedan sin médico automático.",
                )
                return
            L.ok("VOZ", "Modelo de reconocimiento de voz listo.")
        hechos = sumadas = 0
        for f in sorted(self.casos.datos.glob("*.dictado.txt")):
            n = f.name[: -len(".dictado.txt")]
            v = self.casos.voz_de(n)
            if v and v.get("modelo") == VOZ.VERSION_HUELLA:
                continue
            while self.proc.trabajo.get("ocupado"):  # primero lo que está en la cola
                time.sleep(5)
            with self.proc.lock:
                if self.proc.estado.get(n, {}).get("estado") in EN_PROCESO:
                    continue
            a = self.casos.ruta_audio(n)
            if a is None:
                continue
            try:
                pal = json.loads((self.casos.datos / f"{n}.json").read_text(encoding="utf-8")).get("palabras")
                h, seg = VOZ.huella_archivo(a, pal, self.cfg)
            except Exception:
                L.debug(
                    "VOZ",
                    f"No se pudo calcular la huella de voz de {self.casos.visible(n)}.",
                    det=[repr(sys.exc_info()[1])],
                )
                continue
            med = self.casos.medico_de(n)
            with self.casos.voz_lock:
                self.casos.guardar_voz(
                    n,
                    {
                        "v": 1,
                        "modelo": VOZ.VERSION_HUELLA,
                        "h": h,
                        "seg": seg,
                        "det": VOZ.detectar(h, excluir=n, cfg=self.cfg),
                        "fecha": time.time(),
                        "medico_por": "pc" if med else "",
                        "medico_ia": med or None,
                    },
                )
            hechos += 1
            if h and med and (self.casos.datos / f"{n}.final.txt").exists() and not VOZ.muestra(n):
                VOZ.agregar(n, med, h, "revisado antes", seg)
                sumadas += 1
        if hechos:
            L.ok(
                "VOZ",
                f"Huella de voz calculada para {L.plural(hechos, 'caso anterior', 'casos anteriores')}"
                + (
                    f"; {L.plural(sumadas, 'informe ya guardado', 'informes ya guardados')} con médico "
                    f"{'sumó su voz' if sumadas == 1 else 'sumaron su voz'} a las muestras"
                    if sumadas
                    else ""
                )
                + ".",
            )

    def campos_voz(self, vz):
        """Columnas del reconocimiento de voz para actividad.csv."""
        if not vz:
            return {}
        return {
            "medico_voz": vz.get("medico") or "",
            "voz_estado": vz.get("estado") or "",
            "voz_puntaje": round(vz["puntaje"] * 100, 1) if vz.get("puntaje") is not None else None,
        }
