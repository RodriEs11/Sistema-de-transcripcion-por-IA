"""Recepción duradera y reintentos de audios ficticios, sin GPU ni configuración real."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


class RecepcionTest(unittest.TestCase):
    def setUp(self):
        import servidor as S
        from transcripcion.http import audios as AU
        self.S, self.AU = S, AU
        respaldo=Path(__file__).resolve().parents[1]/'respaldo'; respaldo.mkdir(exist_ok=True)
        tmp=tempfile.TemporaryDirectory(dir=respaldo); self.addCleanup(tmp.cleanup)
        self.base=Path(tmp.name); self.nuevos=self.base/'nuevos'; self.datos=self.base/'revision'/'datos'
        self.nuevos.mkdir(); self.datos.mkdir(parents=True)
        from transcripcion import ajustes
        aj=ajustes.para_pruebas(self.base,carpeta_informes=self.base,carpeta_audios_nuevos=self.nuevos)
        self.addCleanup(S.configurar,S.configurar(aj))      # casos y procesamiento nuevos con estas carpetas
        self.audio=b'RIFF'+(100).to_bytes(4,'little')+b'WAVE'+b'\0'*96
        self.huella=hashlib.sha256(self.audio).hexdigest()
        self.parches=ExitStack(); self.addCleanup(self.parches.close)
        self.encolar=self.parches.enter_context(patch.object(S.PROC,'encolar'))
        self.parches.enter_context(patch.object(AU,'anunciar_audio'))
        self.parches.enter_context(patch.object(S.CASOS,'ruta_audio',side_effect=lambda n: next(self.nuevos.glob(n+'.wav'),None)))
        self.h=object.__new__(S.H); self.h.pc='PC-ficticia'

    def recibir(self):return self.AU.guardar_audio_nuevo(self.h,'ficticio.wav',self.audio,self.huella)

    def test_publicacion_solo_despues_de_metadatos(self):
        escribir=self.AU.escribir_atomico
        def observar(ruta,contenido):
            ruta=Path(ruta)
            if ruta.suffix=='.wav':
                self.assertTrue((self.datos/(ruta.stem+'.origen.txt')).exists())
                self.assertFalse(ruta.exists())
            escribir(ruta,contenido)
        with patch.object(self.AU,'escribir_atomico',side_effect=observar): r,error=self.recibir()
        self.assertIsNone(error); self.assertTrue(r['ok'])
        self.assertEqual((self.nuevos/(r['nombre']+'.wav')).read_bytes(),self.audio)
        self.assertEqual(self.S.R.buscar_huella(self.datos,self.huella),r['nombre'])

    def test_fallo_publicacion_no_confirma_ni_encola(self):
        escribir=self.AU.escribir_atomico
        def fallar(ruta,contenido):
            if Path(ruta).suffix=='.wav': raise OSError('disco lleno ficticio')
            escribir(ruta,contenido)
        with patch.object(self.AU,'escribir_atomico',side_effect=fallar):
            with self.assertRaises(OSError):self.recibir()
        self.encolar.assert_not_called(); self.assertEqual(list(self.nuevos.iterdir()),[])
        self.assertIsNone(self.S.R.buscar_huella(self.datos,self.huella))

    def test_reintentos_concurrentes_un_solo_audio_y_caso(self):
        def encolar(n): self.S.PROC.estado[n]={'estado':'en cola'}
        self.encolar.side_effect=encolar
        with ThreadPoolExecutor(max_workers=4) as pool:r=list(pool.map(lambda _:self.recibir(),range(8)))
        self.assertEqual(len({x[0]['nombre'] for x in r}),1)
        self.assertEqual(sum(not x[0]['duplicado'] for x in r),1)
        self.assertEqual(len(list(self.nuevos.glob('*.wav'))),1)
        self.encolar.assert_called_once()

    def test_recupera_reintento_tras_recepcion_sin_encolado(self):
        self.encolar.side_effect=OSError('caída ficticia al encolar')
        with self.assertRaises(OSError):self.recibir()
        self.encolar.side_effect=None
        r,error=self.recibir()
        self.assertIsNone(error); self.assertTrue(r['duplicado'])
        self.assertEqual(len(list(self.nuevos.glob('*.wav'))),1)
        self.encolar.assert_called_with(r['nombre'])

    def test_fallo_replace_huellas_conserva_indice_anterior(self):
        from transcripcion.base import persistencia as P
        self.S.R.guardar_huella(self.datos,'anterior','caso-anterior')
        with patch.object(P.os,'replace',side_effect=OSError('fallo ficticio')):
            with self.assertRaises(OSError):self.S.R.guardar_huella(self.datos,'nuevo','caso-nuevo')
        self.assertEqual(json.loads((self.datos/'_huellas.json').read_text()),{'anterior':'caso-anterior'})


if __name__=='__main__':unittest.main()
