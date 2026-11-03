"""Invalidación y aislamiento del índice, con archivos ficticios."""
from pathlib import Path
import tempfile
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from transcripcion.casos.indice import IndiceCasos


class IndiceTest(unittest.TestCase):
    def test_reutiliza_invalida_y_depura(self):
        indice = IndiceCasos()
        llamadas = []
        def leer():
            llamadas.append(1)
            return len(llamadas)
        self.assertEqual(indice.obtener(('caso', 'titulo'), (1,), leer), 1)
        self.assertEqual(indice.obtener(('caso', 'titulo'), (1,), leer), 1)
        self.assertEqual(indice.obtener(('caso', 'titulo'), (2,), leer), 2)
        indice.depurar(set())
        self.assertEqual(indice.obtener(('caso', 'titulo'), (2,), leer), 3)

    def test_inventario_detecta_edicion_y_borrado(self):
        with tempfile.TemporaryDirectory() as carpeta:
            f = Path(carpeta) / 'ficticio.txt'
            f.write_text('A', encoding='utf-8')
            anterior = IndiceCasos.inventario(carpeta)
            f.write_text('Cambio ficticio', encoding='utf-8')
            self.assertNotEqual(anterior, IndiceCasos.inventario(carpeta))
            f.unlink()
            self.assertEqual(IndiceCasos.inventario(carpeta), {})

    def test_listado_invalida_metadatos_y_no_cachea_permisos(self):
        import servidor as S
        import json
        from transcripcion import ajustes
        with tempfile.TemporaryDirectory() as carpeta:
            aj = ajustes.para_pruebas(Path(carpeta))
            ajustes.preparar_carpetas(aj); datos = aj.datos
            self.addCleanup(S.configurar, S.configurar(aj))      # casos y procesamiento con estas carpetas
            (datos/'ficticio.informe_ia.txt').write_text('Informe ficticio', encoding='utf-8')
            (datos/'ficticio.paciente.json').write_text(json.dumps({'p':'Persona ficticia','manual':True}), encoding='utf-8')
            (datos/'ficticio.medico.txt').write_text('Dr. Uno', encoding='utf-8')
            with patch.object(S.CASOS,'indice',IndiceCasos()), patch.object(S.R,'bloqueado_por',return_value=None) as permiso:
                self.assertEqual(S.VISTA.listar_casos()[0]['medico'],'Dr. Uno')
                permiso.return_value='Otra PC'
                self.assertEqual(S.VISTA.listar_casos()[0]['bloqueado_por'],'Otra PC')
                (datos/'ficticio.medico.txt').write_text('Dra. Modificada', encoding='utf-8')
                self.assertEqual(S.VISTA.listar_casos()[0]['medico'],'Dra. Modificada')
                (datos/'ficticio.informe_ia.txt').unlink()
                self.assertEqual(S.VISTA.listar_casos(),[])
