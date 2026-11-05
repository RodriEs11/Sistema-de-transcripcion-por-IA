"""Recepción de audios: «Cargar audio» de la página y audios que manda la app del trabajo."""

import hashlib
from pathlib import Path

from transcripcion.acceso import remoto as R
from transcripcion.acceso import usuarios as U
from transcripcion.base import registro as L
from transcripcion.base.formatos import duracion_wav
from transcripcion.base.persistencia import escribir_atomico
from transcripcion.casos.repositorio import EXT_AUDIO, LOCAL


def subir(h, pedido):
    """POST /api/subir."""
    sis = h.sis
    q = pedido.q
    nombre_arch = Path(q.get("archivo", [""])[0]).name
    if Path(nombre_arch).suffix.lower() not in EXT_AUDIO:
        return h._json({"error": "Formato de audio no soportado"}, 400)
    if h.remoto:  # desde otra PC: nombre único y se anota de qué PC vino
        r, err = guardar_audio_nuevo(h, nombre_arch, h._body())
        return h._json(r) if r else h._json({"error": err}, 422)
    destino = sis.nuevos / nombre_arch
    cuerpo = h._body()
    escribir_atomico(sis.datos / f"{destino.stem}.origen.txt", LOCAL)
    sis.casos.poner_usuario_caso(destino.stem, h.usuario)
    med = q.get("medico", [""])[0].strip()
    if med:
        escribir_atomico(sis.datos / f"{destino.stem}.medico.txt", med)
    escribir_atomico(destino, cuerpo)
    sis.proc.encolar(destino.stem)
    anunciar_audio(sis, destino.stem, cuerpo, "en esta PC")
    return h._json({"ok": True, "nombre": destino.stem})


def guardar_audio_nuevo(h, original, cuerpo, huella=None):
    """Guarda un audio llegado de otra PC con nombre único y lo pone en cola."""
    sis = h.sis
    with sis.recibir_audio_lock:
        return recibir_audio_serializado(h, original, cuerpo, huella)


def recibir_audio_serializado(h, original, cuerpo, huella=None):
    sis = h.sis
    if len(cuerpo) < 44 or cuerpo[:4] != b"RIFF" or cuerpo[8:12] != b"WAVE":
        if Path(original).suffix.lower() == ".wav":
            L.aviso(
                "AUDIO",
                f"{h.pc} envió «{original}» ({L.tamano(len(cuerpo))}) pero no es un WAV "
                f"válido (¿llegó incompleto?). No se procesa.",
            )
            return None, "El archivo no es un WAV válido (¿llegó incompleto?)"
    hs = hashlib.sha256(cuerpo).hexdigest()
    if huella and huella.lower() != hs:
        L.aviso("AUDIO", f"«{original}» de {h.pc} llegó dañado en el viaje; la aplicación lo vuelve a enviar.")
        return None, "El audio llegó dañado: se vuelve a enviar."
    previo = R.buscar_huella(sis.datos, hs)
    if previo and sis.casos.ruta_audio(previo):
        if previo not in sis.proc.estado:
            sis.proc.encolar(previo)  # reintento tras una caída entre recepción duradera y encolado
        L.info(
            "AUDIO",
            f"{h.pc} envió «{original}», que ya estaba cargado como {sis.casos.visible(previo)}. "
            f"No se procesa de nuevo.",
        )
        return {"ok": True, "nombre": previo, "duplicado": True}, None
    ext = Path(original).suffix.lower()
    nombre = R.nombre_unico(h.pc, original, lambda n: any((sis.nuevos / f"{n}{e}").exists() for e in EXT_AUDIO))
    escribir_atomico(sis.datos / f"{nombre}.origen.txt", h.pc)
    escribir_atomico(sis.datos / f"{nombre}.original.txt", Path(original).name)
    # «Cargar audio» desde la página: el que lo sube; la app sola: el que está usando la página en esa PC
    sis.casos.poner_usuario_caso(
        nombre, getattr(h, "usuario", None) or (R.usuario_activo(h.pc) if U.hay_usuarios() else None)
    )
    # Publicar al final: el vigilante no debe leer un WAV parcial o sin metadatos.
    escribir_atomico(sis.nuevos / f"{nombre}{ext}", cuerpo)
    R.guardar_huella(sis.datos, hs, nombre)
    sis.proc.encolar(nombre)
    anunciar_audio(sis, nombre, cuerpo, f"de {h.pc}")
    return {"ok": True, "nombre": nombre, "duplicado": False}, None


def anunciar_audio(sis, nombre, cuerpo, desde):
    """Línea de «audio recibido» con duración, tamaño, médico y lugar en la cola."""
    L.contar("recibidos")
    dur = duracion_wav(datos=cuerpo)
    med = sis.casos.medico_de(nombre)
    partes = [
        f"«{sis.casos.titulo_de(nombre)}»",
        L.mmss(dur) if dur else None,
        L.tamano(len(cuerpo)),
        f"médico {med}" if med else "sin médico elegido",
    ]
    pos = sis.proc.en_proceso()
    L.ok(
        "AUDIO",
        f"Audio recibido {desde}: "
        + " · ".join(x for x in partes if x)
        + (f" · en cola ({pos} en proceso)" if pos > 1 else ""),
    )
