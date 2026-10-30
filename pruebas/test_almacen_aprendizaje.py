"""Migración e índices incrementales con texto exclusivamente ficticio."""
import csv
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import almacen_aprendizaje as AL
import aprender as A


class AlmacenTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.raiz = Path(self.tmp.name)
        self.hist = self.raiz/'historial.csv'
        self.ej = self.raiz/'ejemplos'; self.ej.mkdir()
        self.corr = self.raiz/'correcciones.md'
        for nombre, valor in [('HIST',self.hist),('EJ',self.ej),('ARCH_CORR',self.corr),('REG',self.ej/'procesados.json')]:
            parche = patch.object(A,nombre,valor); parche.start(); self.addCleanup(parche.stop)

    def registrar(self, clave, ia='Texto errado.', final='Texto corregido.'):
        return A.registrar_ejemplo(clave,'Dictado ficticio',ia,final,clave,recalcular=False,fecha='2026-10-29 12:00')

    def test_migracion_csv_una_vez_y_exportacion(self):
        original='fecha;informe;palabras;porcentaje_corregido\n2026-10-28 10:00;anterior;4;12.5\n'
        self.hist.write_text(original,encoding='utf-8-sig')
        self.registrar('nuevo')
        self.assertEqual(self.hist.read_text(encoding='utf-8-sig'),original)
        self.assertEqual(len(AL.leer_historial(self.hist)),2)
        self.registrar('nuevo',final='Cambio posterior.')
        self.assertEqual(len(AL.leer_historial(self.hist)),2)
        destino=self.raiz/'exportado.csv';AL.exportar_historial(self.hist,destino)
        filas=list(csv.DictReader(io.StringIO(destino.read_text(encoding='utf-8-sig')),delimiter=';'))
        self.assertEqual(len(filas),2)

    def test_incremental_sin_recorrer_corpus_ni_repetir_diff(self):
        self.registrar('uno');self.registrar('dos')
        frec=A.analizar_correcciones()
        self.assertEqual(frec,[(2,('replace','errado','corregido'))])
        with patch.object(Path,'glob',side_effect=AssertionError('No recorrer corpus')), patch.object(A,'cambios_de_textos',side_effect=AssertionError('No repetir diff')):
            self.registrar('dos')
            self.assertEqual(A.analizar_correcciones(),frec)
        self.registrar('dos',final='Texto errado.')
        self.assertEqual(A.analizar_correcciones(),[])
        self.registrar('dos')
        self.assertEqual(A.analizar_correcciones(),frec)

    def test_rollback_reemplazo_de_aportes(self):
        self.registrar('uno');self.registrar('dos'); esperado=A.analizar_correcciones()
        with self.assertRaises(RuntimeError):
            with AL.abrir(self.hist) as c:
                AL.actualizar_ejemplo(c,'dos','nueva',lambda:[('replace','A','B')])
                raise RuntimeError('Fallo ficticio antes de commit')
        self.assertEqual(A.analizar_correcciones(),esperado)

    def test_reconciliacion_explicita_edita_y_elimina(self):
        self.registrar('uno');self.registrar('dos');self.assertTrue(A.analizar_correcciones())
        (self.ej/'dos.informe.txt').write_text('Texto errado.',encoding='utf-8')
        self.assertEqual(A.analizar_correcciones(reconstruir=True),[])
        (self.ej/'uno.informe.txt').unlink()
        A.analizar_correcciones(reconstruir=True)
        with AL.abrir(self.hist) as c:
            self.assertIsNone(c.execute("SELECT clave FROM ejemplos WHERE clave='uno'").fetchone())

    def test_reglas_numeros_puntuacion_y_repeticion(self):
        self.assertEqual(A.cambios_de_textos('Medida 12 mm','Medida 15 mm'),set())
        self.assertEqual(A.cambios_de_textos('Texto final.','texto final,'),set())
        self.assertEqual(len(A.cambios_de_textos('errado. Separador errado.','corregido. Separador corregido.')),1)

    def test_procesados_importados_e_indexados(self):
        import json
        doc=self.raiz/'ficticio.docx';doc.write_bytes(b'ficticio')
        A.REG.write_text(json.dumps({str(doc):{'mtime':doc.stat().st_mtime,'ejemplo':'uno'}}),encoding='utf-8')
        self.assertEqual(A.procesado(doc)['ejemplo'],'uno')
        A.anotar_procesado(doc,'dos')
        self.assertEqual(A.procesado(doc)['ejemplo'],'dos')
        self.assertEqual(json.loads(A.REG.read_text())[str(doc)]['ejemplo'],'uno')

    def test_top40_y_plan_indexado(self):
        with AL.abrir(self.hist) as c:
            for i in range(100):
                AL.actualizar_ejemplo(c,str(i),str(i),lambda i=i:[('replace',str(i),'nuevo')])
            plan=c.execute('EXPLAIN QUERY PLAN SELECT op,de,a,n FROM frecuencias WHERE n>=? ORDER BY n DESC,op DESC,de DESC,a DESC LIMIT 40',(1,)).fetchall()
            self.assertIn('frecuentes',str(plan))

    def test_estadisticas_lee_historial_actual_y_detecta_actualizacion(self):
        import estadisticas as E
        self.registrar('uno')
        with patch.object(E,'HIST',self.hist), patch.object(E,'EJ',self.ej), patch.object(E.L,'CARPETA',self.raiz), patch.object(E,'_CACHE',{'firma':None,'t':0,'informes':[],'generados':[]}):
            actual={'medico':lambda n:None,'estudios':lambda n:None}
            salida=E._informes(actual)
            self.assertEqual(len(salida),1)
            self.registrar('dos')
            self.assertEqual(len(E._informes(actual)),2)

    def test_mantenimiento_exporta_y_respalda_sin_sobrescribir(self):
        import mantenimiento_aprendizaje as M
        self.registrar('uno')
        exportado=self.raiz/'salida.csv';copia=self.raiz/'copia.sqlite3'
        with patch.object(sys,'argv',['mantenimiento_aprendizaje.py','--exportar',str(exportado)]):
            M.main()
        self.assertIn('uno',exportado.read_text(encoding='utf-8-sig'))
        with patch.object(sys,'argv',['mantenimiento_aprendizaje.py','--respaldar',str(copia)]):
            M.main()
        import sqlite3
        c=sqlite3.connect(copia)
        try:
            self.assertEqual(c.execute('SELECT count(*) FROM historial').fetchone()[0],1)
        finally:
            c.close()

    def test_version_desconocida_no_se_reinicializa(self):
        with AL.abrir(self.hist) as c:
            c.execute('PRAGMA user_version=99')
        with self.assertRaises(ValueError):
            self.registrar('no confirmado')
