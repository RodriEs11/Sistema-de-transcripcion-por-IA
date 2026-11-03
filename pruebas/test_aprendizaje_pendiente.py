"""Word confirmado y aprendizaje recuperable, solo con documentos ficticios."""
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from transcripcion.aprendizaje.pendiente import ColaAprendizaje


class ColaTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.carpeta = Path(self.tmp.name)

    def test_recupera_al_crear_otro_consumidor(self):
        aplicadas = []
        c = ColaAprendizaje(self.carpeta, aplicadas.append, lambda: None)
        c.agregar({"nombre": "ficticio", "texto": "último"})
        c.agregar({"nombre": "ficticio", "texto": "más reciente"})
        ColaAprendizaje(self.carpeta, aplicadas.append, lambda: None).procesar()
        self.assertEqual([d["texto"] for d in aplicadas], ["más reciente"])
        self.assertEqual(list(self.carpeta.iterdir()), [])

    def test_fallo_conserva_tarea_y_reintenta_analisis(self):
        with patch('transcripcion.aprendizaje.pendiente.L.error'):
            c = ColaAprendizaje(self.carpeta, lambda d: (_ for _ in ()).throw(OSError("ficticio")), lambda: None)
            c.agregar({"nombre": "ficticio"})
            c.procesar()
            self.assertTrue((self.carpeta / 'ficticio.json').exists())
            c.aplicar = lambda d: None
            c.analizar = lambda: (_ for _ in ()).throw(OSError("ficticio"))
            c.procesar()
            self.assertFalse((self.carpeta / 'ficticio.json').exists())
            self.assertTrue((self.carpeta / '_recalcular').exists())
            c.analizar = lambda: None
            c.procesar()
            self.assertEqual(list(self.carpeta.iterdir()), [])

    def test_guardar_mientras_aprende_no_pierde_version_nueva(self):
        entro = threading.Event(); salir = threading.Event()
        def aplicar(d):
            entro.set()
            self.assertTrue(salir.wait(5))
        c = ColaAprendizaje(self.carpeta, aplicar, lambda: None)
        c.agregar({"nombre": "ficticio", "texto": "viejo"})
        h = threading.Thread(target=c.procesar)
        h.start()
        try:
            self.assertTrue(entro.wait(5))
            c.agregar({"nombre": "ficticio", "texto": "nuevo"})
        finally:
            salir.set(); h.join(5)
        self.assertEqual(json.loads((self.carpeta/'ficticio.json').read_text())["texto"], "nuevo")


class WordTest(unittest.TestCase):
    def test_finalizar_no_invoca_aprendizaje_y_word_es_valido(self):
        import servidor as S
        import aprender as A
        from transcripcion import ajustes
        from docx import Document
        with tempfile.TemporaryDirectory() as tmp:
            carpeta = Path(tmp)
            aj = ajustes.para_pruebas(carpeta, carpeta_informes=carpeta)   # Word en carpeta, datos en carpeta/revision/datos
            datos = aj.datos; datos.mkdir(parents=True)
            self.addCleanup(S.configurar, S.configurar(aj))
            conoc = patch.object(S.CON, 'CONOC', carpeta/'conocimiento'); conoc.start(); self.addCleanup(conoc.stop)
            S.CON.preparar_conocimiento()     # conocimiento de ejemplo, nunca el de la instalación
            (datos/'ficticio.informe_ia.txt').write_text('Informe ficticio.', encoding='utf-8')
            (datos/'ficticio.dictado.txt').write_text('Dictado ficticio.', encoding='utf-8')
            cola = ColaAprendizaje(datos/'_aprendizaje', lambda d: None, lambda: None)
            with patch.object(S,'APRENDIZAJE',cola), patch.object(S,'resumen_voz',return_value=None), patch.object(S.CASOS,'datos_csv',return_value={}), patch.object(S.L,'actividad'), patch.object(A,'registrar_ejemplo',side_effect=AssertionError('No debe ejecutarse en el guardado')):
                r = S.finalizar('ficticio', 'Informe final ficticio.')
                self.assertEqual(r['aprendizaje'],'pendiente')
                self.assertIn('Informe final ficticio.', [p.text for p in Document(r['docx']).paragraphs])
                self.assertTrue((datos/'_aprendizaje/ficticio.json').exists())
                # Una publicación Word fallida conserva el anterior y no confirma una tarea nueva.
                contenido = Path(r['docx']).read_bytes()
                with patch('transcripcion.base.persistencia.os.replace',side_effect=PermissionError('Word abierto ficticio')):
                    with self.assertRaises(PermissionError):
                        S.finalizar('ficticio', 'No confirmado')
                self.assertEqual(Path(r['docx']).read_bytes(), contenido)
                # El trabajador puede quedar ocupado sin retener el lock de finalización.
                entro = threading.Event(); salir = threading.Event()
                def lento(tarea):
                    entro.set(); salir.wait(5)
                cola.aplicar = lento
                hilo = threading.Thread(target=cola.procesar); hilo.start()
                try:
                    self.assertTrue(entro.wait(5))
                    nuevo = S.finalizar('ficticio', 'Nueva versión ficticia.')
                    self.assertFalse(salir.is_set())
                    self.assertEqual(nuevo['aprendizaje'], 'pendiente')
                finally:
                    salir.set(); hilo.join(5)
                self.assertEqual(json.loads((datos/'_aprendizaje/ficticio.json').read_text(encoding='utf-8'))["final"], 'Nueva versión ficticia.')

    def test_registrar_reintento_no_duplica_historial_ni_reanaliza(self):
        import aprender as A
        with tempfile.TemporaryDirectory() as tmp:
            carpeta = Path(tmp)
            with patch.object(A,'EJ',carpeta/'ejemplos'), patch.object(A,'HIST',carpeta/'historial.csv'), patch.object(A,'analizar_correcciones',side_effect=AssertionError('Análisis pesado en guardado')):
                for _ in range(2):
                    A.registrar_ejemplo('ficticio','Dictado','Texto','Texto final','clave',recalcular=False,fecha='2026-10-29 12:00')
                self.assertEqual(len(A.AL.leer_historial(carpeta/'historial.csv')),1)
