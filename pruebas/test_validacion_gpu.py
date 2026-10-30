"""Seguridad y métricas del benchmark, con procesos/API simulados; no utiliza GPU."""
import copy
import json
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import validar_gpu_real as G
from resumir_gpu_real import ORDEN, resumir


class GuardiaTest(unittest.TestCase):
    def test_detecta_python_con_y_sin_consola_y_falla_si_tasklist_falla(self):
        proceso = Mock(stdout='"python.exe","10"\n"pythonw.exe","20"\n"otro.exe","30"\n')
        with patch.object(G.subprocess, 'run', return_value=proceso):
            self.assertEqual(G.python_pids(), {10,20})
            proceso.check_returncode.side_effect = OSError('sin inventario')
            with self.assertRaises(OSError): G.python_pids()

    def test_servidor_activo_impide_carga(self):
        with patch.object(G, 'escucha', return_value=True), patch.object(G, 'api') as api:
            with self.assertRaisesRegex(RuntimeError, 'producción'): G.libre({1})
            api.assert_not_called()

    def test_ollama_ocupado_impide_carga(self):
        with patch.object(G, 'escucha', return_value=False), patch.object(G, 'api', return_value={'models': [{'name': 'ficticio'}]}):
            with self.assertRaisesRegex(RuntimeError, 'ocupado'): G.libre({1})

    def test_api_inaccesible_falla_sin_continuar(self):
        with patch.object(G, 'escucha', return_value=False), patch.object(G, 'api', side_effect=OSError('sin conexión')), patch.object(G, 'python_pids') as pids:
            with self.assertRaises(OSError): G.libre({1})
            pids.assert_not_called()

    def test_redirectores_propios_permitidos_y_python_ajeno_bloqueado(self):
        familia = [{'ProcessId': 2, 'ParentProcessId': 1}, {'ProcessId': 3, 'ParentProcessId': 2}]
        proceso = Mock(stdout=json.dumps(familia))
        with patch.object(G, 'escucha', return_value=False), patch.object(G, 'api', return_value={'models': []}), patch.object(G, 'python_pids', return_value={1, 2, 3}), patch.object(G.subprocess, 'run', return_value=proceso):
            permitidos = {1}; G.libre(permitidos)
            self.assertEqual(permitidos, {1, 2, 3})
            with patch.object(G, 'python_pids', return_value={1, 2, 3, 99}):
                with self.assertRaisesRegex(RuntimeError, 'otro proceso Python'): G.libre(permitidos)


class ResumenTest(unittest.TestCase):
    def setUp(self):
        self.datos = {'completo': True, 'orden': ORDEN, 'pruebas': []}
        for numero, lote in enumerate(ORDEN, 1):
            self.datos['pruebas'].append({'ensayo': numero, 'lote': lote, 'total_s': 10, 'primero_s': 1,
                'espera_media_s': 2.5, 'ultimo_s': 4, 'informes_min': 24, 'cargas_whisper_s': [2],
                'audios': [{'audio': i, 'listo_s': i, 'asr_s': .2,
                            'metricas': {'eval_count': 10, 'eval_duration_s': .5, 'load_duration_s': .1}} for i in range(1, 5)]})

    def test_mediana_y_tokens_ponderados(self):
        r = resumir(self.datos)
        self.assertEqual((r['ensayos'], r['informes']), (9, 36))
        self.assertEqual(r['lotes']['2']['tokens_s'], 20)
        self.assertEqual(r['lotes']['4']['cargas_whisper_s'], 2)

    def test_rechaza_incompletos_duplicados_y_metricas_no_finitas(self):
        for modificar in [lambda d: d.update(completo=False), lambda d: d['pruebas'].pop(),
            lambda d: d['pruebas'][0].update(ensayo=2), lambda d: d['pruebas'][0].update(total_s=float('nan')),
            lambda d: d['pruebas'][0].update(espera_media_s=99),
            lambda d: d['pruebas'][0]['audios'][0].update(audio=2)]:
            with self.subTest(modificar=modificar):
                d = copy.deepcopy(self.datos); modificar(d)
                with self.assertRaises(ValueError): resumir(d)


class ReanudacionTest(unittest.TestCase):
    def test_solo_corpus_intacto_y_protocolo_incompleto_bajo_respaldo(self):
        respaldo=Path(__file__).resolve().parents[1]/'respaldo'
        respaldo.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=respaldo) as tmp:
            base=Path(tmp); raiz=base/'gpu_real_ficticio'; (raiz/'audios').mkdir(parents=True)
            (raiz/'dictados.json').write_text(json.dumps(G.FICTICIOS),encoding='utf-8')
            firmas={}
            for i in range(1,5):
                nombre=f'audio_{i}.wav'; (raiz/'audios'/nombre).write_bytes(b'contenido ficticio')
                firmas[nombre]=hashlib.sha256(b'contenido ficticio').hexdigest()
            (raiz/'entorno.json').write_text(json.dumps({'sha_audios':firmas}),encoding='utf-8')
            resultados=raiz/'resultados.json'
            resultados.write_text(json.dumps({'completo':False,'orden':ORDEN,'pruebas':[]}),encoding='utf-8')
            G.validar_reanudacion(raiz,base)
            with self.assertRaises(RuntimeError): G.validar_reanudacion(raiz,base/'otro')
            resultados.write_text(json.dumps({'completo':True,'orden':ORDEN,'pruebas':[]}),encoding='utf-8')
            with self.assertRaisesRegex(RuntimeError,'terminó'): G.validar_reanudacion(raiz,base)
            resultados.write_text(json.dumps({'completo':False,'orden':ORDEN,'pruebas':[]}),encoding='utf-8')
            (raiz/'audios'/'audio_1.wav').write_bytes(b'modificado')
            with self.assertRaisesRegex(RuntimeError,'Cambió'): G.validar_reanudacion(raiz,base)


if __name__ == '__main__': unittest.main()
