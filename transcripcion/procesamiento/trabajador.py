"""El trabajador: toma los audios de la cola en lotes, los transcribe (Whisper + segunda pasada), reconoce al médico
por la voz, arma el informe con la IA y calcula las marcas. También recupera la cola duradera al arrancar y
reconoce los resultados ya completos para no repetir trabajo.

Viene de servidor.py (docs/refactor.md, etapa 6a). Lo crea servidor.configurar(); main() lo corre en su hilo."""

import contextlib
import gc
import hashlib
import json
import os
import time
from pathlib import Path

from transcripcion.base import registro as L
from transcripcion.base.formatos import duracion_wav, mensaje_amigable, mmss, texto_marcas
from transcripcion.base.persistencia import escribir_atomico
from transcripcion.casos import paciente as PAC
from transcripcion.casos.repositorio import EXT_AUDIO
from transcripcion.controles import avisos as AV
from transcripcion.ia import ejemplos as EJEM
from transcripcion.ia import ollama as OLL
from transcripcion.ia import prompt as PR
from transcripcion.procesamiento import cache_transcripcion as CACHE_ASR
from transcripcion.procesamiento import cola as CP
from transcripcion.procesamiento import lotes as LOTES
from transcripcion.procesamiento.estado import Cancelado


# -------------------------------------------------------- procesamiento
ARCHIVOS_RESULTADO = (".json", ".dictado.txt", ".informe_ia.txt", ".marcas.json")


class Trabajador:
    """Usa `casos` (archivos), `proc` (cola, estado y pausas), `ia` (espera a Ollama), `voces` (médico por la voz),
    `vista` (marcas para la web) y `oper` (no empieza nada si hay un reinicio en camino). `raiz` es la carpeta del
    sistema (resultados simulados) y `cola_al_reiniciar` la cola que guarda un reinicio anterior."""

    def __init__(self, cfg, simular, raiz, informes, cola_al_reiniciar, casos, proc, ia, voces, vista, oper):
        self.cfg = cfg
        self.simular = simular
        self.raiz = raiz
        self.informes = informes
        self.cola_al_reiniciar = cola_al_reiniciar
        self.casos = casos
        self.proc = proc
        self.ia = ia
        self.voces = voces
        self.vista = vista
        self.oper = oper

    def firma_audio(self, ruta):
        s = ruta.stat()
        return [str(ruta.resolve()), s.st_size, s.st_mtime_ns]

    def hash_resultado(self, ruta):
        h = hashlib.sha256()
        with ruta.open("rb") as f:
            for bloque in iter(lambda: f.read(65536), b""):
                h.update(bloque)
        return h.hexdigest()

    def resultado_confirmado(self, n):
        if self.proc.duradera is None:
            return False
        fila = self.proc.duradera.obtener(n)
        if not fila or fila["estado"] not in CP.ACTIVOS:
            return False
        try:
            d = json.loads((self.casos.datos / f"{n}.procesamiento.json").read_text(encoding="utf-8"))
            a = self.casos.ruta_audio(n)
            return (
                d["v"] == 1
                and d["token"] == fila["token"]
                and a is not None
                and d["audio"] == self.firma_audio(a)
                and set(d["archivos"]) == set(ARCHIVOS_RESULTADO)
                and all(self.hash_resultado(self.casos.datos / (n + s)) == d["archivos"][s] for s in ARCHIVOS_RESULTADO)
            )
        except (OSError, ValueError, KeyError, TypeError):
            return False

    def confirmar_resultado(self, n, firma):
        if self.proc.duradera is None:
            return
        fila = self.proc.duradera.obtener(n)
        if fila is None:
            raise CP.ErrorCola("No existe la tarea que produjo el resultado.")
        if firma != self.firma_audio(self.casos.ruta_audio(n)):
            raise OSError("El audio cambió durante el procesamiento.")
        d = {
            "v": 1,
            "token": fila["token"],
            "audio": firma,
            "archivos": {s: self.hash_resultado(self.casos.datos / (n + s)) for s in ARCHIVOS_RESULTADO},
        }
        escribir_atomico(self.casos.datos / f"{n}.procesamiento.json", json.dumps(d, ensure_ascii=False))

    def trabajador(self):
        whisper = None
        while True:
            lote = [self.proc.cola.get()]
            while self.oper.reinicio.get("detener"):  # reinicio en camino: no empieza nada nuevo (queda en la cola)
                time.sleep(0.5)
            lote = LOTES.formar(self.proc.cola, lote[0], self.cfg, self.casos.duracion_de)
            lote_desde = time.perf_counter()
            self.proc.trabajo.update(ocupado=True, desde=time.time())
            trans, info = {}, {}
            etapa = "WHISPER"
            fallo_persistencia = False
            if len(lote) > 1:
                L.info(
                    "WHISPER",
                    f"Procesando {len(lote)} audios juntos: primero se transcriben todos y "
                    f"después la IA arma los informes.",
                )
            try:
                # 1) Whisper para todo el lote
                lote = [n for n in lote if n not in self.proc.borrados]
                for n in lote:
                    try:
                        if n in self.proc.borrados:
                            continue
                        if self.proc.sincronizar_terminal(n):
                            continue
                        if self.resultado_confirmado(n):
                            self.proc.poner_estado(n, "listo")
                            continue
                        self.proc.punto_de_pausa(n)  # una pausa recuperada no necesita cargar modelos
                        a = self.casos.ruta_audio(n)
                        if a is None:
                            self.proc.poner_estado(n, "error", "No encuentro el audio")
                            L.error(
                                "AUDIO",
                                f"{self.casos.visible(n)}: no encuentro el archivo de audio (¿se borró o se movió?).",
                            )
                            L.actividad("error", **self.casos.datos_csv(n), detalle="No encuentro el audio")
                            continue
                        if not self.proc.empezar(n, "transcribiendo", "Transcribiendo el audio…"):
                            continue
                        inicio_caso = time.perf_counter()
                        firma_entrada = self.firma_audio(a) if self.proc.duradera is not None else None
                        t0 = inicio_caso
                        recuperadas = 0
                        carga_whisper = 0.0
                        cache_usada = False
                        firma_asr = None
                        self.proc.pausado_s[n] = 0
                        try:
                            if not self.simular and self.cfg.get("reusar_transcripcion", True) is True:
                                from importlib.metadata import version, PackageNotFoundError

                                try:
                                    version_whisper = version("faster-whisper") + "/" + version("ctranslate2")
                                except PackageNotFoundError:
                                    version_whisper = "desconocida"
                                from transcripcion.asr import huecos as H, whisper as W

                                try:
                                    # el código que produce la transcripción también firma la caché
                                    firma_asr = CACHE_ASR.firma(
                                        a,
                                        {
                                            "modelo": self.cfg["modelo_whisper"],
                                            "dispositivo": self.cfg.get("dispositivo_whisper", "cuda"),
                                            "faster_whisper": version_whisper,
                                        },
                                        [Path(W.__file__), Path(H.__file__), W.VOCAB_DEF],
                                    )
                                    previa = CACHE_ASR.leer(
                                        self.casos.datos / f"{n}.transcripcion_cache.json", firma_asr
                                    )
                                    if previa is not None:
                                        trans[n] = previa
                                        cache_usada = True
                                except OSError:
                                    L.aviso("WHISPER", "No se pudo leer la caché; se transcribe de nuevo.", exc=True)
                            if cache_usada:
                                L.debug(
                                    "WHISPER", "Se reutiliza una transcripción verificada por contenido y parámetros."
                                )
                            elif self.simular:
                                of = self.casos.datos / f"{n}.original.txt"
                                fuente = Path(of.read_text(encoding="utf-8").strip()).stem if of.exists() else n
                                trans[n] = json.loads(
                                    (self.raiz / "resultados" / "fase1" / "json" / f"{fuente}.json").read_text(
                                        encoding="utf-8"
                                    )
                                )["con_vocab"]
                                trans[n]["huecos"] = json.loads(os.environ.get("SIMULAR_HUECOS", "[]"))
                                dem, paso = float(os.environ.get("SIMULAR_DEMORA", "0")), 0.25
                                for k in range(int(dem / paso)):  # tramos simulados (para probar la pausa)
                                    time.sleep(paso)
                                    self.proc.avance(n, "Transcribiendo el audio")((k + 1) * paso * 10, dem * 10)
                            else:
                                if whisper is None:
                                    OLL.liberar_ia(self.cfg["modelo_ia"])
                                    carga_desde = time.perf_counter()
                                    from transcripcion.asr import whisper as W

                                    self.proc.poner_estado(n, "transcribiendo", "Cargando Whisper…")
                                    L.info(
                                        "WHISPER",
                                        f"Cargando Whisper {self.cfg['modelo_whisper']} "
                                        + (
                                            "en la placa de video…"
                                            if self.cfg.get("dispositivo_whisper", "cuda") == "cuda"
                                            else "en el procesador (más lento)…"
                                        ),
                                    )
                                    tc = time.time()
                                    with contextlib.redirect_stdout(L.SalidaAlRegistro("WHISPER")):
                                        whisper = W.cargar_modelo(
                                            self.cfg["modelo_whisper"], self.cfg.get("dispositivo_whisper", "cuda")
                                        )
                                    carga_whisper = time.perf_counter() - carga_desde
                                    L.ok("WHISPER", f"Whisper cargado en {L.seg(time.time() - tc)}.")
                                    self.proc.poner_estado(n, "transcribiendo", "Transcribiendo el audio…")
                                    t0 = time.perf_counter()
                                from transcripcion.asr import huecos as H, whisper as W

                                prompt = W.leer_vocabulario(W.VOCAB_DEF)
                                self.proc.punto_de_pausa(n)  # se pidió la pausa mientras se cargaba Whisper
                                t = W.transcribir(
                                    whisper, a, prompt, al_avanzar=self.proc.avance(n, "Transcribiendo el audio")
                                )
                                self.proc.poner_estado(
                                    n, "transcribiendo", "Revisando partes que Whisper pudo saltear…"
                                )
                                pal, pend = H.reparar(
                                    whisper,
                                    W.cargar_audio(a),
                                    t["palabras"],
                                    prompt,
                                    al_avanzar=self.proc.avance(n, "Revisando partes que Whisper pudo saltear"),
                                )
                                recuperadas = max(0, len(pal) - len(t["palabras"]))
                                trans[n] = {"texto": H.texto_de(pal), "palabras": pal, "huecos": pend}
                            self.proc.punto_de_pausa(n)  # una pausa pedida justo al final se cumple acá
                        except Cancelado:
                            self.proc.pausado_s.pop(n, None)
                            trans.pop(n, None)
                            L.info(
                                "WHISPER",
                                f"Se dejó de transcribir {self.casos.visible(n)}: se borró mientras estaba en pausa.",
                            )
                            continue
                        if firma_asr is not None and not cache_usada:
                            try:
                                CACHE_ASR.guardar(
                                    self.casos.datos / f"{n}.transcripcion_cache.json", firma_asr, trans[n]
                                )
                            except OSError:
                                L.aviso("WHISPER", "No se pudo conservar la caché; el informe continúa.", exc=True)
                        escribir_atomico(
                            self.casos.datos / f"{n}.json", json.dumps(trans[n], ensure_ascii=False, indent=1)
                        )
                        escribir_atomico(self.casos.datos / f"{n}.dictado.txt", trans[n]["texto"])
                        PAC.calcular(
                            self.casos.datos, n, forzar=True
                        )  # nombre del paciente para la lista (no va al informe)
                        escribir_atomico(self.casos.datos / f"{n}.audio.txt", str(a.resolve()))
                        self.voces.calcular_voz(n, a, trans[n]["palabras"])  # médico por la voz (antes de la IA)
                        dur = duracion_wav(ruta=a)
                        if dur is None and trans[n]["palabras"]:
                            dur = trans[n]["palabras"][-1].get("fin")
                        info[n] = {
                            "dur": dur,
                            "whisper": time.perf_counter() - t0 - self.proc.pausado_s.pop(n, 0),
                            "palabras": len(trans[n]["palabras"]),
                            "cache_asr": cache_usada,
                            "carga_whisper_s": carga_whisper,
                            "inicio_caso": inicio_caso,
                            "firma_audio": firma_entrada,
                        }
                        partes = [f"audio {L.mmss(dur)}" if dur else None, L.plural(info[n]["palabras"], "palabra")]
                        if recuperadas:
                            partes.append(f"la segunda pasada recuperó {L.plural(recuperadas, 'palabra')}")
                        L.ok(
                            "WHISPER",
                            f"{self.casos.visible(n)} transcrito en {L.seg(info[n]['whisper'])} · "
                            + " · ".join(x for x in partes if x),
                        )
                        for h in trans[n].get("huecos") or []:
                            L.aviso(
                                "WHISPER",
                                f"{self.casos.visible(n)}: posible parte no transcrita entre {mmss(h['ini'])} y "
                                f"{mmss(h['fin'])}. Revisarla escuchando.",
                            )
                        self.proc.poner_estado(n, "en cola", "Esperando a la IA…")
                    except CP.ErrorCola:
                        raise
                    except Exception as ex:
                        trans.pop(n, None)
                        info.pop(n, None)
                        self.proc.pausado_s.pop(n, None)
                        self.proc.poner_estado(n, "error", mensaje_amigable(ex))
                        L.error("WHISPER", "Falló un audio; se continúa con los demás del lote.", exc=True)
                        L.actividad("error", **self.casos.datos_csv(n), detalle="WHISPER: " + mensaje_amigable(ex))
                if whisper is not None:  # liberar la placa para la IA
                    del whisper
                    whisper = None
                    gc.collect()
                    L.debug("WHISPER", "Whisper liberado de la placa de video.")
                # 2) IA
                etapa = "IA"
                banco = EJEM.cargar_banco() if trans else []
                for n in trans:
                    try:
                        if n in self.proc.borrados:
                            continue
                        self.proc.punto_de_pausa(n)
                        self.ia.esperar_ia(n, list(trans))
                        if not self.proc.empezar(n, "generando", "La IA está armando el informe…"):
                            continue
                        t0 = time.perf_counter()
                        tokens = ""
                        metricas_ia = {}
                        dic = trans[n]["texto"]
                        usu = self.casos.usuario_de(n) or None
                        if self.simular:
                            of = self.casos.datos / f"{n}.original.txt"
                            fuente = Path(of.read_text(encoding="utf-8").strip()).stem if of.exists() else n
                            salida = self.raiz / "resultados" / "fase2" / "gemma4_12b" / f"{fuente}.json"
                            salida = json.loads(salida.read_text(encoding="utf-8"))["salida"]
                            time.sleep(float(os.environ.get("SIMULAR_DEMORA", "0")))
                        else:
                            med = self.casos.medico_de(n) or None
                            # sin médico confirmado (voz dudosa o sin reconocer): plantilla general, sin estilos de médico
                            sin_est = not med and self.voces.resumen_voz(n) is not None
                            ej = EJEM.elegir_ejemplos(
                                dic, banco, k=self.cfg["ejemplos_por_informe"], excluir=n, medico=med, usuario=usu
                            )
                            salida, _, t_in, t_out = OLL.llamar_ia(
                                self.cfg["modelo_ia"],
                                PR.armar_mensajes(dic, ej, med, sin_estilos=sin_est, usuario=usu),
                                metricas=metricas_ia,
                            )
                            tokens = f"{t_in or '?'} tokens de entrada, {t_out or '?'} de salida"
                        escribir_atomico(self.casos.datos / f"{n}.informe_ia.txt", salida)
                        escribir_atomico(self.casos.datos / f"{n}.estilo.txt", usu or "")
                        self.casos.anotar_voz(n, medico_ia=self.casos.medico_de(n) or "")
                        for viejo in (
                            f"{n}.marcas.json",
                            f"{n}.borrador.html",
                            f"{n}.borrador.json",
                            f"{n}.final.txt",
                            f"{n}.formato.json",
                        ):
                            (self.casos.datos / viejo).unlink(missing_ok=True)
                        (self.casos.datos / f"{n}.omisiones_ok.json").unlink(missing_ok=True)
                        lineas, om = self.vista.guardar_marcas(
                            n, salida, dic, trans[n]["palabras"], trans[n].get("huecos")
                        )
                        self.confirmar_resultado(n, info[n]["firma_audio"])
                        self.proc.poner_estado(n, "listo")
                        ia_s = time.perf_counter() - t0
                        try:
                            escribir_atomico(
                                self.casos.datos / f"{n}.rendimiento.json",
                                json.dumps(
                                    {
                                        "v": 1,
                                        "lote_audios": len(lote),
                                        "lote_hasta_listo_s": time.perf_counter() - lote_desde,
                                        "cache_asr": info[n]["cache_asr"],
                                        "carga_whisper_s": info[n]["carga_whisper_s"],
                                        "desde_inicio_caso_s": time.perf_counter() - info[n]["inicio_caso"],
                                        "desde_encolado_s": max(0, time.time() - self.proc.encolado[n])
                                        if n in self.proc.encolado
                                        else None,
                                        "whisper_s": info[n]["whisper"],
                                        "ia_s": ia_s,
                                        "ollama": metricas_ia,
                                    }
                                ),
                            )
                        except OSError:
                            L.aviso("IA", "No se pudieron conservar las métricas de rendimiento.", exc=True)
                        if not self.simular:
                            self.proc.anotar_tiempo(
                                info[n]["dur"], None if info[n]["cache_asr"] else info[n]["whisper"], ia_s
                            )
                        r = self.casos.resumen_avisos(n, {"lineas": lineas, "omisiones": om})
                        nuevos = AV.estudios_sin_plantilla(salida)
                        L.contar("generados")
                        med = self.casos.medico_de(n)
                        vz = self.voces.resumen_voz(n) or {}
                        det = []
                        if r["faltan"]:
                            det.append("Dictado pero no está en el informe: " + ", ".join(r["faltan"]))
                        if tokens:
                            L.debug("IA", f"{self.casos.visible(n)}: {tokens}")
                        L.ok(
                            "IA",
                            f"{self.casos.visible(n)} informe listo en {L.seg(ia_s)}"
                            + (
                                f" · {med}" + (" (por la voz)" if vz.get("por") == "voz" else "")
                                if med
                                else " · sin médico (plantilla general)"
                                if vz
                                else " · sin médico elegido"
                            )
                            + f" · {texto_marcas(r)}",
                            det,
                        )
                        for e in nuevos:
                            L.aviso(
                                "IA",
                                f"{self.casos.visible(n)}: estudio sin plantilla «{e}». Conviene crearla desde Plantillas.",
                            )
                        L.actividad(
                            "generado",
                            **self.casos.datos_csv(n),
                            duracion_audio_s=info.get(n, {}).get("dur"),
                            whisper_s=None if info[n]["cache_asr"] else info[n]["whisper"],
                            ia_s=ia_s,
                            palabras_dictado=info.get(n, {}).get("palabras"),
                            marcas_rojas=r["rojo"],
                            marcas_amarillas=r["amarillo"],
                            marcas_turquesa=r["turq"],
                            marcas_grises=r["gris"],
                            datos_faltantes=" ".join(r["faltan"]),
                            partes_no_transcritas=" ".join(r["huecos"]),
                            estudios_sin_plantilla=" | ".join(nuevos),
                            **self.voces.campos_voz(vz),
                        )
                    except CP.ErrorCola:
                        raise
                    except Exception as ex:
                        self.proc.poner_estado(n, "error", mensaje_amigable(ex))
                        L.error("IA", "Falló un informe; se continúa con los demás del lote.", exc=True)
                        L.actividad("error", **self.casos.datos_csv(n), detalle="IA: " + mensaje_amigable(ex))
            except CP.ErrorCola:
                fallo_persistencia = True
                L.error("COLA", "No se pudo confirmar la cola. Se conservan las tareas y se reintentará.", exc=True)
                with self.proc.lock:
                    pendientes = [
                        n
                        for n in lote
                        if n not in self.proc.borrados
                        and self.proc.estado.get(n, {}).get("estado") not in ("listo", "error")
                    ]
                    for n in pendientes:
                        self.proc.estado[n] = {
                            "estado": "en cola",
                            "msg": "Esperando recuperar el almacenamiento",
                            "t": time.time(),
                        }
                for n in pendientes:
                    self.proc.cola.put(n)
            except Exception as ex:
                msg = mensaje_amigable(ex)
                afectados = [
                    n
                    for n in lote
                    if self.proc.estado.get(n, {}).get("estado") not in ("listo", "error")
                    and n not in self.proc.borrados
                ]
                L.error(
                    etapa,
                    f"No se pudo procesar {', '.join(self.casos.visible(n) for n in afectados) or 'el lote'}: {msg}",
                    exc=True,
                )
                for n in afectados:
                    try:
                        self.proc.poner_estado(n, "error", msg)
                    except CP.ErrorCola:
                        fallo_persistencia = True
                        self.proc.cola.put(n)
                    L.actividad("error", **self.casos.datos_csv(n), detalle=f"{etapa}: {msg}")
            finally:
                if whisper is not None:
                    del whisper
                    whisper = None
                    gc.collect()
                self.proc.trabajo.update(ocupado=False, esperando_ia=False)
            if fallo_persistencia:
                time.sleep(5)
            if not self.proc.en_proceso() and self.proc.cola.empty():
                L.debug("SERVIDOR", "Cola vacía.")

    def reanudar_cola(self):
        """Inicialización exclusiva antes de arrancar trabajadores o atender HTTP."""
        if self.proc.duradera is not None:
            raise CP.ErrorCola("La cola ya se inicializó en este proceso.")
        cola = CP.ColaProcesamiento(self.casos.datos.parent / "cola_procesamiento.sqlite3")
        try:
            cola.importar_legacy(self.cola_al_reiniciar, self.casos.ruta_audio)
            self.proc.duradera = cola
            # Ventana publicación de audio -> alta de tarea, y migración de instalaciones anteriores.
            # Nunca adoptar un caso revisado o con borrador, ni reactivar un registro terminal.
            for a in sorted(self.casos.nuevos.iterdir(), key=lambda p: (p.stat().st_mtime_ns, p.name)):
                n = a.stem
                if a.is_file() and a.suffix.lower() in EXT_AUDIO and cola.obtener(n) is None:
                    if not self.revision_conservada(n) and not (self.casos.datos / f"{n}.informe_ia.txt").exists():
                        cola.solicitar(n)
            for fila in cola.filas():
                n, e = fila["nombre"], fila["estado"]
                if e in ("listo", "cancelado"):
                    continue
                if e == "borrando":
                    self.proc.borrados.add(n)
                    self.proc.estado[n] = {
                        "estado": "error",
                        "msg": "Borrado interrumpido: revisar recuperación antes de procesar.",
                        "t": time.time(),
                    }
                    continue
                if e == "error":
                    self.proc.estado[n] = {
                        "estado": "error",
                        "msg": "El procesamiento falló. Reintentá cuando se haya resuelto el problema.",
                        "t": time.time(),
                    }
                    continue
                if self.resultado_confirmado(n):
                    self.proc.poner_estado(n, "listo")
                    continue
                if self.revision_conservada(n):
                    self.proc.poner_estado(
                        n, "error", "Se conservó una revisión. Revisá el caso antes de volver a procesar."
                    )
                    continue
                if self.casos.ruta_audio(n) is None:
                    self.proc.poner_estado(
                        n, "error", "No encuentro el audio pendiente. Conservamos su registro para recuperación."
                    )
                    continue
                cola.cambiar(n, "en cola")
                self.proc.encolado[n] = fila["encolado"]
                if fila["pausado"]:
                    self.proc.pausas[n] = {
                        "pedida": time.time(),
                        "desde": time.time(),
                        "por": "recuperación tras caída",
                    }
                self.proc.estado[n] = {
                    "estado": "en pausa" if fila["pausado"] else "en cola",
                    "msg": "Pausa conservada tras caída" if fila["pausado"] else "Recuperado tras caída",
                    "t": time.time(),
                }
                self.proc.cola.put(n)
            L.info("COLA", "Cola persistente recuperada; las pausas se conservan.")
        except BaseException:
            self.proc.duradera = None
            cola.cerrar()
            raise

    def revision_conservada(self, n):
        return (
            any(
                (self.casos.datos / (n + s)).exists()
                for s in (".final.txt", ".borrador.json", ".borrador.html", ".formato.json")
            )
            or (self.informes / f"{n}.docx").exists()
        )
