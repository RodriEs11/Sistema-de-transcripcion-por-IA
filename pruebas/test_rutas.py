"""Tabla de rutas HTTP (docs/refactor.md, etapa 6c): qué función atiende cada ruta y cómo se procesa un POST.

Complementa al contrato HTTP (caja negra): acá se prueba la tabla y el despacho del manejador en el mismo proceso.
"""
import http.client
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

import servidor as S  # noqa: E402
from transcripcion import ajustes  # noqa: E402
from transcripcion.acceso import remoto as R  # noqa: E402
from transcripcion.http.manejador import Manejador  # noqa: E402
from transcripcion.http.rutas import Rutas  # noqa: E402
from transcripcion.http.tabla import RUTAS  # noqa: E402

# Si cambia, que sea a propósito: una ruta que desaparece de la tabla deja de existir para la página o la app.
ESPERADAS = [
    ("GET", "/entrar", "acceso.entrar_get"),
    ("GET", "/ingresar", "acceso.ingresar_get"),
    ("GET", "/salir", "acceso.salir"),
    ("GET", "/", "paginas.principal"),
    ("GET", "/index.html", "paginas.principal"),
    ("GET", "/editor_word.js", "paginas.editor_word"),
    ("GET", "/css/principal.css", "paginas.estilos"),
    ("GET", "/js/principal.js", "paginas.script"),
    ("GET", "/admin", "panel.consultar"),
    ("GET", "/admin/estadisticas", "panel.consultar"),
    ("GET", "/admin/correcciones", "panel.consultar"),
    ("GET", "/admin/medicos", "panel.consultar"),
    ("GET", "/api/mi_pc", "usuario.mi_pc"),
    ("GET", "/api/usuario/estilo", "usuario.estilo"),
    ("GET", "/api/cliente/estado", "cliente.estado"),
    ("GET", "/api/cliente/actualizacion", "cliente.actualizacion"),
    ("GET", "/api/cliente/archivo", "cliente.archivo"),
    ("GET", "/api/word", "casos.word"),
    ("GET", "/api/casos", "casos.lista"),
    ("GET", "/api/formato", "conocimiento.formato"),
    ("GET", "/api/medicos", "conocimiento.medicos"),
    ("GET", "/api/voces", "voces.resumen"),
    ("GET", "/api/voces/muestras", "voces.muestras"),
    ("GET", "/api/voces/agrupar", "voces.agrupar"),
    ("GET", "/api/plantillas", "conocimiento.plantillas"),
    ("GET", "/api/caso", "casos.caso"),
    ("GET", "/api/onda", "casos.onda"),
    ("POST", "/entrar", "acceso.entrar_post"),
    ("POST", "/ingresar", "acceso.entrar_post"),
    ("POST", "/api/cliente/vincular", "cliente.vincular"),
    ("POST", "/api/cliente/sesion", "cliente.sesion"),
    ("POST", "/api/cliente/aviso", "cliente.aviso"),
    ("POST", "/api/cliente/audio", "cliente.audio"),
    ("POST", "/api/plantilla_word", "conocimiento.plantilla_word"),
    ("POST", "/api/subir", "audios.subir"),
    ("POST", "/api/vista_previa", "casos.vista_previa"),
    ("POST", "/api/admin/entrar", "panel.entrar"),
    ("POST", "/api/admin/salir", "panel.salir"),
    ("POST", "/api/medico", "conocimiento.medico"),
    ("POST", "/api/voces/etiquetar", "voces.etiquetar"),
    ("POST", "/api/voces/quitar", "voces.quitar"),
    ("POST", "/api/importar", "conocimiento.importar_referencias"),
    ("POST", "/api/plantillas", "conocimiento.guardar_plantillas"),
    ("POST", "/api/plantillas/general", "conocimiento.plantilla_general"),
    ("POST", "/api/borrar", "casos.borrar"),
    ("POST", "/api/caso/pausar", "edicion.pausar_o_reanudar"),
    ("POST", "/api/caso/reanudar", "edicion.pausar_o_reanudar"),
    ("POST", "/api/caso/bloquear", "edicion.bloquear"),
    ("POST", "/api/caso/soltar", "edicion.soltar"),
    ("POST", "/api/caso_medico", "edicion.medico"),
    ("POST", "/api/paciente", "edicion.paciente"),
    ("POST", "/api/procesar", "edicion.procesar"),
    ("POST", "/api/borrador", "edicion.borrador"),
    ("POST", "/api/formato_caso", "edicion.formato"),
    ("POST", "/api/formato_caso/agregar", "edicion.formato_agregar"),
    ("POST", "/api/finalizar", "edicion.finalizar"),
    ("POST", "/api/abrir", "edicion.abrir_word"),
    ("GET", "/api/admin/…", "panel.consultar"),
    ("GET", "/audio/…", "casos.audio"),
    ("POST", "/api/admin/…", "panel.accion"),
    ("POST", "/api/usuario/…", "usuario.accion"),
]


class Tabla(unittest.TestCase):
    def test_rutas_esperadas(self):
        actuales = [(m, r, f"{f.__module__.rsplit('.', 1)[1]}.{f.__name__}") for m, r, f in RUTAS.listado()]
        self.assertEqual(sorted(actuales), sorted(ESPERADAS))

    def test_las_funciones_son_del_paquete_http(self):
        for m, r, f in RUTAS.listado():
            with self.subTest(ruta=f"{m} {r}"):
                self.assertTrue(f.__module__.startswith("transcripcion.http."))

    def test_fases_de_los_post(self):
        crudas = {"/entrar", "/ingresar", "/api/cliente/vincular", "/api/cliente/sesion", "/api/cliente/aviso",
                  "/api/cliente/audio", "/api/plantilla_word", "/api/subir"}
        libres = {"/api/caso_medico", "/api/paciente", "/api/procesar", "/api/borrador", "/api/formato_caso",
                  "/api/formato_caso/agregar", "/api/finalizar"}
        for m, r, _ in RUTAS.listado():
            if m != "POST" or r.endswith("…"):
                continue
            ruta = RUTAS.buscar("POST", r)
            with self.subTest(ruta=r):
                self.assertEqual(ruta.fase == "cruda", r in crudas)
                self.assertEqual(ruta.libre, r in libres)

    def test_exactas_antes_que_prefijos_y_sin_repetidas(self):
        self.assertEqual(RUTAS.buscar("POST", "/api/admin/entrar").funcion.__name__, "entrar")
        self.assertEqual(RUTAS.buscar("POST", "/api/admin/mensaje").funcion.__name__, "accion")
        self.assertIsNone(RUTAS.buscar("GET", "/api/no_existe"))
        t = Rutas()
        t.get("/x", print)
        with self.assertRaises(ValueError):
            t.get("/x", print)
        with self.assertRaises(ValueError):
            t.post("/y", print, "otra")

    def test_cada_sistema_tiene_su_manejador(self):
        a, b = object(), object()
        self.assertIs(Manejador.para(a).sis, a)
        self.assertIs(Manejador.para(b).sis, b)
        self.assertIsNone(Manejador.sis)


class Despacho(unittest.TestCase):
    """Lo que hace do_POST antes de llegar a la función, igual que la cadena de `if` de antes."""

    def setUp(self):
        respaldo = RAIZ / "respaldo"
        respaldo.mkdir(exist_ok=True)
        tmp = tempfile.TemporaryDirectory(prefix="rutas_", dir=respaldo)
        self.addCleanup(tmp.cleanup)
        aj = ajustes.para_pruebas(Path(tmp.name))
        ajustes.preparar_carpetas(aj)
        self.addCleanup(S.configurar, S.configurar(aj))
        self.http = S.ThreadingHTTPServer(("127.0.0.1", 0), S.H)
        self.addCleanup(self.http.server_close)
        p = patch.object(S.SIS, "puerto", self.http.server_port)
        p.start()
        self.addCleanup(p.stop)
        hilo = threading.Thread(target=self.http.serve_forever, daemon=True)
        hilo.start()
        self.addCleanup(hilo.join, 2)
        self.addCleanup(self.http.shutdown)

    def pedir(self, metodo, ruta, cuerpo=None, cabeceras=None):
        c = http.client.HTTPConnection("127.0.0.1", self.http.server_port, timeout=10)
        try:
            c.request(metodo, ruta, body=cuerpo if isinstance(cuerpo, bytes) or cuerpo is None
                      else json.dumps(cuerpo).encode("utf-8"), headers=cabeceras or {})
            r = c.getresponse()
            d = r.read()
            return r.status, (json.loads(d) if "json" in (r.getheader("Content-Type") or "") else d)
        finally:
            c.close()

    def test_post_desconocido_valida_el_nombre_antes_del_404(self):
        self.assertEqual(self.pedir("POST", "/api/no_existe", {})[0], 400)
        self.assertEqual(self.pedir("POST", "/api/no_existe", {"nombre": "../x"})[1], {"error": "nombre inválido"})
        self.assertEqual(self.pedir("POST", "/api/no_existe", {"nombre": "caso"})[0], 404)

    def test_json_invalido_es_error_del_servidor(self):
        st, d = self.pedir("POST", "/api/borrar", b"{no es json")
        self.assertEqual(st, 500)
        self.assertIn("error", d)

    def test_caso_abierto_en_otra_pc_no_se_modifica(self):
        R.bloquear("caso-ajeno", "info-07")
        self.addCleanup(R.BLOQUEOS.pop, "caso-ajeno", None)
        st, d = self.pedir("POST", "/api/borrador", {"nombre": "caso-ajeno", "html": "<p>x</p>"})
        self.assertEqual((st, d), (409, {"error": "Este caso lo está revisando info-07."}))
        st, d = self.pedir("POST", "/api/abrir", {"nombre": "caso-ajeno"})    # abrir el Word no exige el caso libre
        self.assertEqual((st, d), (200, {"ok": False}))

    def test_paginas_desde_web_plantillas(self):
        st, html = self.pedir("GET", "/entrar", cabeceras={"Cf-Connecting-Ip": "10.0.0.9"})   # navegador del trabajo
        self.assertEqual(st, 200)
        self.assertIn(b'<form method="post" action="/entrar">', html)
        self.assertIn(b"Nombre de esta PC", html)
        self.assertNotIn(b"{{", html)
        self.assertTrue(html.endswith(b"</html>"))
        from transcripcion.http.panel import pagina_panel_entrar
        p = pagina_panel_entrar(S.SIS, "info-01", "/admin/medicos")
        self.assertIn('const VOLVER = "/admin/medicos";', p)
        self.assertIn("<b>info-01</b>", p)

    def test_script_y_estilos_de_la_pagina_principal_son_sus_partes_en_orden(self):
        """web/js/principal/ y web/css/principal/ se envían unidos, como cuando estaban dentro de index.html."""
        for ruta, carpeta, tipo in (("/js/principal.js", "js", "text/javascript"), ("/css/principal.css", "css", "text/css")):
            with self.subTest(ruta=ruta):
                partes = sorted((RAIZ / "web" / carpeta / "principal").glob(f"*.{carpeta}"))
                self.assertGreater(len(partes), 5)
                c = http.client.HTTPConnection("127.0.0.1", self.http.server_port, timeout=10)
                try:
                    c.request("GET", ruta)
                    r = c.getresponse()
                    cuerpo = r.read().decode("utf-8")
                    self.assertEqual(r.status, 200)
                    self.assertTrue(r.getheader("Content-Type").startswith(tipo))
                    self.assertEqual(r.getheader("Cache-Control"), "no-store")
                finally:
                    c.close()
                self.assertEqual(cuerpo, "".join(p.read_text(encoding="utf-8") for p in partes))
        index = (RAIZ / "web" / "index.html").read_text(encoding="utf-8")
        self.assertIn('<script src="/js/principal.js"></script>', index)
        self.assertLess(index.index("/js/principal.js"), index.index("/editor_word.js"))


if __name__ == "__main__":
    unittest.main()
