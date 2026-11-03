"""Planificación y trabajador con fixtures ficticios; nunca carga GPU ni llama a Ollama."""
import json
from pathlib import Path
import queue
import tempfile
import unittest
from unittest.mock import patch
from contextlib import ExitStack
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from transcripcion.procesamiento import lotes as B
from transcripcion.procesamiento import cache_transcripcion as C
RESPALDO = Path(__file__).resolve().parents[1]/"respaldo"
RESPALDO.mkdir(exist_ok=True)


class LotesTest(unittest.TestCase):
    def test_fifo_limites_y_primer_audio_largo(self):
        q = queue.Queue()
        for n in ['b','c','d']: q.put(n)
        self.assertEqual(B.formar(q,'a',{},lambda n:60),['a','b'])
        self.assertEqual(list(q.queue),['c','d'])
        self.assertEqual(B.formar(q,'largo',{},lambda n:600),['largo'])
        self.assertEqual(list(q.queue),['c','d'])

    def test_duracion_desconocida_y_config_invalida(self):
        q=queue.Queue();q.put('b')
        self.assertEqual(B.formar(q,'a',{},lambda n:None),['a'])
        self.assertEqual(B.limites({'lote_max_audios':None,'lote_max_segundos':'nan'}),(2,180))
        self.assertEqual(B.limites({'lote_max_audios':0,'lote_max_segundos':-1}),(1,1))

    def test_no_espera_a_productores(self):
        self.assertEqual(B.formar(queue.Queue(),'solo',{},lambda n:30),['solo'])

    def test_encolado_repetido_no_duplica_trabajo(self):
        import servidor as S
        q=queue.Queue()
        with patch.object(S,'COLA',q), patch.object(S,'ESTADO',{}), patch.object(S,'ENCOLADO',{}), patch.object(S,'BORRADOS',set()):
            self.assertTrue(S.encolar('ficticio'))
            self.assertFalse(S.encolar('ficticio'))
            self.assertEqual(q.qsize(),1)
            S.ESTADO['ficticio']['estado']='listo'
            self.assertTrue(S.encolar('ficticio'))
            self.assertEqual(q.qsize(),2)

    def test_caso_borrado_no_retiene_espera_de_ia(self):
        import servidor as S
        with patch.object(S,'BORRADOS',{'ficticio'}), patch.object(S,'estado_ia') as consultar:
            S.esperar_ia('ficticio',['ficticio'])
            consultar.assert_not_called()

    def test_cache_invalida_contenido_parametros_y_codigo(self):
        with tempfile.TemporaryDirectory(dir=RESPALDO) as tmp:
            p=Path(tmp);audio=p/'ficticio.wav';codigo=p/'fuente.py';cache=p/'cache.json'
            audio.write_bytes(b'audio ficticio');codigo.write_text('version uno')
            firma=C.firma(audio,{'modelo':'uno'},[codigo])
            t={'texto':'Dictado ficticio','palabras':[],'huecos':[]}
            C.guardar(cache,firma,t);self.assertEqual(C.leer(cache,firma),t)
            audio.write_bytes(b'otro contenido')
            self.assertIsNone(C.leer(cache,C.firma(audio,{'modelo':'uno'},[codigo])))
            self.assertIsNone(C.leer(cache,dict(firma,parametros={'modelo':'dos'})))
            codigo.write_text('version dos');audio.write_bytes(b'audio ficticio')
            self.assertIsNone(C.leer(cache,C.firma(audio,{'modelo':'uno'},[codigo])))
            cache.write_text('roto');self.assertIsNone(C.leer(cache,firma))

    def test_metricas_no_cambian_payload_ni_contrato(self):
        import nucleo as N
        with patch.object(N,'_post',return_value={'message':{'content':'Informe ficticio.'},'load_duration':2_000_000_000,'prompt_eval_count':10,'eval_count':20}) as llamada:
            metricas={};r=N.llamar_ia('modelo-ficticio',[],metricas=metricas)
            self.assertEqual(len(r),4);self.assertEqual(r[2:],(10,20))
            self.assertEqual(metricas['load_duration_s'],2)
            self.assertEqual(llamada.call_args.args[0]['options'],{'temperature':.1,'num_ctx':12288})

    def test_banco_reutiliza_e_invalida_ejemplo_editado(self):
        import nucleo as N
        with tempfile.TemporaryDirectory(dir=RESPALDO) as tmp:
            p=Path(tmp);ej=p/'ej';ej.mkdir()
            (ej/'ficticio.dictado.txt').write_text('Dictado ficticio',encoding='utf-8')
            (ej/'ficticio.informe.txt').write_text('Informe ficticio',encoding='utf-8')
            with patch.object(N,'_leer_banco',wraps=N._leer_banco) as leer:
                uno=N.cargar_banco(p/'fase1',p/'audios',ej)
                uno[0]['informe']='Cambio del consumidor'
                self.assertEqual(N.cargar_banco(p/'fase1',p/'audios',ej)[0]['informe'],'Informe ficticio')
                self.assertEqual(leer.call_count,1)
                (ej/'ficticio.informe.txt').write_text('Informe ficticio actualizado',encoding='utf-8')
                self.assertEqual(N.cargar_banco(p/'fase1',p/'audios',ej)[0]['informe'],'Informe ficticio actualizado')
                self.assertEqual(leer.call_count,2)

    def test_perfiles_incluyen_revision_de_plantillas(self):
        import nucleo as N
        primero=N._perfil_ejemplo('abdominal',('abdominal',))[0]
        segundo=N._perfil_ejemplo('abdominal',('renal',))[0]
        self.assertIn('pl:abdominal',primero)
        self.assertNotIn('pl:abdominal',segundo)


class FinTrabajador(BaseException):
    pass


class ColaFinita(queue.Queue):
    def get(self, block=True, timeout=None):
        if block and self.empty():
            raise FinTrabajador()
        return super().get(block,timeout)


class TrabajadorTest(unittest.TestCase):
    def ejecutar(self, fallo=None, cache=False):
        import servidor as S
        with tempfile.TemporaryDirectory(dir=RESPALDO) as tmp, ExitStack() as pila:
            raiz=Path(tmp);datos=raiz/'datos';datos.mkdir()
            cola=ColaFinita()
            trans={'texto':'Dictado ficticio','palabras':[],'huecos':[]}
            for n in ['uno','dos','tres']:
                cola.put(n);(raiz/f'{n}.wav').write_bytes(b'WAV ficticio')
                for sub,obj in [('fase1/json',{'con_vocab':trans}),('fase2/gemma4_12b',{'salida':'Informe ficticio.'})]:
                    d=raiz/'resultados'/sub;d.mkdir(parents=True,exist_ok=True)
                    (d/f'{n}.json').write_text(json.dumps(obj),encoding='utf-8')
            if fallo:
                etapa,caso=fallo
                (raiz/'resultados'/etapa/f'{caso}.json').write_text('roto',encoding='utf-8')
            from transcripcion import ajustes
            cfg=ajustes.para_pruebas(raiz,lote_max_audios=2,lote_max_segundos=180).cfg
            for nombre,valor in [('AQUI',raiz),('DATOS',datos),('COLA',cola),('CFG',cfg),('SIMULAR',not cache),('ESTADO',{}),('BORRADOS',set()),('PAUSAS',{}),('PAUSADO_S',{}),('REINICIO',{}),('TRABAJO',{}),('ENCOLADO',{})]:
                pila.enter_context(patch.object(S,nombre,valor))
            pila.enter_context(patch.dict('os.environ',{'SIMULAR_DEMORA':'0'}))
            eventos=[]
            original=S.empezar;estado=S.poner_estado
            def empezar(n,e,msg=''):
                eventos.append((n,e));return original(n,e,msg)
            def poner(n,e,msg=''):
                eventos.append((n,e));return estado(n,e,msg)
            pila.enter_context(patch.object(S,'empezar',side_effect=empezar))
            pila.enter_context(patch.object(S,'poner_estado',side_effect=poner))
            for nombre,valor in [('ruta_audio',lambda n:raiz/f'{n}.wav'),('duracion_de',lambda n:30),('duracion_wav',lambda **kw:30),('esperar_ia',lambda *a:None),('calcular_voz',lambda *a:None),('anotar_voz',lambda *a,**kw:None),('resumen_voz',lambda n:None),('datos_csv',lambda n:{}),('anotar_tiempo',lambda *a:None),('guardar_marcas',lambda *a:([],[])),('resumen_avisos',lambda *a:{'faltan':[],'rojo':0,'amarillo':0,'turq':0,'gris':0,'huecos':[]})]:
                pila.enter_context(patch.object(S,nombre,side_effect=valor))
            pila.enter_context(patch.object(S.PAC,'calcular'))
            pila.enter_context(patch.object(S.L,'actividad'))
            pila.enter_context(patch.object(S.L,'error'))
            pila.enter_context(patch.object(S.N,'cargar_banco',return_value=[]))
            pila.enter_context(patch.object(S.N,'estudios_sin_plantilla',return_value=[]))
            liberar=pila.enter_context(patch.object(S.N,'liberar_ia'))
            if cache:
                if cache is True:
                    pila.enter_context(patch.object(S.CACHE_ASR,'firma',return_value={'ficticia':True}))
                    pila.enter_context(patch.object(S.CACHE_ASR,'leer',return_value=trans))
                else:
                    import shutil
                    import fase1_transcribir as F
                    import huecos as H
                    for f in ['fase1_transcribir.py','huecos.py']:
                        shutil.copyfile(Path(S.__file__).parent/f,raiz/f)
                    cargar=pila.enter_context(patch.object(F,'cargar_modelo',return_value=object()))
                    asr=pila.enter_context(patch.object(F,'transcribir',return_value=trans))
                    pila.enter_context(patch.object(F,'cargar_audio',return_value=[]))
                    pila.enter_context(patch.object(H,'reparar',return_value=([],[])))
                    pila.enter_context(patch.object(H,'texto_de',return_value='Dictado ficticio'))
                pila.enter_context(patch.object(S.N,'elegir_ejemplos',return_value=[]))
                pila.enter_context(patch.object(S.N,'armar_mensajes',return_value=[]))
                pila.enter_context(patch.object(S.N,'llamar_ia',return_value=('Informe ficticio.',0,10,20)))
            with self.assertRaises(FinTrabajador):
                S.trabajador()
            if cache == 'fria':
                self.assertEqual(asr.call_count,3)
                cargas=cargar.call_count;descargas=liberar.call_count
                for n in ['uno','dos','tres']:cola.put(n)
                with self.assertRaises(FinTrabajador):
                    S.trabajador()
                self.assertEqual(asr.call_count,3)
                self.assertEqual(cargar.call_count,cargas)
                self.assertEqual(liberar.call_count,descargas)
            salida=dict(S.ESTADO)
            metricas=json.loads((datos/'tres.rendimiento.json').read_text(encoding='utf-8'))
            if cache is True:liberar.assert_not_called()
            return eventos,salida,metricas

    def test_primer_informe_antes_de_transcribir_tercero(self):
        eventos,estados,_=self.ejecutar()
        self.assertLess(eventos.index(('uno','listo')),eventos.index(('tres','transcribiendo')))
        self.assertTrue(all(e['estado']=='listo' for e in estados.values()))

    def test_error_transcripcion_no_contagia_lote(self):
        _,estados,_=self.ejecutar(('fase1/json','uno'))
        self.assertEqual(estados['uno']['estado'],'error')
        self.assertEqual(estados['dos']['estado'],'listo')
        self.assertEqual(estados['tres']['estado'],'listo')

    def test_error_generacion_no_contagia_lote(self):
        _,estados,_=self.ejecutar(('fase2/gemma4_12b','uno'))
        self.assertEqual(estados['uno']['estado'],'error')
        self.assertEqual(estados['dos']['estado'],'listo')

    def test_cache_evitar_descarga_modelos(self):
        _,estados,metricas=self.ejecutar(cache=True)
        self.assertTrue(all(e['estado']=='listo' for e in estados.values()))
        self.assertTrue(metricas['cache_asr'])

    def test_transcripcion_fria_y_reintento_reusan_cache_real(self):
        _,estados,metricas=self.ejecutar(cache='fria')
        self.assertTrue(all(e['estado']=='listo' for e in estados.values()))
        self.assertTrue(metricas['cache_asr'])
