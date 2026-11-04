"""«Guardar Word y aprender»: arma el Word final del caso, lo publica de forma atómica, registra la actividad y deja
el aprendizaje (ejemplo, historial, voz, correcciones) en la cola persistente. También la vista previa del Word.

Viene de servidor.py (docs/refactor.md, etapa 6a). Lo crea servidor.configurar()."""

import io
import time
from pathlib import Path

from transcripcion.acceso import usuarios as U
from transcripcion.base import registro as L
from transcripcion.base.formatos import mmss
from transcripcion.base.persistencia import escribir_atomico
from transcripcion.casos.repositorio import LOCAL
from transcripcion.conocimiento import plantillas as PL
from transcripcion.controles import marcas as MAR
from transcripcion.informe.word import aplicar_formato, escribir_docx, pagina, parrafos_docx, texto_parrafo


class Guardado:
    """Usa `casos` (archivos), `voces` (muestra de voz al guardar), `informes` (carpeta de los Word) y `fin_lock` (un
    guardado a la vez). `aprendizaje` es la cola persistente (se asigna después de crearla, porque sus funciones
    son métodos de este objeto) y `aprender` el módulo que registra ejemplos y correcciones. `estadisticas` es el módulo de
    estadísticas (se invalida su caché al guardar)."""

    def __init__(self, cfg, informes, casos, voces, fin_lock, aprender, estadisticas):
        self.cfg = cfg
        self.informes = informes
        self.casos = casos
        self.voces = voces
        self.fin_lock = fin_lock
        self.aprender = aprender
        self.estadisticas = estadisticas
        self.aprendizaje = None  # ColaAprendizaje: la asigna servidor.configurar() al crearla

    # ------------------------------------------------------------- finalizar
    def finalizar(self, nombre, texto, quien=LOCAL, usuario=None):
        with self.fin_lock:  # solo publicación Word + final + tarea duradera; aprendizaje fuera de este lock
            return self._finalizar(nombre, texto, quien, usuario)

    def _finalizar(self, nombre, texto, quien=LOCAL, usuario=None):
        pct_corregido = self.aprender.pct_corregido
        final, marcado = self.texto_a_marcado(texto)
        ia = (self.casos.datos / f"{nombre}.informe_ia.txt").read_text(encoding="utf-8")
        dic = (self.casos.datos / f"{nombre}.dictado.txt").read_text(encoding="utf-8")
        pc = pct_corregido("\n".join(l.rstrip() for l in MAR.texto_limpio(ia).splitlines()), final)
        fin_f = self.casos.datos / f"{nombre}.final.txt"
        ya_guardado = fin_f.exists()
        reg = self.casos.datos / f"{nombre}.ejemplo.txt"
        clave = reg.read_text(encoding="utf-8").strip() if reg.exists() else time.strftime("%Y%m%d_%H%M%S_") + nombre
        documento = io.BytesIO()
        escribir_docx(marcado, documento, U.cfg_de(self.cfg, usuario), self.casos.formato_de(nombre))
        docx = self.informes / f"{nombre}.docx"
        escribir_atomico(docx, documento.getvalue())
        escribir_atomico(reg, clave)
        escribir_atomico(fin_f, final)
        self.aprendizaje.agregar(
            {
                "nombre": nombre,
                "dictado": dic,
                "ia": ia,
                "final": final,
                "clave": clave,
                "medico": self.casos.medico_de(nombre) or None,
                "docx": str(docx),
                "usuario": usuario,
                "mtime_ns": docx.stat().st_mtime_ns,
                "fecha": time.strftime("%Y-%m-%d %H:%M"),
            }
        )
        L.contar("guardados")
        vz = self.voces.resumen_voz(nombre)
        rev = self.casos.revision_de(nombre)
        por = f"{U.nombre_de(usuario)} ({quien})" if usuario else quien
        L.ok(
            "INFORME",
            f"{self.casos.visible(nombre)} {'guardado de nuevo' if ya_guardado else 'guardado'} por {por} · "
            f"{f'{pc * 100:.1f}'.replace('.', ',')}% corregido"
            + (f" · revisión {mmss(rev)}" if rev else "")
            + f" · Word {docx.name} · aprendizaje pendiente",
        )
        # el transcriptor que guarda (no necesariamente el del caso): por eso se pisa el «usuario» de datos_csv
        L.actividad(
            "guardado",
            **{**self.casos.datos_csv(nombre), "usuario": U.nombre_de(usuario) if usuario else ""},
            porcentaje_corregido=pc * 100,
            palabras_informe=len(final.split()),
            revision_s=rev,
            detalle=("guardado de nuevo" if ya_guardado else "guardado") + f" desde {quien}",
            **self.voces.campos_voz(vz),
        )
        self.estadisticas.invalidar()
        return {"docx": str(docx), "pct": round(pc * 100, 1), "aprendizaje": "pendiente"}

    def texto_a_marcado(self, texto):
        """Texto del editor -> (texto final limpio, líneas como las recibe el Word)."""
        lineas = [l.rstrip() for l in texto.replace("\r", "").split("\n")]
        while lineas and not lineas[0].strip():
            lineas.pop(0)
        final = "\n".join(lineas).strip()
        return final, [{"segs": [(l, None, None)], "linea": None, "titulo": PL.es_titulo(l)} for l in final.split("\n")]

    def vista_previa(self, texto, nombre=None, usuario=None):
        """Párrafos exactamente como quedan en el Word (mismo código que escribir_docx) + la hoja.
        b / a0 = negrita y alineación normales; a / r = con el formato elegido a mano (si hay).
        usuario: con el formato del Word propio del transcriptor."""
        _, marcado = self.texto_a_marcado(texto)
        cfg_u = U.cfg_de(self.cfg, usuario)
        pars = parrafos_docx(marcado, cfg_u)
        if nombre:
            aplicar_formato(pars, self.casos.formato_de(nombre))
        pars = [
            None
            if p is None
            else {"t": texto_parrafo(p), "b": p["negrita"], "a0": p["alin_def"], "a": p["alin"], "r": p.get("runs")}
            for p in pars
        ]
        return {
            "parrafos": pars,
            "pagina": pagina(cfg_u),
            "fuente": cfg_u["fuente"],
            "tamano": cfg_u["tamano_fuente"],
            "encabezado": int(cfg_u["lineas_vacias_para_encabezado"]),
        }

    def aplicar_aprendizaje(self, tarea):
        registrar_ejemplo, anotar_procesado = self.aprender.registrar_ejemplo, self.aprender.anotar_procesado
        registrar_ejemplo(
            tarea["nombre"],
            tarea["dictado"],
            tarea["ia"],
            tarea["final"],
            tarea["clave"],
            medico=tarea["medico"],
            recalcular=False,
            fecha=tarea["fecha"],
            usuario=tarea.get("usuario"),
        )
        docx = Path(tarea["docx"])
        if docx.exists() and docx.stat().st_mtime_ns == tarea["mtime_ns"]:
            anotar_procesado(docx, tarea["clave"])
        n = tarea["nombre"]
        fin = self.casos.datos / f"{n}.final.txt"
        if (
            fin.exists()
            and fin.read_text(encoding="utf-8") == tarea["final"]
            and self.casos.medico_de(n) == (tarea["medico"] or "")
        ):
            try:
                self.voces.muestra_al_guardar(n)
            except Exception:
                L.aviso("VOZ", "No se pudo registrar la muestra de voz del informe guardado.", exc=True)
        self.estadisticas.invalidar()

    def analizar_aprendizaje(self):
        analizar_correcciones = self.aprender.analizar_correcciones
        analizar_correcciones()
