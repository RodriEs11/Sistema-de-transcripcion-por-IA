"""Estado para el panel de administración: servidor, IA, PC, cola en vivo, casos abiertos, túnel y usuarios."""

import time

from transcripcion.acceso import admin as ADM
from transcripcion.acceso import remoto as R
from transcripcion.acceso import usuarios as U
from transcripcion.base import plataforma as P
from transcripcion.base import registro as L
from transcripcion.casos import paciente as PAC
from transcripcion.conocimiento import medicos as MED
from transcripcion.conocimiento import plantillas as PL
from transcripcion.operacion import app_cliente as A
from transcripcion.operacion import gpu as GPU
from transcripcion.procesamiento.estado import EN_PROCESO


def cola_en_vivo(sis):
    """Lo que se está procesando y lo que espera, en orden, con cuánto lleva y cuánto falta (aproximado)."""
    ahora = time.time()
    esp = sis.proc.esperas()
    with sis.proc.lock:
        enp = {n: dict(v) for n, v in sis.proc.estado.items() if v.get("estado") in EN_PROCESO}
        errores = sum(1 for v in sis.proc.estado.values() if v.get("estado") == "error")
    items = []
    for n in sorted(enp, key=lambda x: (esp.get(x) or {}).get("adelante", 0)):
        e, s_ = enp[n], esp.get(n) or {}
        msg = e.get("msg") or ""
        items.append(
            {
                "nombre": n,
                "titulo": sis.casos.titulo_de(n),
                "paciente": PAC.de(sis.datos, n),
                "pc": sis.casos.origen_de(n),
                "medico": sis.casos.medico_de(n),
                "estado": e.get("estado"),
                "msg": msg,
                "etapa_desde": s_.get("desde"),
                "adelante": s_.get("adelante"),
                "eta": s_.get("eta"),
                "en_cola": round(ahora - sis.proc.encolado[n]) if n in sis.proc.encolado else None,
                "dur": sis.casos.duracion_de(n),
                "espera_ia": e.get("estado") == "en cola" and msg.startswith("Esperando a la IA ("),
                "puede_pausar": e.get("estado") == "transcribiendo" and n not in sis.proc.pausas,
                "pausa_pedida": n in sis.proc.pausas and e.get("estado") != "en pausa",
            }
        )
    return {
        "items": items,
        "eta_total": max((i["eta"] or 0 for i in items), default=0),
        "errores": errores,
        "pausada": bool(sis.oper.reinicio.get("detener")),
        "en_pausa": bool(sis.proc.trabajo.get("en_pausa")),
        "tiempos": {
            "whisper_x": round(sis.proc.tiempos["whisper_x"], 3),
            "ia": round(sis.proc.tiempos["ia"], 1),
            "n": sis.proc.tiempos["n"],
        },
    }


def casos_abiertos(sis):
    """Casos que alguna PC tiene abiertos ahora (bloqueados para las demás)."""
    ahora, out = time.time(), []
    for n, b in sorted(list(R.BLOQUEOS.items()), key=lambda x: x[1].get("desde", x[1]["t"])):
        edad = ahora - b["t"]
        if edad >= R.BLOQUEO_SEG:
            continue
        out.append(
            {
                "nombre": n,
                "titulo": sis.casos.titulo_de(n),
                "paciente": PAC.de(sis.datos, n),
                "pc": b["pc"],
                "desde": b.get("desde", b["t"]),
                "senal": round(edad),
                "libera_en": round(R.BLOQUEO_SEG - edad),
                "rev": sis.casos.revision_de(n),
            }
        )
    return out


def estado_tunel(sis):
    t = R.URL_TUNEL
    if not sis.tunel["modo"]:
        e = "apagado"
    elif not R.configurado():
        e = "sin_contrasena"
    elif sis.tunel["error"]:
        e = "puerto_ocupado"
    elif not t.get("iniciado"):
        e = "detenido"
    else:
        e = {
            "activo": "activo",
            "abriendo": "abriendo",
            "reconectando": "reconectando",
            "sin cloudflared": "sin_cloudflared",
            "sin devtunnel": "sin_devtunnel",
            "sin sesion": "sin_sesion",
            "sin configurar": "sin_configurar",
            "error": "reconectando",
        }.get(t.get("estado") or "", "abriendo")
        if e == "abriendo" and t.get("url") and t.get("servicio") != "devtunnel":
            e = "conectando"  # ya tiene dirección, falta que Cloudflare confirme la conexión
    servicio = t.get("servicio") or R.servicio_tunel()
    return {
        "modo": sis.tunel["modo"],
        "estado": e,
        "url": t.get("url"),
        "desde": t.get("desde"),
        "servicio": servicio,
        "nombre_servicio": R.nombre_servicio(servicio),
        "error": sis.tunel["error"],
        "puerto_tunel": sis.puerto_tunel if servicio == "devtunnel" else None,
        "cambio": t.get("cambio"),
        "publicada": t.get("publicada"),
        "error_pub": t.get("error_pub"),
        "reinicios": t.get("reinicios", 0),
        "centro": t.get("centro"),
    }


def estado_admin(sis):
    ahora = time.time()
    try:
        cs = sis.vista.listar_casos()
    except Exception:
        cs = []
    k = {e: sum(1 for c in cs if c["estado"] == e) for e in ("listo", "nuevo", "error", "revisado")}
    gpu = GPU.lectura(sis.simular)
    man = A.manifiesto()
    oficial = man.get("version") or ""
    vinc = R.pcs_vinculadas()
    nombres = set(vinc) | set(sis.visto) | {v["pc"] for v in list(R.SESIONES.values())}
    con_panel = {x["pc"] for x in R.sesiones_admin()}
    pcs = []
    for pc in sorted(nombres, key=str.lower):
        v = vinc.get(pc, {})
        ultima = max(sis.visto.get(pc, 0), v.get("ultima") or 0) or None
        version = A.VERSION_PC.get(pc) or v.get("version")
        pcs.append(
            {
                "pc": pc,
                "llaves": v.get("llaves", 0),
                "vinculada": v.get("vinculada"),
                "ultima_vinculacion": v.get("ultima_vinculacion"),
                "ultima": ultima,
                "conectada": bool(ultima and ahora - ultima < 60),
                "version": version,
                "desactualizada": bool(version and oficial and version != oficial),
                "medico": R.medico_pc(pc),
                "sesiones": R.sesiones_de(pc),
                "panel": pc in con_panel,
                "revisando": sorted(
                    sis.casos.visible(c)
                    for c, b in list(R.BLOQUEOS.items())
                    if b["pc"] == pc and ahora - b["t"] < R.BLOQUEO_SEG
                ),
            }
        )
    gen, tr = sis.proc.en_estado("generando"), sis.proc.en_estado("transcribiendo")
    return {
        "ahora": ahora,
        "servidor": {
            "version": sis.version,
            "desde": sis.inicio,
            "simulado": sis.simular,
            "url": f"http://127.0.0.1:{sis.puerto}",
            "registros": str(L.CARPETA),
            "sistema": P.NOMBRE,
            "puede_abrir": P.puede_abrir(),
        },
        "ia": {
            "estado": sis.ia.ultimo["e"],
            "modelo": sis.cfg["modelo_ia"],
            "trabajando": f"armando el informe de «{sis.casos.titulo_de(gen[0])}»" if gen else None,
        },
        "whisper": {
            "modelo": sis.cfg["modelo_whisper"],
            "trabajando": f"transcribiendo «{sis.casos.titulo_de(tr[0])}»" if tr else None,
        },
        "gpu": gpu[0] if gpu else ("simulada (modo prueba)" if sis.simular else None),
        "gpu_tono": gpu[1] if gpu else None,
        "casos": {**k, "en_proceso": sis.proc.en_proceso()},
        "hoy": dict(L.HOY),
        "tunel": estado_tunel(sis),
        "contrasena": R.configurado(),
        "usuarios": estado_usuarios(),
        "admin_remoto": {
            "configurada": R.admin_configurado(),
            "desde": R.admin_desde(),
            "sesiones": R.sesiones_admin(),
        },
        "app": {"version": oficial, "archivos": len(man.get("archivos", []))},
        "pcs": pcs,
        "registro": ADM.ultimos_eventos(),
        "mantenimiento": sis.oper.estado_mantenimiento(),
        "cola": cola_en_vivo(sis),
        "abiertos": casos_abiertos(sis),
    }


def estado_usuarios():
    ses = R.sesiones_de_usuarios()
    out = []
    for u in U.lista():
        prop = {
            "plantillas": len(PL.secciones_de_usuario(u["clave"])),
            "medicos": len(MED.medicos_con_notas_propias(u["clave"])),
            "reglas": bool(U.leer_archivo(u["clave"], "reglas_dictado.md").strip()),
            "formato": bool(U.formato(u["clave"])),
        }
        out.append({**u, "en": sorted(set(ses.get(u["clave"], []))), "propio": prop})
    return out
