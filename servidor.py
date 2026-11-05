# -*- coding: utf-8 -*-
"""
INTERFAZ WEB. Se abre con interfaz.bat o .sh (solo esta PC) o con iniciar_servidor.bat o .sh
(esta PC + las PC del trabajo por un tunel: el rapido de Cloudflare o Microsoft Dev Tunnels).
Todo se procesa en esta PC: las otras solo envian audios y muestran la pagina.
"""
import os
import sys
import threading
import time
import webbrowser
from http.server import ThreadingHTTPServer
from pathlib import Path

from transcripcion.operacion import estadisticas as EST
from transcripcion.aprendizaje import aprender as APRENDER
from transcripcion.operacion import app_cliente as A
from transcripcion.aprendizaje.pendiente import ColaAprendizaje
from transcripcion.operacion import mantenimiento as M
from transcripcion.conocimiento import archivos as CON
from transcripcion.base import plataforma as P
from transcripcion.base import registro as L
from transcripcion.acceso import remoto as R
from transcripcion import ajustes
from transcripcion.casos.repositorio import Casos
from transcripcion.procesamiento.estado import Procesamiento
from transcripcion.procesamiento.trabajador import Trabajador
from transcripcion.operacion.reinicio import Operacion
from transcripcion.casos.borrado import Borrado
from transcripcion.casos.vista import VistaCasos
from transcripcion.voz.servicio import ServicioVoz
from transcripcion.operacion.ia import EstadoIA
from transcripcion.informe.guardado import Guardado
from transcripcion.http.manejador import Manejador, ManejadorTunel
from transcripcion.http.sistema import Sistema
from transcripcion.operacion import gpu as GPU

AQUI = Path(__file__).resolve().parent
WEB = AQUI / "web"

# Ajustes del arranque. Importar este módulo no lee la configuración ni crea carpetas: los completa
# configurar(), que llama main() (o una prueba con ajustes.para_pruebas). Ver docs/refactor.md, etapa 1.
AJUSTES = None
CFG = None            # configuracion.json ya leída
NUEVOS = None         # carpeta de audios nuevos
INFORMES = None       # carpeta de los Word
DATOS = None          # Informes/revision/datos: archivos de cada caso
PUERTO = None         # interfaz web local
# Puerto propio del túnel de Microsoft (Dev Tunnels): todo lo que entra por acá es de las PC del trabajo,
# tenga los encabezados que tenga. Solo escucha en 127.0.0.1 y solo con ese túnel elegido.
PUERTO_TUNEL = None
SIMULAR = False       # SIMULAR_IA=1: sin Whisper ni Ollama (solo para pruebas)
COLA_AL_REINICIAR = None
APRENDIZAJE = None    # cola persistente de aprendizaje (se crea en configurar)
CASOS = None          # archivos de los casos (transcripcion.casos.repositorio.Casos, se crea en configurar)
PROC = None           # estado del procesamiento: etapas, cola, pausas (transcripcion.procesamiento.estado)
IA = None     # estado de Ollama (transcripcion.operacion.ia)
VOCES = None  # reconocimiento por la voz (transcripcion.voz.servicio)
VISTA = None  # lista y caso abierto para las pantallas (transcripcion.casos.vista)
BORRADO = None # borrado de casos (transcripcion.casos.borrado)
OPER = None   # reinicio programado y mensajes a las PC (transcripcion.operacion.reinicio)
TRAB = None   # trabajador de la cola (transcripcion.procesamiento.trabajador)
GUARDADO = None  # Guardar Word y aprender, vista previa (transcripcion.informe.guardado)
VERSION = "2026.11.16"
SIS = None     # lo que usan las rutas HTTP (transcripcion.http.sistema.Sistema)
H = Manejador  # manejador HTTP de este sistema: Manejador.para(SIS), se arma en configurar
HTunel = ManejadorTunel
FIN_LOCK = threading.Lock()
INICIO = time.time()
TUNEL = {"modo": False, "http": None, "error": None}     # "modo": se abrió con iniciar_servidor.bat (--tunel)


VISTO = {}              # PC del trabajo -> hora de su último pedido

# ------------------------------------------------- mensajes a las PC y reinicio desde el panel
SRV = {"http": None, "salida": 0}


def abrir_tunel():
    """Abre el túnel elegido (configurar_tunel). Con Microsoft Dev Tunnels, antes abre el puerto propio
    del túnel; si no se puede, no abre el túnel (devtunnel publicaría lo que haya en ese puerto)."""
    if R.URL_TUNEL.get("iniciado"):
        return
    if R.servicio_tunel() == "devtunnel" and not TUNEL["http"]:
        try:
            TUNEL["http"] = Servidor(("127.0.0.1", PUERTO_TUNEL), HTunel)
        except OSError as ex:
            TUNEL["error"] = f"El puerto {PUERTO_TUNEL} está ocupado por otro programa ({ex})."
            L.error("TÚNEL", f"No se pudo abrir el puerto {PUERTO_TUNEL} para el túnel de Microsoft: lo usa otro "
                             f"programa. Cerralo o cambiá PUERTO_TUNEL. Mientras tanto el sistema funciona solo en esta PC.")
            return
        threading.Thread(target=TUNEL["http"].serve_forever, daemon=True, name="puerto-tunel").start()
        L.debug("TÚNEL", f"Puerto propio del túnel abierto: 127.0.0.1:{PUERTO_TUNEL}")
    R.escribir_conexion_cliente()
    R.iniciar_tunel(PUERTO, PUERTO_TUNEL)



def configurar(aj):
    """Toma los ajustes (de ajustes.cargar() en main, o de ajustes.para_pruebas en una prueba).
    No crea carpetas ni arranca hilos: eso lo hace main(). Devuelve los ajustes anteriores, para que una
    prueba los restaure con configurar(anteriores); configurar(None) deja todo sin configurar."""
    global AJUSTES, CFG, NUEVOS, INFORMES, DATOS, PUERTO, PUERTO_TUNEL, SIMULAR, COLA_AL_REINICIAR, APRENDIZAJE, CASOS, PROC, IA, VOCES, VISTA, BORRADO, OPER, TRAB, GUARDADO, SIS, H, HTunel
    anteriores = AJUSTES
    AJUSTES = aj
    if aj is None:
        CFG = NUEVOS = INFORMES = DATOS = PUERTO = PUERTO_TUNEL = COLA_AL_REINICIAR = APRENDIZAJE = CASOS = PROC = IA = VOCES = VISTA = BORRADO = OPER = TRAB = GUARDADO = SIS = None
        SIMULAR = False
        H, HTunel = Manejador, ManejadorTunel
        return anteriores
    CFG = aj.cfg
    NUEVOS, INFORMES, DATOS = aj.audios_nuevos, aj.informes, aj.datos
    PUERTO, PUERTO_TUNEL, SIMULAR = aj.puerto, aj.puerto_tunel, aj.simular_ia
    COLA_AL_REINICIAR = INFORMES / "revision" / "cola_al_reiniciar.json"
    CASOS = Casos(DATOS, NUEVOS)
    PROC = Procesamiento(CASOS)
    IA = EstadoIA(CFG, SIMULAR, AQUI, CASOS, PROC)
    VOCES = ServicioVoz(CFG, CASOS, PROC)
    VISTA = VistaCasos(CASOS, PROC, VOCES, INICIO, R)
    BORRADO = Borrado(CASOS, PROC, INFORMES, R)
    OPER = Operacion(CASOS, PROC, COLA_AL_REINICIAR, TUNEL, SRV, FIN_LOCK, M)
    TRAB = Trabajador(CFG, SIMULAR, AQUI, INFORMES, COLA_AL_REINICIAR, CASOS, PROC, IA, VOCES, VISTA, OPER)
    GUARDADO = Guardado(CFG, INFORMES, CASOS, VOCES, FIN_LOCK, APRENDER, EST)
    APRENDIZAJE = ColaAprendizaje(DATOS / "_aprendizaje", GUARDADO.aplicar_aprendizaje, GUARDADO.analizar_aprendizaje)
    GUARDADO.aprendizaje = APRENDIZAJE   # la cola llama a métodos de GUARDADO; GUARDADO le encola tareas
    SIS = Sistema(cfg=CFG, datos=DATOS, nuevos=NUEVOS, informes=INFORMES, web=WEB, puerto=PUERTO,
                  puerto_tunel=PUERTO_TUNEL, simular=SIMULAR, version=VERSION, inicio=INICIO, casos=CASOS, proc=PROC,
                  ia=IA, voces=VOCES, vista=VISTA, borrado=BORRADO, oper=OPER, guardado=GUARDADO, tunel=TUNEL,
                  visto=VISTO, abrir_tunel=abrir_tunel)
    H, HTunel = Manejador.para(SIS), ManejadorTunel.para(SIS)    # rutas en transcripcion/http/tabla.py
    return anteriores


class Servidor(ThreadingHTTPServer):
    daemon_threads = True

    def handle_error(self, request, client_address):
        """Una PC que corta la conexión a mitad de camino es normal: no ensuciar la ventana."""
        ex = sys.exc_info()[1]
        if isinstance(ex, (ConnectionError, TimeoutError, BrokenPipeError)):
            L.debug("SERVIDOR", f"Conexión cortada por el otro lado: {ex!r}")
        else:
            L.error("SERVIDOR", "Error atendiendo un pedido.", exc=True)



_PANEL = {"casos_t": 0, "casos": None}    # conteo de casos del encabezado (se renueva cada 3 s)


def filas_encabezado(url, tunel):
    """Lo que muestra el encabezado fijo; se llama cada segundo (lo pesado se refresca cada 3 s)."""
    ahora = time.time()
    if ahora - _PANEL["casos_t"] > 3:
        try:
            cs = VISTA.listar_casos()
            _PANEL["casos"] = {k: sum(1 for x in cs if x["estado"] == k) for k in ("listo", "nuevo", "error")}
        except Exception:
            pass
        _PANEL["casos_t"] = ahora
    g = GPU.lectura(SIMULAR)
    filas = [("Interfaz", url, None), ("Administración", f"{url}/admin (PC vinculadas, túnel, errores)", None)]
    if SIMULAR:
        filas.append(("Modo", "PRUEBA: Whisper y la IA están simulados", "aviso"))
    # acceso remoto
    if not tunel:
        filas.append(("Acceso remoto", f"apagado: solo esta PC (para el trabajo usá {P.script('iniciar_servidor')})", None))
    elif not R.configurado():
        filas.append(("Acceso remoto", f"falta la contraseña: ejecutá {P.script('configurar_acceso')}", "aviso"))
    elif R.URL_TUNEL.get("url") and R.URL_TUNEL.get("estado") == "activo":
        desde = R.URL_TUNEL.get("desde")
        filas.append(("Acceso remoto", f"túnel de {R.nombre_servicio(R.URL_TUNEL.get('servicio'))} activo"
                      + (f" desde hace {L.hace(ahora - desde)}" if desde else ""), "ok"))
    elif R.URL_TUNEL.get("estado") in ("sin sesion", "sin configurar", "sin devtunnel") or TUNEL["error"]:
        filas.append(("Acceso remoto", TUNEL["error"] or f"Microsoft Dev Tunnels no está listo: ejecutá "
                                                         f"{P.script('configurar_tunel')}", "error"))
    else:
        filas.append(("Acceso remoto", "túnel abriéndose o reconectando…", "aviso"))
    if tunel and R.configurado():      # en su propio renglón, para que la dirección entre entera
        filas.append(("Dirección", R.URL_TUNEL.get("url") or f"esperando a {R.nombre_servicio()}…", None))
    if tunel:
        activas = sorted((p, t) for p, t in VISTO.items() if ahora - t < 60)
        filas.append(("PC conectadas", ", ".join(p if ahora - t < 10 else f"{p} (hace {L.hace(ahora - t)})"
                                                 for p, t in activas) or "ninguna en este momento",
                      "ok" if activas else None))
    if tunel:
        try:
            t = A.texto_panel()
        except Exception:
            t = None
        if t:
            filas.append(("App del trabajo", t, None))
    # IA y Whisper
    gen = PROC.en_estado("generando")
    e = IA.ultimo["e"]
    if e == "caida":
        filas.append(("IA", "Ollama no responde: abrilo para poder generar informes", "error"))
    elif e == "sin_modelo":
        filas.append(("IA", f"Ollama no tiene el modelo {CFG['modelo_ia']}", "error"))
    else:
        filas.append(("IA", f"{CFG['modelo_ia']} · " + (f"armando el informe de «{CASOS.titulo_de(gen[0])}»" if gen
                                                       else "lista, esperando"), "ok"))
    tr = PROC.en_estado("transcribiendo")
    filas.append(("Whisper", f"{CFG['modelo_whisper']} · " + (f"transcribiendo «{CASOS.titulo_de(tr[0])}»" if tr
                                                              else "en espera (se carga cuando llega un audio)"),
                  "ok" if tr else None))
    filas.append(("Placa de video", g[0] if g else ("simulada" if SIMULAR else "sin datos (nvidia-smi no responde)"),
                  g[1] if g else None))
    # casos
    k = _PANEL["casos"] or {}
    proc = PROC.en_proceso()
    partes = [f"{k.get('listo', 0)} para revisar", f"{k.get('nuevo', 0)} sin procesar", f"{proc} en proceso"]
    if k.get("error"):
        partes.append(f"{k['error']} con error")
    filas.append(("Casos", " · ".join(partes), "error" if k.get("error") else ("aviso" if k.get("nuevo") else None)))
    h = L.HOY
    filas.append(("Hoy", f"{L.plural(h['recibidos'], 'audio recibido', 'audios recibidos')} · "
                         f"{L.plural(h['generados'], 'informe', 'informes')} · "
                         f"{L.plural(h['guardados'], 'guardado')} · {L.plural(h['errores'], 'error', 'errores')}",
                  "aviso" if h["errores"] else None))
    filas.append(("Registro", f"{L.ruta_corta(L.CARPETA)}{os.sep} (un archivo por día + actividad.csv)", None))
    return filas


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    titulo = M.titulo_consola()          # antes de que el servidor cambie el título de la ventana
    configurar(ajustes.cargar(AQUI))
    ajustes.preparar_carpetas(AJUSTES)
    CON.preparar_conocimiento()
    L.configurar()
    srv = None
    for intento in range(6):             # al reiniciar desde el panel, Windows puede tardar un instante en soltar el puerto
        try:
            srv = Servidor(("127.0.0.1", PUERTO), H)
            break
        except OSError:
            if intento == 5:
                L.error("SERVIDOR", f"No se pudo abrir el puerto {PUERTO}: seguramente el servidor ya está abierto en "
                                    f"otra ventana. Usá esa ventana o cerrala y volvé a abrir esta.", exc=True)
                sys.exit(1)
            time.sleep(1)
    SRV["http"] = srv
    R.cargar_sesiones()
    try:
        TRAB.reanudar_cola()
    except Exception:
        L.error('COLA', 'No se pudo recuperar la cola. No se inicia procesamiento ni se aceptan audios; conservá la base y los archivos.', exc=True)
        srv.server_close()
        return 1
    M.empezar(titulo)
    url = f"http://127.0.0.1:{PUERTO}"
    tunel = "--tunel" in sys.argv
    TUNEL["modo"] = tunel
    e_ia = IA.estado_ia()
    IA.ultimo["e"] = e_ia
    IA.cache.update(t=time.time(), ok=e_ia != "caida")
    L.encabezado("TRANSCRIPCIÓN DE INFORMES  ·  SERVIDOR", f"versión {VERSION}",
                 lambda: filas_encabezado(url, tunel),
                 "Eventos · no cierres esta ventana · Ctrl+C apaga · historial completo en registros")
    L.estado(ia=e_ia == "ok", cola=0)
    PROC.cargar_tiempos()
    APRENDIZAJE.iniciar()
    threading.Thread(target=TRAB.trabajador, daemon=True, name="procesamiento").start()
    threading.Thread(target=IA.vigilar_ia, args=(e_ia,), daemon=True, name="vigilancia-ia").start()
    threading.Thread(target=VOCES.hilo_voces, daemon=True, name="voces").start()
    g = M.git_al_arrancar() or {}
    L.ok("SERVIDOR", f"Servidor iniciado en {url}" + ("" if e_ia == "ok" else " (sin IA hasta que se abra Ollama)")
         + (f" · código {g['commit']}" + (f" + {L.plural(len(g['sucios']), 'cambio')} sin commitear" if g.get("sucios") else "")
            if g.get("commit") else ""))
    if tunel:
        if not R.configurado():
            L.aviso("TÚNEL", f"Todavía no hay contraseña para el acceso remoto: ejecutá {P.script('configurar_acceso')}. "
                             "Por ahora el sistema funciona solo en esta PC.")
        else:
            abrir_tunel()
    if "--sin-navegador" not in sys.argv:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    if not P.ES_WINDOWS:     # Linux: "kill" o "systemctl stop" apagan en orden, igual que Ctrl+C
        import signal

        def _apagar(*_):
            raise KeyboardInterrupt
        signal.signal(signal.SIGTERM, _apagar)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    L.cerrar_encabezado()
    R.cerrar_tunel()
    if TUNEL["http"]:
        try:
            TUNEL["http"].shutdown()         # primero que deje de atender; si no, server_close tira WinError 10038
            TUNEL["http"].server_close()
        except Exception:
            pass
    try:
        srv.server_close()
    except Exception:
        pass
    h = L.HOY
    if SRV["salida"] == M.CODIGO_REINICIO:
        L.info("SERVIDOR", "Servidor cerrado para reiniciarse: se vuelve a abrir solo en esta misma ventana.")
        OPER._salir_para_reiniciar()
    L.info("SERVIDOR", f"Servidor apagado. Hoy: {L.plural(h['recibidos'], 'audio recibido', 'audios recibidos')}, "
                       f"{L.plural(h['generados'], 'informe generado', 'informes generados')}, "
                       f"{L.plural(h['guardados'], 'guardado')}, {L.plural(h['errores'], 'error', 'errores')}.")


if __name__ == "__main__":
    sys.exit(main() or 0)
