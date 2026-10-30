"""Guardas y agregación del ensayo CPU/GPU; no ejecuta modelos ni usa la red."""
import copy
import math
import unittest

import comparar_cpu_gpu as C


class GuardiaTest(unittest.TestCase):
    def test_rechaza_actividad_y_modelos_de_uso(self):
        libre = dict(cola=0, abiertos=0, pausada=False, en_pausa=False, trabajando=False, reinicio=False)
        C.validar_libre(libre, [])
        for campo in libre:
            with self.subTest(campo=campo):
                with self.assertRaises(RuntimeError):
                    C.validar_libre(dict(libre, **{campo: True}), [])
        with self.assertRaises(RuntimeError): C.validar_libre(libre, [{'name': 'ocupado'}])


class ResumenTest(unittest.TestCase):
    def setUp(self):
        self.pruebas = [{'ensayo': n, 'modo': modo, 'total_s': 10, 'primero_s': 1,
            'espera_media_s': 2.5, 'informes_min': 24, 'solapamiento_s': int(modo == 'paralelo'),
            'audios': [{'audio': i, 'listo_s': i, 'asr_inicio_s': i-1, 'asr_fin_s': i-.5,
                'metricas': {'eval_count': 10, 'eval_duration_s': .5}, 'omisiones': 0, 'huecos': 0}
                for i in range(1, 5)]} for n, modo in enumerate(C.ORDEN, 1)]

    def test_agrega_solo_campanas_completas_con_solapamiento(self):
        r = C.resumen(self.pruebas)
        self.assertEqual(r['paralelo']['tokens_s'], 20)
        self.assertEqual(r['actual']['total_s'], 10)
        for cambiar in (lambda p: p.pop(), lambda p: p[0].update(modo='paralelo'),
                        lambda p: p[1].update(solapamiento_s=0),
                        lambda p: p[0].update(total_s=math.nan),
                        lambda p: p[0]['audios'][0].update(audio=4)):
            p = copy.deepcopy(self.pruebas)
            cambiar(p)
            with self.assertRaises(ValueError): C.resumen(p)


if __name__ == '__main__': unittest.main()
