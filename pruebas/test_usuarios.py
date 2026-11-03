"""Transcriptores con estilo propio: usuarios, sesiones, capas de conocimiento, aprendizaje y HTTP.
Todo con datos ficticios en una carpeta temporal dentro de respaldo/."""
import http.client
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
import urllib.parse
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from transcripcion import ajustes
import servidor as S
from transcripcion.conocimiento import archivos as CON
from transcripcion.conocimiento import medicos as MED
from transcripcion.conocimiento import plantillas as PL
from transcripcion.ia import ejemplos as EJEM
from transcripcion.ia import prompt as PR
import remoto as R
from transcripcion.acceso import usuarios as U
import aprender as AP

PLANTILLAS = """# PLANTILLAS FICTICIAS

## ECOGRAFÍA TIROIDEA
TITULO: ECOGRAFÍA TIROIDEA
PROTOCOLO NORMAL:
- Glándula tiroides de forma y tamaño normal.

## MAMOGRAFÍA
TITULO: MAMOGRAFÍA DIGITAL BILATERAL
PROTOCOLO NORMAL:
- Mamas de densidad tipo B.
"""


class Base(unittest.TestCase):
    def setUp(self):
        respaldo = Path(__file__).resolve().parents[1] / "respaldo"
        respaldo.mkdir(exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(prefix="test_usuarios_", dir=respaldo)
        self.addCleanup(self.tmp.cleanup)
        d = Path(self.tmp.name)
        conoc = d / "conocimiento"
        conoc.mkdir()
        (conoc / "plantillas.md").write_text(PLANTILLAS, encoding="utf-8")
        (conoc / "reglas_dictado.md").write_text("- Regla general ficticia.\n", encoding="utf-8")
        self.d = d
        for obj, nombre, valor in ((CON, "CONOC", conoc), (MED, "DIR_MED", conoc / "medicos"),
                                   (U, "ARCH", d / "usuarios.json"), (U, "CARPETA", conoc / "usuarios"),
                                   (R, "ARCH", d / "acceso_remoto.json"), (R, "ARCH_SESIONES", d / "sesiones.json"),
                                   (R, "SESIONES", {}), (R, "FALLOS", {}), (R, "CARPETA_CLIENTE", d / "cliente"),
                                   (AP, "ARCH_CORR", conoc / "correcciones_aprendidas.md"),
                                   (AP, "EJ", d / "ejemplos"), (AP, "HIST", d / "resultados" / "historial.csv")):
            p = patch.object(obj, nombre, valor)
            p.start()
            self.addCleanup(p.stop)
        U._CACHE.update(mt=None, d=None)
        self.addCleanup(U._CACHE.update, mt=None, d=None)
        # El servidor trabaja en la carpeta temporal (antes usaba las carpetas reales de la configuración)
        aj = ajustes.para_pruebas(d)
        ajustes.preparar_carpetas(aj)
        self.addCleanup(S.configurar, S.configurar(aj))


class UsuariosTest(Base):
    def test_alta_contrasenas_y_estado(self):
        self.assertFalse(U.hay_usuarios())
        clave = U.crear("María José Pérez", "inicial1")
        self.assertEqual(clave, "maria-jose-perez")
        self.assertTrue(U.hay_usuarios())
        self.assertTrue(U.datos(clave)["cambiar"])
        with self.assertRaises(FileExistsError):
            U.crear("MARIA JOSE PEREZ", "otra123")
        with self.assertRaises(ValueError):
            U.crear("Ana", "corta")
        self.assertEqual(U.verificar("maria jose pérez", "inicial1"), clave)
        self.assertEqual(U.verificar("María José Pérez", "inicial1"), clave)
        self.assertIsNone(U.verificar(clave, "mal"))
        self.assertIsNone(U.verificar("nadie", "inicial1"))
        self.assertIn("actual", U.cambiar_propia(clave, "mal", "nueva123"))
        self.assertEqual(U.cambiar_propia(clave, "inicial1", "nueva123"), "")
        self.assertFalse(U.datos(clave)["cambiar"])
        self.assertEqual(U.verificar(clave, "nueva123"), clave)
        U.activar(clave, False)
        self.assertIsNone(U.verificar(clave, "nueva123"))
        self.assertFalse(U.hay_usuarios())
        U.activar(clave, True)
        U.renombrar(clave, "Majo Pérez")
        self.assertEqual(U.nombre_de(clave), "Majo Pérez")
        self.assertNotIn("nueva123", U.ARCH.read_text(encoding="utf-8"))

    def test_preferencias_y_formato(self):
        clave = U.crear("Ana", "inicial1")
        g = U.guardar_preferencias(clave, {"tema": "dark", "pref_salto": "5", "compacto": "1", "<x>": "y"})
        self.assertEqual(g, {"tema": "dark", "pref_salto": "5"})
        self.assertEqual(U.preferencias(clave), g)
        U.guardar_formato(clave, {"fuente": "Arial", "tamano_fuente": 11, "centrar_titulos": False})
        with self.assertRaises(ValueError):
            U.guardar_formato(clave, {"tamano_fuente": 99})
        with self.assertRaises(ValueError):
            U.guardar_formato(clave, {"fuente": "Comic"})
        cfg = U.cfg_de({"fuente": "Tahoma", "tamano_fuente": 12, "centrar_titulos": True, "otra": 1}, clave)
        self.assertEqual(cfg, {"fuente": "Arial", "tamano_fuente": 11, "centrar_titulos": False, "otra": 1})
        U.guardar_formato(clave, {"fuente": None, "tamano_fuente": None, "centrar_titulos": None})
        self.assertFalse(U.archivo(clave, "formato.json").exists())
        with self.assertRaises(ValueError):
            U.carpeta("../afuera")


class SesionesTest(Base):
    def test_sesion_usuario_activo_e_inactividad(self):
        a = R.nueva_sesion("info-01")
        self.assertIsNone(R.sesion(a)["usuario"])
        b = R.nueva_sesion("info-01", usuario="ana", reemplaza=a)
        self.assertIsNone(R.sesion(a))
        self.assertEqual(R.sesion(b)["usuario"], "ana")
        self.assertEqual(R.usuario_activo("info-01"), "ana")
        self.assertIsNone(R.usuario_activo("info-02"))
        # el archivo guarda huellas, nunca el identificador de la sesión
        self.assertNotIn(b, R.ARCH_SESIONES.read_text(encoding="utf-8"))
        R.SESIONES.clear()
        self.assertEqual(R.cargar_sesiones(), 1)
        self.assertEqual(R.sesion(b)["usuario"], "ana")
        for v in R.SESIONES.values():
            v["ult"] = time.time() - R.SESION_INACTIVA_SEG - 1
        self.assertIsNone(R.sesion(b))                 # se cerró la app: la sesión se cae sola
        c = R.nueva_sesion("info-01", usuario="ana")
        self.assertEqual(R.cerrar_sesiones_usuario("ana"), 1)
        self.assertIsNone(R.sesion(c))

    def test_sesion_en_uso_no_vence(self):
        # la app puede quedar abierta (escondida junto al reloj) varios días: mientras la página consulta, sigue
        sid = R.nueva_sesion("info-01", usuario="ana")
        v = next(iter(R.SESIONES.values()))
        v["exp"] = time.time() + 30                      # a punto de vencer
        self.assertEqual(R.sesion(sid)["usuario"], "ana")
        self.assertGreater(v["exp"], time.time() + R.SESION_SEG - 60)
        guardado = json.loads(R.ARCH_SESIONES.read_text(encoding="utf-8"))
        self.assertGreater(next(iter(guardado.values()))["exp"], time.time() + R.SESION_SEG - 60)
        # sin ninguna consulta en 12 h (PC apagada) sí se cierra
        v["ult"] = time.time() - R.SESION_INACTIVA_SEG - 1
        self.assertIsNone(R.sesion(sid))

    def test_cookie_sin_vencimiento(self):
        self.assertNotIn("Max-Age", R.cookie_sesion("x"))
        self.assertIn("Secure", R.cookie_sesion("x"))
        self.assertNotIn("Secure", R.cookie_sesion("x", local=True))


class CapasTest(Base):
    def test_plantillas_propias_y_generales(self):
        U.crear("Ana", "inicial1")
        nombres = [n for n, _ in PL.secciones_plantillas("ana")[1]]
        self.assertEqual(nombres, ["ECOGRAFÍA TIROIDEA", "MAMOGRAFÍA"])
        vistas = [(x["nombre"], x["cuerpo"]) for x in PL.secciones_con_origen("ana")]
        cambiadas = [(n, c + "\n- Frase propia de Ana." if n == "MAMOGRAFÍA" else c) for n, c in vistas]
        cambiadas.append(("ECOGRAFÍA RENAL", "TITULO: ECOGRAFÍA RENAL\n- Riñones normales."))
        r = PL.aplicar_plantillas(cambiadas, "ana", "mio")
        self.assertEqual(r["propias"], 2)
        self.assertNotIn("Frase propia", CON.leer("plantillas.md"))
        origen = {x["nombre"]: x["origen"] for x in PL.secciones_con_origen("ana")}
        self.assertEqual(origen, {"ECOGRAFÍA TIROIDEA": "general", "MAMOGRAFÍA": "propia", "ECOGRAFÍA RENAL": "nueva"})
        self.assertIn("Frase propia", PL.plantillas_relevantes("mamografía bilateral", usuario="ana"))
        self.assertNotIn("Frase propia", PL.plantillas_relevantes("mamografía bilateral"))
        self.assertNotIn("Frase propia", PL.plantillas_relevantes("mamografía bilateral", usuario="otro"))
        # una frase de la plantilla de cualquiera cuenta como frase de plantilla para los controles
        self.assertIn("- Frase propia de Ana.", PL.frases_de_plantilla())
        # borrar una general «solo para mí» no se puede: se avisa
        sin_tiroides = [(x["nombre"], x["cuerpo"]) for x in PL.secciones_con_origen("ana") if "TIROIDEA" not in x["nombre"]]
        r = PL.aplicar_plantillas(sin_tiroides, "ana", "mio")
        self.assertEqual(r["no_borradas"], ["ECOGRAFÍA TIROIDEA"])
        self.assertIn("ECOGRAFÍA TIROIDEA", CON.leer("plantillas.md"))
        # «para todos»: pasa a la general y deja de ser propia
        todas = [(x["nombre"], x["cuerpo"]) for x in PL.secciones_con_origen("ana")]
        todas = [(n, c.replace("Frase propia de Ana", "Frase de todos")) for n, c in todas]
        PL.aplicar_plantillas(todas, "ana", "todos")
        self.assertIn("Frase de todos", CON.leer("plantillas.md"))
        origen = {x["nombre"]: x["origen"] for x in PL.secciones_con_origen("ana")}
        self.assertEqual(origen["MAMOGRAFÍA"], "general")
        self.assertEqual(origen["ECOGRAFÍA RENAL"], "nueva")
        self.assertTrue(PL.volver_a_general("ana", "ECOGRAFÍA RENAL"))     # la que era solo suya se quita
        self.assertNotIn("ECOGRAFÍA RENAL", [x["nombre"] for x in PL.secciones_con_origen("ana")])
        self.assertFalse(PL.volver_a_general("ana", "ECOGRAFÍA RENAL"))
        actuales = [(x["nombre"], x["cuerpo"]) for x in PL.secciones_con_origen("ana")]
        self.assertEqual(PL.aplicar_plantillas(actuales, "ana", "todos")["sin_cambios"], True)

    def test_notas_reglas_y_prompt(self):
        U.crear("Ana", "inicial1")
        MED.guardar_medico("Dr. Ficticio", "Notas generales.", crear=True)
        self.assertIsNone(MED.notas_propias("Dr. Ficticio", "ana"))
        MED.guardar_notas_propias("Dr. Ficticio", "ana", "Notas de Ana.")
        self.assertEqual(MED.notas_medico("Dr. Ficticio", "ana"), "Notas de Ana.")
        self.assertEqual(MED.notas_medico("Dr. Ficticio"), "Notas generales.")
        self.assertEqual(MED.medicos_con_notas_propias("ana"), ["Dr. Ficticio"])
        MED.guardar_medico("Dr. Renombrado", "Notas generales.", original="Dr. Ficticio")
        self.assertEqual(MED.notas_medico("Dr. Renombrado", "ana"), "Notas de Ana.")
        U.escribir_archivo("ana", "reglas_dictado.md", "- Regla propia de Ana.\n")
        U.escribir_archivo("ana", "correcciones_aprendidas.md", "# x\n\n- Corrección propia de Ana.\n")
        ej = [{"dictado": "dictado ajeno", "informe": "INFORME", "usuario": "beto", "ajeno": True}]
        sis = PR.armar_mensajes("mamografía", ej, "Dr. Renombrado", usuario="ana")
        texto = sis[0]["content"]
        for esperado in ("Regla general ficticia", "Regla propia de Ana", "Notas de Ana.", "Corrección propia de Ana",
                         "OTRO transcriptor"):
            self.assertIn(esperado, texto)
        self.assertIn("ejemplo de otro transcriptor", sis[1]["content"])
        general = PR.armar_mensajes("mamografía", [], "Dr. Renombrado")[0]["content"]
        self.assertNotIn("Regla propia de Ana", general)
        self.assertIn("Notas generales.", general)

    def test_elegir_ejemplos_primero_los_propios(self):
        banco = [
            {"nombre": "a", "dictado": "mamografía bilateral densidad b", "informe": "x", "usuario": "beto"},
            {"nombre": "b", "dictado": "mamografía bilateral densidad c", "informe": "x", "usuario": "ana"},
            {"nombre": "c", "dictado": "mamografía bilateral densidad b nódulo", "informe": "x", "usuario": None},
            {"nombre": "d", "dictado": "ecografía tiroidea normal", "informe": "x", "usuario": "ana"},
        ]
        el = EJEM.elegir_ejemplos("mamografía bilateral densidad b dictada", banco, k=3, usuario="ana")
        self.assertEqual(el[0]["nombre"], "b")                 # propio y del mismo estudio primero
        self.assertNotIn("d", [e["nombre"] for e in el[:2]])   # propio pero de otro estudio: después
        self.assertTrue(next(e for e in el if e["nombre"] == "a").get("ajeno"))
        self.assertFalse(next(e for e in el if e["nombre"] == "c").get("ajeno"))
        sin = EJEM.elegir_ejemplos("mamografía bilateral densidad b dictada", banco, k=3)
        self.assertFalse(any(e.get("ajeno") for e in sin))


class CorreccionesTest(unittest.TestCase):
    def test_reparto_general_y_propio(self):
        k1, k2, k3, k4 = ("replace", "a", "b"), ("insert", "", "c"), ("delete", "d", ""), ("replace", "e", "f")
        fuentes = {k1: {"ana": 3}, k2: {"ana": 1, "beto": 1}, k3: {"": 2}, k4: {"": 1, "beto": 1}}
        gen, prop = AP.repartir_correcciones(fuentes)
        self.assertEqual({k for _, k in gen}, {k2, k3, k4})
        self.assertEqual(prop, {"ana": [(3, k1)]})
        gen, prop = AP.repartir_correcciones({k1: {"ana": 1}})
        self.assertEqual((gen, prop), ([], {}))


class AprendizajeTest(Base):
    def test_correcciones_por_transcriptor(self):
        U.crear("Ana", "inicial1"); U.crear("Beto", "inicial1")
        ia, final = "Patrón fibronodulillar difuso.\n", "Patrón fibronodular difuso.\n"
        for i, u in enumerate(("ana", "ana")):
            AP.registrar_ejemplo(f"caso{i}", "dictado ficticio", ia, final, clave=f"2026_{i}_caso{i}", usuario=u)
        propias = U.leer_archivo("ana", "correcciones_aprendidas.md")
        self.assertIn("fibronodular", propias)
        self.assertNotIn("fibronodular", AP.ARCH_CORR.read_text(encoding="utf-8"))
        self.assertEqual((AP.EJ / "2026_0_caso0.usuario.txt").read_text(encoding="utf-8"), "ana")
        banco = EJEM._leer_banco(self.d / "f1", self.d / "aud", AP.EJ)
        self.assertEqual({e["usuario"] for e in banco}, {"ana"})
        AP.registrar_ejemplo("caso9", "dictado ficticio", ia, final, clave="2026_9_caso9", usuario="beto")
        self.assertIn("fibronodular", AP.ARCH_CORR.read_text(encoding="utf-8"))     # la hicieron dos distintos
        self.assertFalse(U.archivo("ana", "correcciones_aprendidas.md").exists())
        # reconstruir desde los archivos da lo mismo
        AP.analizar_correcciones(reconstruir=True)
        self.assertIn("fibronodular", AP.ARCH_CORR.read_text(encoding="utf-8"))


class HttpTest(Base):
    def setUp(self):
        super().setUp()
        self.http = S.ThreadingHTTPServer(("127.0.0.1", 0), S.H)
        self.addCleanup(self.http.server_close)
        self.port = self.http.server_port
        p = patch.object(S, "PUERTO", self.port)
        p.start()
        self.addCleanup(p.stop)
        hilo = threading.Thread(target=self.http.serve_forever, daemon=True)
        hilo.start()
        self.addCleanup(hilo.join, 2)
        self.addCleanup(self.http.shutdown)

    def pedir(self, ruta, datos=None, cookie=None, extra=None, form=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        h = {"Content-Type": "application/json", "X-Panel": "1"}
        cuerpo = None if datos is None else json.dumps(datos)
        if form is not None:
            h["Content-Type"] = "application/x-www-form-urlencoded"
            cuerpo = urllib.parse.urlencode(form)
        if cookie:
            h["Cookie"] = cookie
        h.update(extra or {})
        c.request("GET" if cuerpo is None else "POST", ruta, cuerpo, h)
        r = c.getresponse()
        txt = r.read().decode("utf-8")
        galleta = r.getheader("Set-Cookie") or ""
        c.close()
        return r.status, (json.loads(txt) if txt.startswith("{") else txt), r.getheader("Location"), galleta

    def entrar(self, usuario, contrasena, extra=None, cookie=None):
        st, _, loc, galleta = self.pedir("/entrar", form={"usuario": usuario, "contrasena": contrasena},
                                         extra=extra, cookie=cookie)
        return st, loc, galleta.split(";")[0]

    def test_sin_usuarios_funciona_como_antes(self):
        self.assertEqual(self.pedir("/api/mi_pc")[1]["con_usuarios"], False)
        self.assertEqual(self.pedir("/api/plantillas")[0], 200)

    def test_flujo_con_usuarios(self):
        st, r, _, _ = self.pedir("/api/admin/usuarios/crear", {"nombre": "Ana", "contrasena": "inicial1"})
        self.assertEqual(st, 200, r)
        self.assertEqual(self.pedir("/api/casos")[0], 401)
        self.assertEqual(self.pedir("/")[2], "/ingresar")
        self.assertIn("Usuario", self.pedir("/ingresar")[1])
        self.assertEqual(self.entrar("ana", "mal")[0], 401)
        st, loc, galleta = self.entrar("ana", "inicial1")
        self.assertEqual((st, loc), (303, "/"))
        mi = self.pedir("/api/mi_pc", cookie=galleta)[1]
        self.assertEqual(mi["usuario"]["nombre"], "Ana")
        self.assertTrue(mi["usuario"]["cambiar"])
        self.assertIsNone(mi["preferencias"])
        self.assertEqual(self.pedir("/api/usuario/contrasena", {"actual": "inicial1", "nueva": "propia123"}, galleta)[0], 200)
        # plantillas solo para Ana
        secs = self.pedir("/api/plantillas", cookie=galleta)[1]["secciones"]
        secs = [{"nombre": x["nombre"], "cuerpo": x["cuerpo"] + ("\n- Propia." if x["nombre"] == "MAMOGRAFÍA" else "")}
                for x in secs]
        st, r, _, _ = self.pedir("/api/plantillas", {"secciones": secs, "destino": "mio"}, galleta)
        self.assertEqual((st, r["propias"]), (200, 1))
        self.assertNotIn("Propia", CON.leer("plantillas.md"))
        # notas propias de un médico
        MED.guardar_medico("Dr. Ficticio", "Generales.", crear=True)
        self.assertEqual(self.pedir("/api/medico", {"medico": "Dr. Ficticio", "notas": "De Ana.", "destino": "mio"},
                                    galleta)[0], 200)
        meds = self.pedir("/api/medicos", cookie=galleta)[1]["medicos"]
        self.assertEqual((meds[0]["notas"], meds[0]["propias"], meds[0]["generales"]), ("De Ana.", True, "Generales."))
        self.assertEqual(MED.notas_medico("Dr. Ficticio"), "Generales.")
        # preferencias y formato
        self.assertEqual(self.pedir("/api/usuario/preferencias", {"preferencias": {"tema": "dark"}}, galleta)[0], 200)
        self.assertEqual(self.pedir("/api/mi_pc", cookie=galleta)[1]["preferencias"], {"tema": "dark"})
        self.assertEqual(self.pedir("/api/usuario/formato", {"formato": {"tamano_fuente": 40}}, galleta)[0], 400)
        self.assertEqual(self.pedir("/api/usuario/formato", {"formato": {"tamano_fuente": 11}}, galleta)[0], 200)
        self.assertEqual(self.pedir("/api/formato", cookie=galleta)[1]["tamano"], 11)
        estilo = self.pedir("/api/usuario/estilo", cookie=galleta)[1]
        self.assertEqual((estilo["plantillas_propias"], estilo["medicos_propios"]), (["MAMOGRAFÍA"], ["Dr. Ficticio"]))
        # el panel lo muestra con su estilo y su sesión
        u = self.pedir("/api/admin/estado")[1]["usuarios"][0]
        self.assertEqual((u["nombre"], u["en"], u["propio"]["plantillas"]), ("Ana", ["Servidor"], 1))
        # salir
        self.assertEqual(self.pedir("/salir", cookie=galleta)[2], "/ingresar")
        self.assertEqual(self.pedir("/api/casos", cookie=galleta)[0], 401)
        # desactivado: no entra más (con otro activo; sin ninguno activo el sistema vuelve a no pedir usuario)
        self.assertEqual(self.pedir("/api/admin/usuarios/crear", {"nombre": "Beto", "contrasena": "inicial2"})[0], 200)
        self.pedir("/api/admin/usuarios/activo", {"usuario": "ana", "activo": False})
        self.assertEqual(self.entrar("ana", "propia123")[0], 401)
        self.pedir("/api/admin/usuarios/activo", {"usuario": "beto", "activo": False})
        self.assertEqual(self.pedir("/api/casos")[0], 200)

    def test_guardar_word_con_transcriptor(self):
        # regresión: «registro.actividad() got multiple values for keyword argument 'usuario'»
        from unittest.mock import MagicMock
        from transcripcion.base import registro as L
        datos = self.d / "Informes" / "revision" / "datos"
        datos.mkdir(parents=True, exist_ok=True)
        n = "Servidor_20261102-120000_ficticio"
        (datos / f"{n}.informe_ia.txt").write_text("MAMOGRAFÍA\n\n-Mamas de densidad tipo B.\n", encoding="utf-8")
        (datos / f"{n}.dictado.txt").write_text("mamografía densidad b", encoding="utf-8")
        (datos / f"{n}.usuario.txt").write_text("beto", encoding="utf-8")
        cola = MagicMock()
        for obj, nombre, valor in ((S, "DATOS", datos), (S, "INFORMES", self.d / "Informes"), (S, "APRENDIZAJE", cola),
                                   (L, "CARPETA", self.d / "registros")):
            p = patch.object(obj, nombre, valor); p.start(); self.addCleanup(p.stop)
        U.crear("Ana", "inicial1"); U.crear("Beto", "inicial1")
        _, _, galleta = self.entrar("ana", "inicial1")
        st, r, _, _ = self.pedir("/api/finalizar", {"nombre": n, "texto": "MAMOGRAFÍA\n\n-Mamas de densidad tipo C.\n"},
                                 galleta)
        self.assertEqual(st, 200, r)
        self.assertTrue((self.d / "Informes" / f"{n}.docx").exists())
        self.assertEqual(cola.agregar.call_args[0][0]["usuario"], "ana")   # el ejemplo es de quien lo revisó
        csv = (self.d / "registros" / "actividad.csv").read_text(encoding="utf-8-sig")
        self.assertIn("Ana", csv.splitlines()[-1])

    def test_vincular_abre_la_pagina_con_ese_usuario(self):
        U.crear("Ana", "inicial1")
        remoto = {"Cf-Ray": "prueba"}
        st, r, _, _ = self.pedir("/api/cliente/vincular", {"pc": "info-03", "usuario": "Ana", "contrasena": "inicial1"},
                                 extra=remoto)
        self.assertEqual(st, 200, r)
        st, _, loc, galleta = self.pedir("/entrar?codigo=" + r["codigo"], extra=remoto)
        self.assertEqual(loc, "/")
        mi = self.pedir("/api/mi_pc", cookie=galleta.split(";")[0], extra=remoto)[1]
        self.assertEqual((mi["pc"], mi["usuario"]["nombre"]), ("info-03", "Ana"))     # no pide el usuario otra vez
        self.assertEqual(self.pedir("/entrar?codigo=" + r["codigo"], extra=remoto)[0], 200)   # un solo uso: formulario
        # sin transcriptores no hay código con usuario
        st, r2, _, _ = self.pedir("/api/cliente/vincular", {"pc": "info-04", "usuario": "Nadie", "contrasena": "x"},
                                  extra=remoto)
        self.assertEqual(st, 403)

    def test_servidor_reiniciado_no_pide_entrar_de_nuevo(self):
        U.crear("Ana", "inicial1")
        remoto = {"Cf-Ray": "prueba"}
        st, r, _, _ = self.pedir("/api/cliente/vincular", {"pc": "info-05", "usuario": "Ana", "contrasena": "inicial1"},
                                 extra=remoto)
        llave = {"Authorization": "Bearer " + r["llave"], **remoto}
        galleta = self.pedir("/entrar?codigo=" + r["codigo"], extra=remoto)[3].split(";")[0]
        self.assertEqual(self.pedir("/api/casos", cookie=galleta, extra=remoto)[0], 200)
        # el servidor se reinicia: las sesiones se recuperan de sesiones.json
        R.SESIONES.clear()
        R.cargar_sesiones()
        self.assertEqual(self.pedir("/api/casos", cookie=galleta, extra=remoto)[0], 200)
        # la app vuelve a abrir la pantalla con un código nuevo (app 1.23, sin «reconectar»): se conserva la sesión
        cod = self.pedir("/api/cliente/sesion", {}, extra=llave)[1]["codigo"]
        st, _, loc, nueva = self.pedir("/entrar?codigo=" + cod, cookie=galleta, extra=remoto)
        self.assertEqual((loc, nueva), ("/", ""))
        self.assertEqual(self.pedir("/api/casos", cookie=galleta, extra=remoto)[0], 200)
        # dirección nueva del túnel (otra cookie, vacía): con «reconectar» sigue la misma persona
        cod = self.pedir("/api/cliente/sesion", {"reconectar": True}, extra=llave)[1]["codigo"]
        st, _, loc, otra = self.pedir("/entrar?codigo=" + cod, extra=remoto)
        mi = self.pedir("/api/mi_pc", cookie=otra.split(";")[0], extra=remoto)[1]
        self.assertEqual(mi["usuario"]["nombre"], "Ana")
        # la app abierta de cero (sin «reconectar») pide el usuario
        cod = self.pedir("/api/cliente/sesion", {}, extra=llave)[1]["codigo"]
        st, _, loc, sin = self.pedir("/entrar?codigo=" + cod, extra=remoto)
        self.assertEqual(self.pedir("/api/mi_pc", cookie=sin.split(";")[0], extra=remoto)[0], 401)
        # después de «Cerrar sesión», reconectar tampoco devuelve a nadie
        for g in (galleta, otra.split(";")[0]):
            self.pedir("/salir", cookie=g, extra=remoto)
        cod = self.pedir("/api/cliente/sesion", {"reconectar": True}, extra=llave)[1]["codigo"]
        st, _, loc, sin = self.pedir("/entrar?codigo=" + cod, extra=remoto)
        self.assertEqual(self.pedir("/api/mi_pc", cookie=sin.split(";")[0], extra=remoto)[0], 401)

    def test_app_conectada_a_127_0_0_1(self):
        # la app de pruebas en la PC del servidor: los pedidos llegan como locales, con la llave de la PC
        U.crear("Ana", "inicial1")
        st, r, _, _ = self.pedir("/api/cliente/vincular", {"pc": "pc-test", "usuario": "ana", "contrasena": "inicial1"})
        self.assertEqual(st, 200, r)
        llave = {"Authorization": "Bearer " + r["llave"]}
        self.assertEqual(self.pedir("/api/cliente/estado", extra=llave)[0], 200)
        self.assertEqual(self.pedir("/api/cliente/estado")[0], 401)
        self.assertEqual(self.pedir("/api/casos", extra=llave)[0], 401)       # los informes, solo con usuario
        cod = self.pedir("/api/cliente/sesion", {}, extra=llave)[1]["codigo"]
        st, _, loc, galleta = self.pedir("/entrar?codigo=" + cod)
        self.assertEqual((st, loc), (303, "/"))
        self.assertNotIn("Secure", galleta)                  # http://127.0.0.1: si no, el navegador la descarta
        self.assertEqual(self.pedir("/", cookie=galleta.split(";")[0])[2], "/ingresar")

    def test_trabajo_usuario_reemplaza_contrasena_compartida(self):
        R.poner_contrasena("compartida1")
        remoto = {"Cf-Ray": "prueba"}
        # sin transcriptores: como antes
        st, r, _, _ = self.pedir("/api/cliente/vincular", {"pc": "info-01", "contrasena": "compartida1"}, extra=remoto)
        self.assertEqual(st, 200, r)
        U.crear("Ana", "inicial1")
        st, r, _, _ = self.pedir("/api/cliente/vincular", {"pc": "info-02", "contrasena": "compartida1"}, extra=remoto)
        self.assertEqual(st, 403)
        st, r, _, _ = self.pedir("/api/cliente/vincular", {"pc": "info-02", "usuario": "Ana", "contrasena": "inicial1"},
                                 extra=remoto)
        self.assertEqual(st, 200, r)
        llave = {"Authorization": "Bearer " + r["llave"], **remoto}
        # la llave sola sirve para lo que la app hace sin nadie, no para ver informes
        self.assertEqual(self.pedir("/api/cliente/estado", extra=llave)[0], 200)
        self.assertEqual(self.pedir("/api/casos", extra=llave)[0], 401)
        # la app entra con un código: la PC queda identificada y la persona escribe su usuario
        cod = self.pedir("/api/cliente/sesion", {}, extra=llave)[1]["codigo"]
        st, _, loc, galleta = self.pedir("/entrar?codigo=" + cod, extra=remoto)
        galleta = galleta.split(";")[0]
        self.assertEqual(self.pedir("/api/casos", cookie=galleta, extra=remoto)[0], 401)
        # la página no va a /entrar (la app lo intercepta para volver a entrar con la llave) sino a /ingresar
        self.assertEqual(self.pedir("/", cookie=galleta, extra=remoto)[2], "/ingresar")
        pagina = self.pedir("/ingresar", cookie=galleta, extra=remoto)[1]
        self.assertIn('action="/ingresar"', pagina)
        self.assertIn("info-02", pagina)
        self.assertNotIn('name="pc"', pagina)
        self.assertEqual(self.entrar("ana", "compartida1", extra=remoto, cookie=galleta)[0], 401)
        st, loc, g2 = self.entrar("ana", "inicial1", extra=remoto, cookie=galleta)
        self.assertEqual(st, 303)
        self.assertEqual(self.pedir("/api/casos", cookie=g2, extra=remoto)[0], 200)
        self.assertEqual(self.pedir("/api/casos", cookie=galleta, extra=remoto)[0], 401)   # la anterior se reemplazó
        self.assertEqual(R.usuario_activo("info-02"), "ana")
        # al salir la PC sigue identificada: el siguiente solo pone su usuario
        st, _, loc, g3 = self.pedir("/salir", cookie=g2, extra=remoto)
        self.assertEqual(loc, "/ingresar")
        self.assertNotIn('name="pc"', self.pedir("/ingresar", cookie=g3.split(";")[0], extra=remoto)[1])
        # sin ninguna sesión, por el túnel se va a /entrar (la app ahí vuelve a entrar sola con su llave)
        self.assertEqual(self.pedir("/", extra=remoto)[2], "/entrar")
        self.assertEqual(self.pedir("/ingresar", extra=remoto)[2], "/entrar")


if __name__ == "__main__":
    unittest.main()
