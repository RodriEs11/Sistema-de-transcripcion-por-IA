"""Archivos de cada caso en Informes/revision/datos (y su audio en Audios_nuevos): nombre para mostrar,
origen, médico, transcriptor, estilo, estudios, duración, tiempo de revisión, voz y avisos para la lista.

Viene de servidor.py (docs/refactor.md, etapa 5). El servidor crea un `Casos` en configurar(); una prueba arma
el suyo con carpetas temporales: `Casos(datos, nuevos)`."""

import json
import os
import re
import sys
import threading
import time
from pathlib import Path

from transcripcion.acceso import usuarios as U
from transcripcion.base import registro as L
from transcripcion.base.formatos import duracion_wav, mmss
from transcripcion.base.persistencia import escribir_atomico
from transcripcion.casos import borradores as BOR
from transcripcion.casos.indice import IndiceCasos
from transcripcion.conocimiento import plantillas as PL

LOCAL = "Servidor"  # nombre con el que aparecen los casos subidos en la misma PC del servidor
EXT_AUDIO = {".wav", ".mp3", ".m4a", ".ogg", ".flac", ".wma", ".aac", ".opus"}
# Archivos que puede tener un caso en Informes/revision/datos (listado, firma del índice y borrado)
SUFIJOS_CASO = (
    ".procesamiento.json",
    ".transcripcion_cache.json",
    ".rendimiento.json",
    ".json",
    ".dictado.txt",
    ".informe_ia.txt",
    ".marcas.json",
    ".borrador.html",
    ".borrador.json",
    ".final.txt",
    ".medico.txt",
    ".audio.txt",
    ".ejemplo.txt",
    ".onda.json",
    ".origen.txt",
    ".original.txt",
    ".paciente.json",
    ".formato.json",
    ".omisiones_ok.json",
    ".revision.json",
    ".voz.json",
    ".usuario.txt",
    ".estilo.txt",
)


REV_MAX_POR_PEDIDO = 600  # lo que puede juntar la página si se cortó la conexión un rato

COLOR_TIPO = {
    "numero": "rojo",
    "completar": "rojo",
    "dudoso": "amarillo",
    "bajaconf": "amarillo",
    "verificar": "turq",
    "plantilla": "gris",
}


class Casos:
    """Lectura y escritura de los archivos de los casos. Guarda en memoria solo cachés (estudios, duraciones,
    resumen de voz) y los candados de los archivos que se actualizan desde varios hilos."""

    def __init__(self, datos, nuevos):
        self.datos = datos
        self.nuevos = nuevos
        self.indice = IndiceCasos()  # metadatos del listado, por firma de los archivos de cada caso
        self.estudios_cache = {}  # nombre -> (firma del archivo, "Mamografía + Eco mamaria")
        self.duraciones = {}  # nombre -> duración del audio en segundos (cache)
        # ------------------------------------------------- tiempo de revisión
        # La página cuenta los segundos en que el caso está abierto y alguien lo está trabajando (teclado, mouse o audio
        # sonando en el último minuto) y los manda con cada renovación del bloqueo, al cerrar y al guardar. Se acumulan
        # acá, por caso, aunque se abra varias veces o desde otra PC. Al guardar se anotan en actividad.csv
        # (columna revision_s).
        self.rev_lock = threading.Lock()
        # ------------------------------------------------- médico reconocido por la voz (voces.py)
        # <caso>.voz.json = {"h": huella, "seg": segundos de voz, "det": resultado de la detección, "medico_por": quién
        # puso el médico del caso ("voz" = se reconoció solo, "usuaria" = se eligió al revisar, "pc" = el médico elegido
        # para los audios de esa PC, "" = sin médico), "medico_ia": con qué médico armó el informe la IA}.
        # La muestra de voz de un médico se guarda en voces/huellas.json recién cuando se guarda el informe con ese
        # médico (o cuando se etiqueta a mano desde «Agrupar voces»).
        self.voz_cache = {}
        self.voz_lock = threading.Lock()

    def titulo_de(self, n):
        """Nombre para mostrar: el nombre original del audio que llegó de otra PC."""
        f = self.datos / f"{n}.original.txt"
        return Path(f.read_text(encoding="utf-8").strip()).stem if f.exists() else n

    def estudios_de(self, n):
        """Estudios del informe, abreviados, para la lista (del final si ya se guardó; si no, de la IA)."""
        f = self.datos / f"{n}.final.txt"
        if not f.exists():
            f = self.datos / f"{n}.informe_ia.txt"
        try:
            st = f.stat()
        except OSError:
            return None
        firma = (f.name, st.st_size, st.st_mtime_ns)
        c = self.estudios_cache.get(n)
        if c and c[0] == firma:
            return c[1]
        try:
            t = PL.estudios_del_informe(f.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError):
            return None
        self.estudios_cache[n] = (firma, t)
        return t

    def origen_de(self, n):
        f = self.datos / f"{n}.origen.txt"
        return f.read_text(encoding="utf-8").strip() if f.exists() else LOCAL

    def duracion_de(self, n):
        """Duración del audio en segundos (de la cabecera del WAV; si no es WAV, del final de la transcripción)."""
        if self.duraciones.get(n) is None:
            a = self.ruta_audio(n)
            d = duracion_wav(ruta=a) if a else None
            if d is None and (self.datos / f"{n}.json").exists():
                try:
                    pal = json.loads((self.datos / f"{n}.json").read_text(encoding="utf-8")).get("palabras") or []
                    d = pal[-1].get("fin") if pal else None
                except (ValueError, OSError):
                    d = None
            if d is None:
                return None  # no se guarda: se vuelve a intentar cuando esté transcrito
            self.duraciones[n] = round(d, 1)
        return self.duraciones[n]

    def visible(self, n):
        """Cómo se nombra un caso en la ventana del servidor: «tmp7957» (info-01)."""
        try:
            return f"«{self.titulo_de(n)}» ({self.origen_de(n)})"
        except OSError:
            return f"«{n}»"

    def datos_csv(self, n):
        return {
            "caso": n,
            "audio_original": self.titulo_de(n),
            "pc": self.origen_de(n),
            "medico": self.medico_de(n),
            "estudios": self.estudios_de(n),
            "usuario": U.nombre_de(self.usuario_de(n)),
        }

    def sumar_revision(self, n, seg_, pc):
        try:
            seg_ = float(seg_ or 0)
        except (TypeError, ValueError):
            return
        if not (0 < seg_ <= REV_MAX_POR_PEDIDO) or not (self.datos / f"{n}.dictado.txt").exists():
            return
        f = self.datos / f"{n}.revision.json"
        with self.rev_lock:
            try:
                d = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
            except (OSError, ValueError):
                d = {}
            d["s"] = round(float(d.get("s", 0)) + seg_, 1)
            por = d.setdefault("por_pc", {})
            por[pc] = round(float(por.get(pc, 0)) + seg_, 1)
            d.setdefault("desde", time.strftime("%Y-%m-%d %H:%M:%S"))
            d["ultimo"] = time.strftime("%Y-%m-%d %H:%M:%S")
            try:
                f.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
            except OSError:
                L.debug("CASO", f"No se pudo anotar el tiempo de revisión de {n}", det=[repr(sys.exc_info()[1])])

    def revision_de(self, n):
        """Segundos de revisión activa acumulados del caso (None si no se midió)."""
        f = self.datos / f"{n}.revision.json"
        try:
            return round(float(json.loads(f.read_text(encoding="utf-8")).get("s", 0))) if f.exists() else None
        except (OSError, ValueError, TypeError):
            return None

    # ----------------------------------------------------------------- casos
    def ruta_audio(self, nombre):
        f = self.datos / f"{nombre}.audio.txt"
        if f.exists():
            p = Path(f.read_text(encoding="utf-8").strip())
            if p.exists():
                return p
        for p in self.nuevos.iterdir():
            if p.suffix.lower() in EXT_AUDIO and p.stem == nombre:
                return p
        return None

    def medico_de(self, n):
        f = self.datos / f"{n}.medico.txt"
        return f.read_text(encoding="utf-8").strip() if f.exists() else ""

    # ------------------------------------------------- transcriptor del caso
    # <caso>.usuario.txt = con el estilo de quién se arma (el que estaba usando la página en esa PC al llegar el audio,
    # o el que pidió «Volver a generar»). <caso>.estilo.txt = con el estilo de quién lo armó la IA la última vez
    # (vacío = estilo general). Si el que lo abre es otro, la página avisa y ofrece regenerarlo con su estilo.
    def usuario_de(self, n):
        f = self.datos / f"{n}.usuario.txt"
        u = f.read_text(encoding="utf-8").strip() if f.exists() else ""
        return u if u and U.existe(u) else ""

    def poner_usuario_caso(self, n, usuario):
        f = self.datos / f"{n}.usuario.txt"
        if usuario:
            escribir_atomico(f, usuario)
        else:
            f.unlink(missing_ok=True)

    def estilo_de(self, n):
        """None si nunca se generó con la información de estilo (casos anteriores a los usuarios)."""
        f = self.datos / f"{n}.estilo.txt"
        return f.read_text(encoding="utf-8").strip() if f.exists() else None

    def voz_de(self, n):
        try:
            return json.loads((self.datos / f"{n}.voz.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def guardar_voz(self, n, v):
        f = self.datos / f"{n}.voz.json"
        tmp = f.with_name(f.name + ".nuevo")
        tmp.write_text(json.dumps(v, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        os.replace(tmp, f)
        self.voz_cache.pop(n, None)

    def anotar_voz(self, n, **campos):
        """Cambia campos de <caso>.voz.json (si existe)."""
        with self.voz_lock:
            v = self.voz_de(n)
            if v is not None:
                v.update(campos)
                self.guardar_voz(n, v)

    def resumen_avisos(self, n, m):
        """Cuántas marcas de cada color quedan y qué datos faltan (para la lista y el modo compacto).
        Si hay borrador se cuentan las marcas que siguen en él (las ya revisadas no cuentan)."""
        r = {"rojo": 0, "amarillo": 0, "turq": 0, "gris": 0, "faltan": [], "huecos": []}
        borrador = BOR.leer(self.datos, n)
        if borrador["html"] is not None:
            h = borrador["html"]
            for tipo in re.findall(r'<mark class="m-(\w+)', h):
                if tipo in COLOR_TIPO:
                    r[COLOR_TIPO[tipo]] += 1
            for tipo in re.findall(r'class="ln[^"]*\bl-(plantilla|verificar)\b', h):
                r[COLOR_TIPO[tipo]] += 1
        else:
            for ln in m.get("lineas", []):
                if ln.get("linea"):
                    r[COLOR_TIPO[ln["linea"]]] += 1
                for sg in ln.get("segs", []):
                    if sg.get("tipo") in COLOR_TIPO:
                        r[COLOR_TIPO[sg["tipo"]]] += 1
        ok = set(borrador["omisiones_ok"])
        for o in m.get("omisiones", []):
            if o["dato"] in ok:
                continue
            if o.get("hueco"):
                r["huecos"].append(mmss(o.get("ini", o.get("seg") or 0)))
            else:
                r["faltan"].append(o["dato"])
        return r

    def revisado_en(self, n):
        """Cuándo se guardó el Word por última vez (para «Revisados hoy» en la pantalla de inicio)."""
        try:
            return (self.datos / f"{n}.final.txt").stat().st_mtime
        except OSError:
            return None

    def fecha_caso(self, n, audio, defecto):
        try:
            return (audio if audio else self.datos / f"{n}.informe_ia.txt").stat().st_mtime
        except OSError:
            return defecto

    def formato_de(self, nombre):
        """Formato elegido a mano en la vista previa (negrita, cursiva, color, alineación), o None."""
        f = self.datos / f"{nombre}.formato.json"
        try:
            return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None
        except (OSError, ValueError):
            return None
