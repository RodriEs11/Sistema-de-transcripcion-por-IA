"""Contrato HTTP del servidor, probado desde afuera (caja negra).

Red de seguridad del refactor (docs/refactor.md, etapa 0): levanta `servidor.py` en un subproceso, en modo
simulado (sin Whisper ni Ollama), sobre una COPIA del código en una carpeta temporal con datos ficticios.
Recorre el flujo diario completo por HTTP: página, lista, subir audio, procesar, abrir el caso, guardar
borrador, guardar Word, descargarlo y borrar el caso.

Como no importa ningún módulo del sistema ni toca sus variables globales, esta prueba no cambia cuando el
código se reorganiza por dentro: si deja de pasar después de un refactor, cambió el comportamiento.
Solo puede cambiar junto con un cambio funcional deliberado (y documentado en docs/api.md).
"""
import http.client
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import wave

RAIZ = Path(__file__).resolve().parents[1]
CASO = "contrato_ficticio"
DICTADO = ("Ecografía tiroidea. Glándula tiroides de forma y tamaño normal. "
           "Lóbulo derecho mide 45 por 15 milímetros. Fin.")
INFORME_IA = ("ECOGRAFÍA TIROIDEA\n\n-Glándula tiroides de forma y tamaño normal.\n"
              "-Lóbulo derecho de 45 x 15 mm.\n\nLo saluda atte.")


def _puerto_libre():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _copiar_sistema(destino):
    """Copia solo lo versionado que necesita el servidor para arrancar (nunca datos de la instalación)."""
    destino.mkdir()
    for p in RAIZ.glob("*.py"):
        shutil.copy2(p, destino / p.name)
    for p in RAIZ.iterdir():     # paquetes de Python (la estructura destino del refactor: transcripcion/, …)
        if p.is_dir() and (p / "__init__.py").exists():
            shutil.copytree(p, destino / p.name, ignore=shutil.ignore_patterns("__pycache__"))
    for nombre in ("configuracion.ejemplo.json", "vocabulario.txt"):
        if (RAIZ / nombre).exists():
            shutil.copy2(RAIZ / nombre, destino / nombre)
    shutil.copytree(RAIZ / "web", destino / "web")
    shutil.copytree(RAIZ / "conocimiento.ejemplo", destino / "conocimiento.ejemplo")
    (destino / "cliente").mkdir()
    for p in (RAIZ / "cliente").glob("*"):
        if p.is_file() and p.name in ("LEEME.txt", "Transcripcion.exe.config"):
            shutil.copy2(p, destino / "cliente" / p.name)
    (destino / "respaldo").mkdir()


def _palabras(texto):
    """Palabras con tiempos ficticios, con la misma forma que devuelve fase1_transcribir.transcribir."""
    out, t = [], 0.0
    for w in texto.split():
        out.append({"p": " " + w, "ini": round(t, 2), "fin": round(t + 0.3, 2), "conf": 0.95})
        t += 0.35
    return out


def _wav(ruta, segundos=2.0, sr=16000):
    with wave.open(str(ruta), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(b"\x00\x10" * int(segundos * sr))


class ContratoHTTP(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        RAIZ.joinpath("respaldo").mkdir(exist_ok=True)
        cls.tmp = tempfile.TemporaryDirectory(prefix="contrato_http_", dir=RAIZ / "respaldo")
        base = Path(cls.tmp.name)
        cls.sistema = base / "sistema"
        cls.nuevos = base / "Audios_nuevos"
        cls.informes = base / "Informes"
        _copiar_sistema(cls.sistema)
        for sub, obj in (("fase1/json", {"con_vocab": {"texto": DICTADO, "palabras": _palabras(DICTADO)}}),
                         ("fase2/gemma4_12b", {"salida": INFORME_IA})):
            d = cls.sistema / "resultados" / sub
            d.mkdir(parents=True)
            (d / f"{CASO}.json").write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")
        cls.puerto = _puerto_libre()
        env = dict(os.environ, SIMULAR_IA="1", SIMULAR_DEMORA="0", PYTHONIOENCODING="utf-8",
                   PUERTO_INTERFAZ=str(cls.puerto), PUERTO_TUNEL=str(_puerto_libre()))
        env.pop("SIMULAR_SIN_IA", None)
        # Sin internet para el subproceso: que no baje el modelo de voz (26 MB) en cada corrida. Las direcciones
        # locales no pasan por el proxy. Ver docs/refactor.md, etapa 1 (dependencias explícitas).
        for var in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"):
            env[var] = "http://127.0.0.1:9"
        env["NO_PROXY"] = env["no_proxy"] = "127.0.0.1,localhost"
        cls.log = open(base / "servidor.log", "wb")
        cls.proc = subprocess.Popen([sys.executable, "servidor.py", "--sin-navegador"], cwd=cls.sistema,
                                    env=env, stdout=cls.log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
        limite = time.time() + 60
        while True:
            try:
                if cls.pedir("GET", "/api/casos")[0] == 200:
                    break
            except OSError:
                pass
            if cls.proc.poll() is not None or time.time() > limite:
                cls._cerrar()
                raise RuntimeError("El servidor no arrancó:\n" + cls._log())
            time.sleep(0.2)

    @classmethod
    def _log(cls, completo=False):
        cls.log.flush()
        texto = (Path(cls.tmp.name) / "servidor.log").read_text(encoding="utf-8", errors="replace")
        return texto if completo else texto[-4000:]

    @classmethod
    def _cerrar(cls):
        if cls.proc.poll() is None:
            cls.proc.terminate()
            try:
                cls.proc.wait(15)
            except subprocess.TimeoutExpired:
                cls.proc.kill()
                cls.proc.wait(5)
        cls.log.close()
        cls.tmp.cleanup()

    @classmethod
    def tearDownClass(cls):
        cls._cerrar()

    @classmethod
    def pedir(cls, metodo, ruta, cuerpo=None, json_=True, cabeceras=None):
        c = http.client.HTTPConnection("127.0.0.1", cls.puerto, timeout=20)
        try:
            if isinstance(cuerpo, (dict, list)):
                cuerpo = json.dumps(cuerpo).encode("utf-8")
            h = {"Host": f"127.0.0.1:{cls.puerto}", **(cabeceras or {})}
            c.request(metodo, ruta, body=cuerpo, headers=h)
            r = c.getresponse()
            datos = r.read()
            if json_ and "json" in (r.getheader("Content-Type") or ""):
                return r.status, json.loads(datos.decode("utf-8"))
            return r.status, datos
        finally:
            c.close()

    def esperar_estado(self, estados, segundos=60):
        limite, ultimo = time.time() + segundos, None
        while time.time() < limite:
            st, d = self.pedir("GET", "/api/casos")
            self.assertEqual(st, 200)
            caso = next((c for c in d["casos"] if c["nombre"] == CASO), None)
            ultimo = caso
            if caso and caso["estado"] in estados:
                return caso
            if caso and caso["estado"] == "error":
                self.fail(f"El caso terminó en error: {caso}\n{self._log()}")
            time.sleep(0.2)
        self.fail(f"El caso no llegó a {estados}; último: {ultimo}\n{self._log()}")

    def test_flujo_completo(self):
        # Página principal y lista vacía
        st, html = self.pedir("GET", "/", json_=False)
        self.assertEqual(st, 200)
        self.assertIn(b"<html", html.lower())
        st, d = self.pedir("GET", "/api/casos")
        self.assertEqual(st, 200)
        for clave in ("casos", "ollama", "pc", "ia_estado", "modelo", "mensaje", "pausa"):
            self.assertIn(clave, d)
        self.assertEqual(d["casos"], [])
        self.assertTrue(d["ollama"])

        # Estado para la app del trabajo
        st, d = self.pedir("GET", "/api/cliente/estado")
        self.assertEqual(st, 200)
        self.assertIn("app", d)

        # Subir un audio: se encola y el procesamiento simulado lo deja para revisar
        wav = Path(self.tmp.name) / f"{CASO}.wav"
        _wav(wav)
        st, d = self.pedir("POST", f"/api/subir?archivo={CASO}.wav", wav.read_bytes(),
                           cabeceras={"Content-Type": "application/octet-stream"})
        self.assertEqual(st, 200, d)
        self.assertEqual(d, {"ok": True, "nombre": CASO})
        self.assertTrue((self.nuevos / f"{CASO}.wav").exists())
        caso = self.esperar_estado(("listo",))
        for clave in ("nombre", "estado", "marcas", "medico", "origen", "avisos", "titulo", "paciente",
                      "estudios", "dur", "puede_borrar", "fecha"):
            self.assertIn(clave, caso)
        self.assertEqual(caso["origen"], "Servidor")
        self.assertTrue(caso["puede_borrar"])

        # Abrir el caso: dictado con palabras y tiempos, informe y marcas
        st, d = self.pedir("GET", f"/api/caso?nombre={CASO}")
        self.assertEqual(st, 200, d)
        texto = json.dumps(d, ensure_ascii=False)
        self.assertIn("Lóbulo derecho", texto)
        self.assertIn("Glándula tiroides", texto)
        st, d = self.pedir("GET", f"/api/onda?nombre={CASO}")
        self.assertEqual(st, 200)

        # Borrador con control de revisión
        st, d = self.pedir("POST", "/api/borrador", {"nombre": CASO, "html": "<p>ECOGRAFÍA TIROIDEA</p>"})
        self.assertEqual(st, 200, d)
        self.assertTrue(d.get("ok"))
        rev = d["revision"]
        st, d = self.pedir("POST", "/api/borrador", {"nombre": CASO, "html": "<p>segunda</p>", "revision": rev})
        self.assertEqual(st, 200, d)
        self.assertEqual(d["revision"], rev + 1)
        # Otra sesión con la revisión vieja y contenido distinto: conflicto, no se pisa
        st, d = self.pedir("POST", "/api/borrador", {"nombre": CASO, "html": "<p>otra</p>", "revision": rev})
        self.assertEqual(st, 409, d)
        st, d = self.pedir("POST", "/api/borrador", {"nombre": CASO, "html": "<p>x</p>", "revision": "vieja"})
        self.assertEqual(st, 400, d)

        # Guardar Word: crea el .docx y el caso pasa a revisado
        st, d = self.pedir("POST", "/api/finalizar", {"nombre": CASO, "texto": INFORME_IA})
        self.assertEqual(st, 200, d)
        self.assertNotIn("error", d)
        self.assertTrue((self.informes / f"{CASO}.docx").exists())
        self.esperar_estado(("revisado",))
        st, docx = self.pedir("GET", f"/api/word?nombre={CASO}", json_=False)
        self.assertEqual(st, 200)
        self.assertTrue(docx.startswith(b"PK"), "el Word descargado no es un .docx")

        # Validación de nombres: nada de rutas
        st, _ = self.pedir("GET", "/api/caso?nombre=../configuracion")
        self.assertGreaterEqual(st, 400)

        # Borrar el caso
        st, d = self.pedir("POST", "/api/borrar", {"nombres": [CASO]})
        self.assertEqual(st, 200, d)
        st, d = self.pedir("GET", "/api/casos")
        self.assertEqual([c["nombre"] for c in d["casos"]], [])

        # Ningún error inesperado del lado del servidor durante todo el flujo
        time.sleep(0.5)      # el aprendizaje sigue en segundo plano después de guardar
        self.assertNotIn("Traceback", self._log(completo=True), self._log())

    def test_formato_y_vista_previa(self):
        st, d = self.pedir("GET", "/api/formato")
        self.assertEqual(st, 200)
        self.assertIsInstance(d, dict)
        st, d = self.pedir("POST", "/api/vista_previa", {"texto": INFORME_IA})
        self.assertEqual(st, 200, d)
        self.assertIn("Lo saluda atte.", json.dumps(d, ensure_ascii=False))

    def test_conocimiento_de_ejemplo(self):
        st, d = self.pedir("GET", "/api/plantillas")
        self.assertEqual(st, 200)
        self.assertTrue(json.dumps(d, ensure_ascii=False).strip("{}[] "), "sin plantillas")
        st, d = self.pedir("GET", "/api/medicos")
        self.assertEqual(st, 200)
        st, d = self.pedir("GET", "/api/mi_pc")
        self.assertEqual(st, 200)
        self.assertIn("pc", d)

    def test_admin_solo_local_y_con_cabecera(self):
        st, _ = self.pedir("GET", "/api/admin/estado")
        self.assertEqual(st, 200)
        # Los POST del panel exigen X-Panel y Origin de la misma página
        st, _ = self.pedir("POST", "/api/admin/mensaje", {"texto": "x"})
        self.assertIn(st, (400, 403))

    def test_ruta_inexistente(self):
        st, _ = self.pedir("GET", "/api/no_existe", json_=False)
        self.assertEqual(st, 404)


if __name__ == "__main__":
    unittest.main()
