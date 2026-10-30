"""Cola GPU con archivos ficticios, SQLite real y caídas de procesos propios; sin modelos."""
from contextlib import ExitStack, closing
from concurrent.futures import ThreadPoolExecutor
import http.client
import json
from pathlib import Path
import queue
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import cola_procesamiento as C

RESPALDO = Path(__file__).resolve().parents[1]/'respaldo'
RESPALDO.mkdir(exist_ok=True)


class ColaTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=RESPALDO); self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name); self.ruta = self.base/'cola.sqlite3'
        self.cola = C.ColaProcesamiento(self.ruta); self.addCleanup(self.cola.cerrar)

    def test_fifo_idempotencia_y_reintento_explicito(self):
        self.assertTrue(self.cola.solicitar('uno')); self.cola.solicitar('dos')
        token = self.cola.obtener('uno')['token']
        self.assertFalse(self.cola.solicitar('uno'))
        self.assertEqual([r['nombre'] for r in self.cola.filas()], ['uno','dos'])
        self.assertEqual(self.cola.obtener('uno')['token'], token)
        self.cola.cambiar('uno','listo'); self.assertEqual(len(self.cola.filas()),1)
        self.cola.solicitar('uno')
        self.assertNotEqual(self.cola.obtener('uno')['token'],token)
        self.assertEqual([r['nombre'] for r in self.cola.filas()], ['dos','uno'])

    def test_concurrencia_no_duplica_tarea(self):
        with ThreadPoolExecutor(max_workers=8) as p: altas=list(p.map(lambda _:self.cola.solicitar('ficticio'),range(32)))
        self.assertEqual(sum(altas),1); self.assertEqual(len(self.cola.filas()),1)

    def test_commit_fallido_no_confirma_y_revierte(self):
        conexion=self.cola.db; falso=Mock(wraps=conexion)
        falso.commit.side_effect=sqlite3.OperationalError('disco lleno ficticio')
        with patch.object(self.cola,'db',falso):
            with self.assertRaises(C.ErrorCola):self.cola.solicitar('no-confirmado')
        self.assertIsNone(self.cola.obtener('no-confirmado'))

    def test_otro_propietario_y_version_desconocida_no_se_reinician(self):
        with self.assertRaises(C.ErrorCola):C.ColaProcesamiento(self.ruta)
        self.cola.cerrar()
        with closing(sqlite3.connect(self.ruta)) as db:db.execute('PRAGMA user_version=99');db.commit()
        with self.assertRaises(C.ErrorCola):C.ColaProcesamiento(self.ruta)
        with closing(sqlite3.connect(self.ruta)) as db:self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],99)

    def test_base_corrupta_y_nombres_invalidos_se_conservan(self):
        for n in ('', '../ficticio','carpeta/ficticio',None):
            with self.assertRaises(ValueError):self.cola.solicitar(n)
        self.cola.cerrar(); self.ruta.write_bytes(b'base ficticia corrupta')
        with self.assertRaises(C.ErrorCola):C.ColaProcesamiento(self.ruta)
        self.assertEqual(self.ruta.read_bytes(),b'base ficticia corrupta')

    def test_importacion_legacy_unica_y_no_destructiva(self):
        f=self.base/'anterior.json'; f.write_text(json.dumps({'nombres':['uno','dos','uno']}))
        self.cola.importar_legacy(f,lambda n:True)
        self.cola.cambiar('uno','listo')
        self.cola.importar_legacy(f,lambda n:True)
        self.assertEqual(self.cola.obtener('uno')['estado'],'listo'); self.assertTrue(f.exists())
        self.assertEqual([r['nombre'] for r in self.cola.filas()],['dos'])

    def test_legacy_invalido_no_se_borra_ni_importa_parcialmente(self):
        f=self.base/'anterior.json'; contenido=json.dumps({'nombres':['uno','../incorrecto']}); f.write_text(contenido)
        with self.assertRaises(ValueError):self.cola.importar_legacy(f,lambda n:True)
        self.assertEqual(self.cola.filas(),[]); self.assertEqual(f.read_text(),contenido)

    def test_borrado_interrumpido_no_se_reactiva_y_rollback_restaura_pausa(self):
        self.cola.solicitar('ficticio'); self.cola.pausa('ficticio',True)
        previo=self.cola.preparar_borrado('ficticio')
        with self.assertRaises(C.ErrorCola):self.cola.solicitar('ficticio')
        self.cola.revertir_borrado('ficticio',previo)
        self.assertEqual(self.cola.obtener('ficticio')['pausado'],1)
        self.cola.preparar_borrado('ficticio'); self.cola.cancelar_borrado('ficticio')
        self.assertEqual(self.cola.filas(),[])

    def test_respaldo_sqlite_consistente_sin_sobrescritura(self):
        self.cola.solicitar('ficticio'); destino=self.base/'respaldo.sqlite3'
        self.cola.respaldar(destino)
        with closing(sqlite3.connect(destino)) as db:
            self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0],'ok')
            self.assertEqual(db.execute('SELECT nombre FROM tareas').fetchone()[0],'ficticio')
        with self.assertRaises(FileExistsError):self.cola.respaldar(destino)

    def test_salida_abrupta_libera_propietario_y_conserva_commits(self):
        self.cola.cerrar()
        codigo="""import os,sys
from cola_procesamiento import ColaProcesamiento
c=ColaProcesamiento(sys.argv[1])
c.solicitar('primero');c.cambiar('primero',sys.argv[2]);c.pausa('primero',True)
c.solicitar('segundo')
os._exit(73)
"""
        for estado in ('en cola','transcribiendo','generando'):
            with self.subTest(estado=estado):
                ruta=self.base/(estado.replace(' ','_')+'.sqlite3')
                r=subprocess.run([sys.executable,'-c',codigo,str(ruta),estado],capture_output=True,timeout=15,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                self.assertEqual(r.returncode,73,r.stderr.decode(errors='replace'))
                c=C.ColaProcesamiento(ruta)
                try:
                    self.assertEqual([r['nombre'] for r in c.filas()],['primero','segundo'])
                    self.assertEqual(c.obtener('primero')['pausado'],int(estado!='generando'))
                    self.assertEqual(c.obtener('primero')['estado'],estado)
                finally:c.cerrar()

    def test_caida_durante_transaccion_revierte_sin_perder_tarea(self):
        self.cola.cerrar()
        codigo="""import os,sys
from cola_procesamiento import ColaProcesamiento
c=ColaProcesamiento(sys.argv[1]);c.solicitar('ficticio')
with c.transaccion() as db:
 db.execute("UPDATE tareas SET estado='generando'")
 os._exit(73)
"""
        r=subprocess.run([sys.executable,'-c',codigo,str(self.ruta)],capture_output=True,timeout=15,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        self.assertEqual(r.returncode,73)
        c=C.ColaProcesamiento(self.ruta)
        try:self.assertEqual(c.obtener('ficticio')['estado'],'en cola')
        finally:c.cerrar()

    def test_respaldo_por_cli_no_toma_propietario_ni_detiene_la_cola(self):
        self.cola.solicitar('ficticio')
        destino=self.base/'copia.sqlite3'
        r=subprocess.run([sys.executable,'mantenimiento_cola.py','--base',str(self.ruta),'--respaldar',str(destino)],capture_output=True,timeout=15,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        self.assertEqual(r.returncode,0,r.stderr.decode(errors='replace'))
        self.assertTrue(self.cola.cambiar('ficticio','generando'))
        with closing(sqlite3.connect(destino)) as db:self.assertEqual(db.execute('SELECT estado FROM tareas').fetchone()[0],'en cola')

    def test_terminales_no_se_recargan_y_busqueda_usa_indice(self):
        with self.cola.transaccion() as db:
            db.executemany("INSERT INTO tareas(nombre,token,estado,encolado) VALUES (?,?,'listo',0)",[(f'ficticio-{i}',f'{i:032x}') for i in range(1000)])
        self.cola.solicitar('pendiente')
        self.assertEqual([r['nombre'] for r in self.cola.filas()],['pendiente'])
        plan=self.cola.db.execute("EXPLAIN QUERY PLAN SELECT * FROM tareas WHERE estado IN ('en cola','transcribiendo','generando','en pausa','error','borrando') ORDER BY orden").fetchall()
        self.assertTrue(any('tareas_estado_orden' in r[3] and 'SEARCH' in r[3] for r in plan))


class ServidorTest(unittest.TestCase):
    def setUp(self):
        import servidor as S
        self.S=S
        tmp=tempfile.TemporaryDirectory(dir=RESPALDO); self.addCleanup(tmp.cleanup)
        self.base=Path(tmp.name); self.datos=self.base/'revision'/'datos'; self.datos.mkdir(parents=True)
        self.audios=self.base/'audios'; self.audios.mkdir()
        self.pila=ExitStack(); self.addCleanup(self.pila.close)
        for nombre,valor in [('COLA_DURADERA',None),('DATOS',self.datos),('NUEVOS',self.audios),('INFORMES',self.base),
                             ('COLA_AL_REINICIAR',self.base/'legacy.json'),('ESTADO',{}),('ENCOLADO',{}),('BORRADOS',set()),
                             ('PAUSAS',{}),('PAUSADO_S',{}),('COLA',queue.Queue()),('SRV',dict(S.SRV))]:
            self.pila.enter_context(patch.object(S,nombre,valor))
        self.pila.enter_context(patch.object(S.L,'estado'))
        self.addCleanup(self.cerrar)

    def cerrar(self):
        if self.S.COLA_DURADERA is not None:self.S.COLA_DURADERA.cerrar(); self.S.COLA_DURADERA=None

    def audio(self,n):
        p=self.audios/(n+'.wav');p.write_bytes(b'WAV exclusivamente ficticio');return p

    def iniciar(self):self.S.reanudar_cola();return self.S.COLA_DURADERA

    def reiniciar(self):
        self.cerrar();self.S.ESTADO.clear();self.S.ENCOLADO.clear();self.S.PAUSAS.clear();self.S.BORRADOS.clear()
        self.S.COLA=queue.Queue();return self.iniciar()

    def test_recupera_fifo_fases_pausas_y_caso_sin_audio_visible(self):
        c=self.iniciar()
        for n in ('uno','dos','ausente'):self.audio(n);self.S.encolar(n)
        c.cambiar('uno','generando');c.cambiar('dos','transcribiendo');c.pausa('dos',True)
        self.audios.joinpath('ausente.wav').unlink()
        self.reiniciar()
        self.assertEqual(list(self.S.COLA.queue),['uno','dos'])
        self.assertEqual(self.S.ESTADO['dos']['estado'],'en pausa')
        self.assertIn('ausente',[x['nombre'] for x in self.S.listar_casos()])
        self.assertEqual(self.S.reanudar('dos','prueba')[1],200)
        self.assertEqual(self.S.COLA_DURADERA.obtener('dos')['pausado'],0)

    def test_adopta_huerfano_pero_no_informe_revisado_borrador_ni_cancelado(self):
        self.audio('huerfano');self.audio('revisado');self.audio('borrador');self.audio('cancelado')
        (self.datos/'revisado.informe_ia.txt').write_text('Informe ficticio')
        (self.datos/'borrador.borrador.json').write_text('{}')
        c=C.ColaProcesamiento(self.datos.parent/'cola_procesamiento.sqlite3')
        c.preparar_borrado('cancelado');c.cancelar_borrado('cancelado');c.cerrar()
        self.iniciar();self.assertEqual(list(self.S.COLA.queue),['huerfano'])

    def test_checkpoint_valido_no_regenera_ni_borra_revision(self):
        c=self.iniciar();self.audio('listo');self.S.encolar('listo')
        for sufijo in self.S.ARCHIVOS_RESULTADO:(self.datos/('listo'+sufijo)).write_text('Resultado ficticio',encoding='utf-8')
        self.S.confirmar_resultado('listo',self.S.firma_audio(self.audios/'listo.wav'))
        borrador=self.datos/'listo.borrador.html';borrador.write_text('Edición ficticia conservada')
        self.reiniciar()
        self.assertTrue(self.S.COLA.empty());self.assertEqual(self.S.COLA_DURADERA.obtener('listo')['estado'],'listo')
        self.assertEqual(borrador.read_text(),'Edición ficticia conservada')

    def test_checkpoint_corrupto_con_revision_se_detiene_para_recuperar(self):
        self.iniciar();self.audio('caso');self.S.encolar('caso')
        (self.datos/'caso.procesamiento.json').write_text('{}');(self.datos/'caso.final.txt').write_text('Final ficticio')
        self.reiniciar();self.assertTrue(self.S.COLA.empty());self.assertEqual(self.S.ESTADO['caso']['estado'],'error')

    def test_word_o_formato_sin_checkpoint_no_se_sobrescriben_al_recuperar(self):
        self.iniciar()
        for n in ('word','formato'):self.audio(n);self.S.encolar(n)
        word=self.base/'word.docx';word.write_bytes(b'Word exclusivamente ficticio')
        formato=self.datos/'formato.formato.json';formato.write_text('{"v":2}')
        self.reiniciar();self.assertTrue(self.S.COLA.empty())
        self.assertEqual(word.read_bytes(),b'Word exclusivamente ficticio');self.assertEqual(formato.read_text(),'{"v":2}')

    def test_una_solicitud_nueva_no_reutiliza_checkpoint_anterior(self):
        c=self.iniciar();self.audio('caso');self.S.encolar('caso')
        for s in self.S.ARCHIVOS_RESULTADO:(self.datos/('caso'+s)).write_text('Resultado ficticio')
        self.S.confirmar_resultado('caso',self.S.firma_audio(self.audios/'caso.wav'));self.S.poner_estado('caso','listo')
        self.S.encolar('caso');self.assertFalse(self.S.resultado_confirmado('caso'))

    def test_confirmacion_de_encolado_fallida_no_publica_en_memoria(self):
        c=self.iniciar();self.audio('caso');conexion=c.db;falso=Mock(wraps=conexion)
        falso.commit.side_effect=sqlite3.OperationalError('disco lleno ficticio')
        with patch.object(c,'db',falso):
            with self.assertRaises(C.ErrorCola):self.S.encolar('caso')
        self.assertTrue(self.S.COLA.empty());self.assertNotIn('caso',self.S.ESTADO)

    def test_commit_real_respuesta_perdida_se_recupera_sin_duplicar(self):
        c=self.iniciar();self.audio('caso');conexion=c.db;falso=Mock(wraps=conexion)
        def perdido():conexion.commit();raise sqlite3.OperationalError('Confirmación perdida ficticia')
        falso.commit.side_effect=perdido
        with patch.object(c,'db',falso):
            with self.assertRaises(C.ErrorCola):self.S.encolar('caso')
        token=c.obtener('caso')['token'];self.S.encolar('caso')
        self.assertEqual(c.obtener('caso')['token'],token);self.assertEqual(list(self.S.COLA.queue),['caso'])

    def test_http_no_confirma_si_el_registro_duradero_falla(self):
        self.iniciar();self.audio('caso')
        httpd=self.S.ThreadingHTTPServer(('127.0.0.1',0),self.S.H)
        hilo=threading.Thread(target=httpd.serve_forever,daemon=True);hilo.start()
        try:
            with patch.object(self.S,'PUERTO',httpd.server_port),patch.object(self.S.COLA_DURADERA,'solicitar',side_effect=C.ErrorCola('Fallo ficticio')):
                cliente=http.client.HTTPConnection('127.0.0.1',httpd.server_port,timeout=5)
                try:
                    cliente.request('POST','/api/procesar',json.dumps({'nombre':'caso'}),{'Content-Type':'application/json'})
                    r=cliente.getresponse();d=json.loads(r.read());self.assertEqual(r.status,503);self.assertNotIn('ok',d)
                finally:cliente.close()
        finally:httpd.shutdown();httpd.server_close();hilo.join(2)

    def test_borrado_real_y_reversion_por_permiso_no_resucitan_tareas(self):
        c=self.iniciar();self.audio('caso');self.S.encolar('caso')
        token=c.obtener('caso')['token']
        with patch.object(self.S,'_apartar',side_effect=PermissionError('Bloqueo ficticio')):
            self.assertIn('No se pudo borrar',self.S.borrar_caso('caso'))
        self.assertEqual(c.obtener('caso')['estado'],'en cola');self.assertEqual(c.obtener('caso')['token'],token)
        self.assertIsNone(self.S.borrar_caso('caso'))
        self.reiniciar();self.assertTrue(self.S.COLA.empty())

    def test_subida_no_confirmada_se_adopta_completa_al_reabrir(self):
        self.iniciar();cuerpo=b'RIFF'+(72).to_bytes(4,'little')+b'WAVE'+b'\0'*68
        httpd=self.S.ThreadingHTTPServer(('127.0.0.1',0),self.S.H)
        hilo=threading.Thread(target=httpd.serve_forever,daemon=True);hilo.start()
        try:
            with patch.object(self.S,'PUERTO',httpd.server_port),patch.object(self.S.COLA_DURADERA,'solicitar',side_effect=C.ErrorCola('Fallo ficticio')):
                cliente=http.client.HTTPConnection('127.0.0.1',httpd.server_port,timeout=5)
                try:
                    cliente.request('POST','/api/subir?archivo=subido.wav',cuerpo,{'Content-Type':'audio/wav'})
                    r=cliente.getresponse();r.read();self.assertEqual(r.status,503)
                finally:cliente.close()
        finally:httpd.shutdown();httpd.server_close();hilo.join(2)
        self.assertEqual((self.audios/'subido.wav').read_bytes(),cuerpo)
        self.assertTrue((self.datos/'subido.origen.txt').exists());self.assertTrue(self.S.COLA.empty())
        self.reiniciar();self.assertEqual(list(self.S.COLA.queue),['subido'])

    def test_cancelar_registro_sin_audio_y_borrado_sin_commit_final(self):
        c=self.iniciar();self.audio('caso');self.S.encolar('caso')
        with patch.object(c,'cancelar_borrado',side_effect=C.ErrorCola('Fallo final ficticio')):
            with self.assertRaises(C.ErrorCola):self.S.borrar_caso('caso')
        self.reiniciar();self.assertEqual(self.S.COLA_DURADERA.obtener('caso')['estado'],'borrando')
        self.assertIsNone(self.S.borrar_caso('caso'));self.assertNotIn('caso',self.S.ESTADO)
        self.S.COLA_DURADERA.solicitar('sin-audio');self.S.poner_estado('sin-audio','error','No encuentro audio')
        self.assertIsNone(self.S.borrar_caso('sin-audio'))
        self.reiniciar();self.assertTrue(self.S.COLA.empty());self.assertNotIn('sin-audio',self.S.ESTADO)

    def test_arranque_no_inicia_hilos_ni_acepta_trabajo_con_cola_inaccesible(self):
        with (patch.object(self.S,'Servidor') as servidor,patch.object(self.S,'reanudar_cola',side_effect=C.ErrorCola('Fallo ficticio')),
              patch.object(self.S.L,'configurar'),patch.object(self.S.M,'titulo_consola'),patch.object(self.S.threading,'Thread') as hilo):
            self.assertEqual(self.S.main(),1)
            servidor.return_value.server_close.assert_called_once();hilo.assert_not_called()

    def test_trabajador_completo_reabre_tras_caida_en_asr_ia_y_antes_de_listo(self):
        codigo='''import json,os,sys,queue
from pathlib import Path
import servidor as S
base=Path(sys.argv[1]);modo=sys.argv[2]
S.AQUI=base;S.NUEVOS=base/'audios';S.INFORMES=base;S.DATOS=base/'revision'/'datos'
S.COLA_AL_REINICIAR=base/'legacy.json';S.SIMULAR=True
os.environ['SIMULAR_DEMORA']='0'
S.calcular_voz=lambda *a:None
S.anotar_voz=lambda *a,**k:None
S.resumen_voz=lambda *a:None
S.PAC.calcular=lambda *a,**k:None
S.esperar_ia=lambda *a:None
S.N.cargar_banco=lambda:[]
S.N.estudios_sin_plantilla=lambda *a:[]
class Fin(BaseException):pass
class ColaFinita(queue.Queue):
 def get(self,block=True,timeout=None):
  if self.empty():raise Fin()
  return super().get(block,timeout)
S.COLA=ColaFinita()
S.reanudar_cola()
empezar=S.empezar;poner=S.poner_estado
generaciones=0
def inicio(n,e,msg=''):
 global generaciones
 r=empezar(n,e,msg)
 if e=='generando':generaciones+=1
 if (modo=='asr' and e=='transcribiendo') or (modo=='ia' and e=='generando'):os._exit(74)
 return r
def estado(n,e,msg=''):
 if modo=='listo' and e=='listo':os._exit(74)
 return poner(n,e,msg)
S.empezar=inicio;S.poner_estado=estado
if modo=='perdida':
 cambiar=S.COLA_DURADERA.cambiar
 def commit_perdido(n,e):
  r=cambiar(n,e)
  if e=='listo':raise S.CP.ErrorCola('Respuesta local perdida ficticia')
  return r
 S.COLA_DURADERA.cambiar=commit_perdido
try:S.trabajador()
except Fin:pass
assert S.COLA_DURADERA.obtener('ficticio')['estado']=='listo'
assert S.ESTADO.get('ficticio',{}).get('estado') in ('listo',None)
if modo=='perdida':assert generaciones==1
S.COLA_DURADERA.cerrar()
'''
        for etapa in ('asr','ia','listo','perdida'):
            with self.subTest(etapa=etapa):
                base=self.base/etapa;datos=base/'revision'/'datos';datos.mkdir(parents=True)
                audios=base/'audios';audios.mkdir();(audios/'ficticio.wav').write_bytes(b'Audio ficticio')
                for sub,obj in [('fase1/json',{'con_vocab':{'texto':'Dictado ficticio','palabras':[],'huecos':[]}}),
                                ('fase2/gemma4_12b',{'salida':'Informe exclusivamente ficticio.'})]:
                    p=base/'resultados'/sub;p.mkdir(parents=True);(p/'ficticio.json').write_text(json.dumps(obj))
                pasos=[(etapa,74),('continuar',0)] if etapa!='perdida' else [('perdida',0)]
                for modo,codigo_salida in pasos:
                    r=subprocess.run([sys.executable,'-c',codigo,str(base),modo],capture_output=True,timeout=20,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                    self.assertEqual(r.returncode,codigo_salida,r.stderr.decode(errors='replace'))
                    if modo=='listo':
                        (datos/'ficticio.borrador.html').write_text('Revisión ficticia que debe conservarse')
                if etapa=='listo':self.assertEqual((datos/'ficticio.borrador.html').read_text(),'Revisión ficticia que debe conservarse')


if __name__=='__main__':unittest.main()
