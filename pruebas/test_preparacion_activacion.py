"""Respaldo, integridad y rollback con fixtures ficticios; no consulta datos reales ni reinicia."""
from contextlib import closing
import csv
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import preparar_activacion as P
import rollback_datos as R
from verificar_paquete import verificar
import borradores as B
import cola_procesamiento as C
import almacen_aprendizaje as A


class PreparacionTest(unittest.TestCase):
    def setUp(self):
        respaldo=Path(__file__).resolve().parents[1]/'respaldo';respaldo.mkdir(exist_ok=True)
        self.tmp=tempfile.TemporaryDirectory(dir=respaldo);self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name)

    def test_copia_y_sqlite_consistente_sin_modificar_origen(self):
        origen=self.base/'origen';origen.mkdir();(origen/'audio.txt').write_text('Ficticio')
        with closing(sqlite3.connect(origen/'indice.sqlite3')) as db:
            db.execute('CREATE TABLE prueba (n)');db.execute('INSERT INTO prueba VALUES (1)');db.commit()
        antes=P.sha(origen/'indice.sqlite3');inventario=P.respaldar_arbol(origen,self.base/'copia')
        self.assertEqual(inventario['indice.sqlite3']['metodo'],'sqlite_backup')
        self.assertEqual(P.sha(origen/'indice.sqlite3'),antes)
        with closing(sqlite3.connect(self.base/'copia'/'indice.sqlite3')) as db:self.assertEqual(db.execute('SELECT n FROM prueba').fetchone()[0],1)

    def test_manifiesto_rechaza_cambio_omision_y_secretos(self):
        paquete=self.base/'paquete';f=paquete/'entrega'/'fuente.py';f.parent.mkdir(parents=True);f.write_text('ficticio')
        P.guardar(paquete/'manifiesto_entrega.json',{'fuente.py':P.sha(f)})
        self.assertFalse(verificar(paquete)['autoriza_activar'])
        f.write_text('alterado')
        with self.assertRaises(ValueError):verificar(paquete)
        f.unlink()
        with self.assertRaises(ValueError):verificar(paquete)
        secreto=f.with_name('conexion.json');secreto.write_text('{}')
        P.guardar(paquete/'manifiesto_entrega.json',{'conexion.json':P.sha(secreto)})
        with self.assertRaises(ValueError):verificar(paquete)

    def fixture(self):
        origen=self.base/'origen';d=origen/'informes'/'revision'/'datos';d.mkdir(parents=True)
        B.guardar(d,'ficticio',{'html':'<div>Corrección ficticia nueva</div>','omisiones_ok':['dato ficticio']})
        (origen/'resultados').mkdir();(origen/'ejemplos').mkdir()
        A.anotar_historial(origen/'resultados'/'historial.csv','ficticio','2026-10-29 12:00',12,'2.0')
        with A.abrir(origen/'resultados'/'historial.csv') as db:
            db.execute('INSERT INTO procesados VALUES (?,?,?)',('Word ficticio.docx',10,'ejemplo-ficticio'))
        return origen,d

    def test_rollback_en_copia_conserva_edicion_reciente_y_exporta_historial(self):
        origen,d=self.fixture();firma=P.sha(d/'ficticio.borrador.json')
        salida=self.base/'retrocompatible';r=R.preparar(origen,salida)
        self.assertEqual(r['borradores_convertidos'],1)
        antiguo=salida/'informes'/'revision'/'datos'
        self.assertIn('Corrección ficticia nueva',(antiguo/'ficticio.borrador.html').read_text(encoding='utf-8'))
        self.assertEqual(json.loads((antiguo/'ficticio.omisiones_ok.json').read_text()),['dato ficticio'])
        self.assertFalse((antiguo/'ficticio.borrador.json').exists())
        self.assertEqual(P.sha(d/'ficticio.borrador.json'),firma)
        with (salida/'resultados'/'historial.csv').open(encoding='utf-8-sig') as f:self.assertEqual(len(list(csv.DictReader(f,delimiter=';'))),1)
        self.assertEqual(json.loads((salida/'ejemplos'/'_procesados.json').read_text())['Word ficticio.docx']['ejemplo'],'ejemplo-ficticio')
        with self.assertRaises(FileExistsError):R.preparar(origen,salida)

    def test_rollback_no_sigue_si_hay_aprendizaje_cola_o_json_corrupto(self):
        origen,d=self.fixture();salida=self.base/'salida'
        trabajo=d/'_aprendizaje';trabajo.mkdir();f=trabajo/'ficticio.json';f.write_text('{}')
        with self.assertRaises(ValueError):R.preparar(origen,salida)
        self.assertFalse(salida.exists());f.unlink()
        c=C.ColaProcesamiento(d.parent/'cola_procesamiento.sqlite3');c.solicitar('ficticio');c.cerrar()
        with self.assertRaises(ValueError):R.preparar(origen,salida)
        c=C.ColaProcesamiento(d.parent/'cola_procesamiento.sqlite3');c.cambiar('ficticio','listo');c.cerrar()
        (d/'ficticio.borrador.json').write_text('{}')
        with self.assertRaises(B.Corrupto):R.preparar(origen,salida)
        self.assertFalse(salida.exists())


if __name__=='__main__':unittest.main()
