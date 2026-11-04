"""Benchmark opt-in de GPU con voz sintética, daemon separado y vigilancia de producción.

python herramientas/validar_gpu_real.py --ejecutar
Sin esa opción solo explica el alcance; no carga modelos. Windows/.venv del servidor.
"""
import argparse
import csv
import gc
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import socket
import statistics
import subprocess
import sys
import time
import urllib.request
import wave

SIN_VENTANA = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
FICTICIOS = [
    'Este es un dictado ficticio de prueba, sin paciente real. Ecografía tiroidea. Tiroides de tamaño conservado, contornos regulares y ecoestructura homogénea. Lóbulo derecho de cuarenta por quince por doce milímetros. Lóbulo izquierdo de treinta y ocho por catorce por once milímetros. Istmo de dos milímetros. No se identifican nódulos sólidos ni quísticos. No se observan adenopatías cervicales. Conclusión: estudio sin alteraciones significativas. Fin del dictado ficticio.',
    'Este es un dictado ficticio de prueba, sin paciente real. Mamografía bilateral. Mamas de densidad dispersa, categoría ACR dos. No se identifican nódulos, distorsiones ni agrupaciones de microcalcificaciones sospechosas. Regiones axilares sin hallazgos significativos. La ecografía mamaria muestra tejido de aspecto conservado, sin imágenes nodulares sólidas ni quísticas. Categorización conjunta BI RADS uno. Se sugiere control de rutina. Fin del dictado ficticio.',
    'Este es un dictado ficticio de prueba, sin paciente real. Radiografía de tórax, frente y perfil. Campos pulmonares bien expandidos, sin infiltrados ni imágenes nodulares evidentes. Senos costofrénicos libres. Silueta cardíaca de tamaño conservado. No se observan alteraciones óseas agudas en las estructuras incluidas en el estudio. Conclusión: no se identifican signos de proceso pleuropulmonar agudo. Fin del dictado ficticio.',
    'Este es un dictado ficticio de prueba, sin paciente real. Ecografía abdominal. Hígado de tamaño y ecoestructura conservados, sin lesiones focales. Vesícula de paredes finas, sin litiasis. Vía biliar no dilatada. Páncreas y bazo sin particularidades. Ambos riñones de tamaño conservado, sin dilatación de la vía excretora ni imágenes compatibles con litiasis. No se observa líquido libre. Conclusión: estudio sin alteraciones significativas. Fin del dictado ficticio.'
]


def api(puerto, ruta, datos=None, timeout=5):
    req = urllib.request.Request(f'http://127.0.0.1:{puerto}/api/{ruta}',
        data=None if datos is None else json.dumps(datos).encode('utf-8'),
        headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def escucha(puerto):
    with socket.socket() as s:
        s.settimeout(.2)
        return s.connect_ex(('127.0.0.1',puerto)) == 0


def python_pids():
    r=subprocess.run(['tasklist','/FO','CSV','/NH'],capture_output=True,text=True,timeout=10,creationflags=SIN_VENTANA)
    r.check_returncode()
    return {int(f[1]) for f in csv.reader(io.StringIO(r.stdout)) if len(f)>1 and f[0].lower() in ('python.exe','pythonw.exe') and f[1].isdigit()}


def libre(permitidos):
    if escucha(8765):
        raise RuntimeError('El servidor de producción comenzó a escuchar; se cancela el benchmark.')
    if api(11434,'ps').get('models'):
        raise RuntimeError('Ollama de uso diario está ocupado; se cancela el benchmark.')
    actuales=python_pids()
    if actuales - permitidos:
        # Windows puede usar un redirector .venv y un intérprete hijo para el mismo comando.
        r=subprocess.run(['powershell','-NoProfile','-Command',"Get-CimInstance Win32_Process -Filter \"Name='python.exe' OR Name='pythonw.exe'\" | Select-Object ProcessId,ParentProcessId | ConvertTo-Json -Compress"],capture_output=True,text=True,timeout=15,creationflags=SIN_VENTANA)
        r.check_returncode();familia=json.loads(r.stdout or '[]')
        if isinstance(familia,dict):familia=[familia]
        for _ in range(len(familia)):
            for proceso in familia:
                if proceso['ParentProcessId'] in permitidos:permitidos.add(proceso['ProcessId'])
        if actuales - permitidos:
            raise RuntimeError('Hay otro proceso Python; no se reserva la GPU.')


def gpu():
    r=subprocess.run(['nvidia-smi','--query-gpu=name,memory.used,memory.total,utilization.gpu,temperature.gpu','--format=csv,noheader,nounits'],capture_output=True,text=True,timeout=10,creationflags=subprocess.CREATE_NO_WINDOW)
    r.check_returncode()
    return r.stdout.strip()


def descargar_modelo():
    api(11435,'generate',{'model':'gemma4:12b','keep_alive':0},timeout=120)
    if api(11435,'ps').get('models'):
        raise RuntimeError('El daemon de ensayo no confirmó la liberación de Gemma.')


def validar_reanudacion(raiz, base):
    raiz, base = raiz.resolve(), base.resolve()
    if raiz == base or not raiz.is_relative_to(base) or not raiz.name.startswith('gpu_real_'):
        raise RuntimeError('La reanudación debe ser un ensayo bajo respaldo.')
    if json.loads((raiz/'dictados.json').read_text(encoding='utf-8')) != FICTICIOS:
        raise RuntimeError('No coincide el corpus sintético.')
    entorno=json.loads((raiz/'entorno.json').read_text(encoding='utf-8'))
    nombres={f'audio_{i}.wav' for i in range(1,5)}
    if set(entorno['sha_audios']) != nombres or {p.name for p in (raiz/'audios').glob('*.wav')} != nombres:
        raise RuntimeError('El corpus debe contener exactamente los cuatro WAV sintéticos.')
    for nombre,firma in entorno['sha_audios'].items():
        if hashlib.sha256((raiz/'audios'/nombre).read_bytes()).hexdigest()!=firma:
            raise RuntimeError('Cambió un WAV de ensayo.')
    datos=json.loads((raiz/'resultados.json').read_text(encoding='utf-8'))
    if datos.get('completo') or datos.get('orden') != [1,2,4,4,2,1,2,4,1] or len(datos['pruebas'])>9:
        raise RuntimeError('La campaña ya terminó o usa otro protocolo.')
    for numero,p in enumerate(datos['pruebas'],1):
        if p['ensayo']!=numero or p['lote']!=datos['orden'][numero-1] or [a['audio'] for a in p['audios']]!=[1,2,3,4]:
            raise RuntimeError('Los ensayos previos no forman un prefijo completo válido.')


def trabajador(raiz, modelo_whisper):
    sys.path.insert(0,str(raiz/'sistema'))
    from transcripcion.asr import whisper as F
    from transcripcion.controles import avisos as AV
    from transcripcion.controles import marcas as MAR
    from transcripcion.ia import ollama as OLL
    from transcripcion.ia import prompt as PR
    from transcripcion.asr import huecos as H
    OLL.OLLAMA='http://127.0.0.1:11435'
    audios=sorted((raiz/'audios').glob('*.wav'))
    duraciones=[]
    for audio in audios:
        with wave.open(str(audio)) as w:duraciones.append(w.getnframes()/w.getframerate())
    # Contexto de ensayo fijo y exclusivamente ficticio. No se lee el banco de producción.
    ejemplos=[{'dictado':'Ecografía tiroidea normal.','informe':'ECOGRAFÍA TIROIDEA\n\nTiroides de tamaño y ecoestructura conservados. Lo saluda atte.'},
              {'dictado':'Radiografía de tórax sin hallazgos agudos.','informe':'RADIOGRAFÍA DE TÓRAX\n\nNo se identifican signos de proceso pleuropulmonar agudo. Lo saluda atte.'},
              {'dictado':'Ecografía abdominal sin alteraciones.','informe':'ECOGRAFÍA ABDOMINAL\n\nNo se identifican alteraciones significativas. Lo saluda atte.'}]
    resultados={'completo':False,'duraciones_audio_s':duraciones,'orden':[1,2,4,4,2,1,2,4,1],
                 'modelo_whisper':modelo_whisper,'modelo_ia':'gemma4:12b','pruebas':[]}
    if (raiz/'resultados.json').exists():
        resultados=json.loads((raiz/'resultados.json').read_text(encoding='utf-8'))
    def guardar():
        (raiz/'resultados.json').write_text(json.dumps(resultados,ensure_ascii=False,indent=2),encoding='utf-8')
    guardar()
    for numero,tamano in enumerate(resultados['orden'],1):
        if numero <= len(resultados['pruebas']):continue
        descargar_modelo()
        registros=[];cargas=[]
        inicio=time.perf_counter()
        print(f'INICIO ensayo={numero} lote={tamano}',flush=True)
        for pos in range(0,len(audios),tamano):
            descargar_modelo()
            carga=time.perf_counter()
            modelo=F.cargar_modelo(modelo_whisper,'cuda')
            cargas.append(time.perf_counter()-carga)
            trans=[]
            for i in range(pos,min(pos+tamano,len(audios))):
                t0=time.perf_counter()
                t=F.transcribir(modelo,audios[i],F.leer_vocabulario(F.VOCAB_DEF))
                palabras,huecos=H.reparar(modelo,F.cargar_audio(audios[i]),t['palabras'],F.leer_vocabulario(F.VOCAB_DEF))
                trans.append((i,{'texto':H.texto_de(palabras),'palabras':palabras,'huecos':huecos},time.perf_counter()-t0))
            del modelo;gc.collect()
            for i,t,asr_s in trans:
                metricas={};t0=time.perf_counter()
                salida,_,entrada,tokens=OLL.llamar_ia('gemma4:12b',PR.armar_mensajes(t['texto'],ejemplos),metricas=metricas)
                marcado=MAR.marcar(salida,t['texto'],t['palabras'])
                omisiones=AV.omisiones(t['texto'],salida,t['palabras'])
                ia_s=time.perf_counter()-t0
                listo=time.perf_counter()-inicio
                modelos=api(11435,'ps').get('models',[])
                memoria=[{k:m.get(k) for k in ('name','size','size_vram')} for m in modelos]
                registros.append({'audio':i+1,'listo_s':listo,'asr_s':asr_s,'ia_controles_s':ia_s,
                    'tokens_entrada':entrada,'tokens_salida':tokens,'metricas':metricas,'modelos':memoria,
                    'omisiones':len(omisiones),'huecos':len(t['huecos']),'lineas':len(marcado),'gpu':gpu()})
                (raiz/f'ensayo_{numero}_audio_{i+1}.txt').write_text(t['texto']+'\n\n'+salida,encoding='utf-8')
                (raiz/'progreso.json').write_text(json.dumps({'ensayo':numero,'lote':tamano,'audio':i+1,'espera_s':round(listo,2)}),encoding='utf-8')
                print(f'LISTO ensayo={numero} lote={tamano} audio={i+1} espera={listo:.2f}s',flush=True)
        total=time.perf_counter()-inicio
        resultados['pruebas'].append({'ensayo':numero,'lote':tamano,'total_s':total,'primero_s':registros[0]['listo_s'],
            'espera_media_s':statistics.mean(r['listo_s'] for r in registros),'ultimo_s':registros[-1]['listo_s'],
            'informes_min':len(audios)*60/total,'cargas_whisper_s':cargas,'audios':registros})
        guardar()
    descargar_modelo()
    resultados['completo']=True;guardar()


def ejecutar(reanudar=None):
    if os.name!='nt':raise RuntimeError('Este protocolo usa voz sintética local de Windows.')
    permitidos=python_pids()
    if permitidos - {os.getpid(),os.getppid()}:
        raise RuntimeError('Ya hay otros procesos Python; no se inicia la prueba.')
    libre(permitidos)
    if escucha(11435):raise RuntimeError('El puerto de ensayo ya está ocupado.')
    from huggingface_hub import try_to_load_from_cache
    modelo=try_to_load_from_cache('Systran/faster-whisper-large-v3','model.bin')
    if not isinstance(modelo,str) or not Path(modelo).is_file():raise RuntimeError('Whisper no está en caché; no se descarga durante la validación.')
    ollama=shutil.which('ollama')
    if not ollama:raise RuntimeError('No se encontró ollama.exe')
    if 'gemma4:12b' not in [m.get('name') for m in api(11434,'tags').get('models',[])]:raise RuntimeError('Falta Gemma; no se descargan pesos.')
    proyecto=Path(__file__).resolve().parents[1]
    raiz=proyecto/'respaldo'/('gpu_real_'+time.strftime('%Y%m%d_%H%M%S')) if reanudar is None else reanudar.resolve()
    if reanudar is not None:
        validar_reanudacion(raiz, proyecto/'respaldo')
    else:
        raiz.mkdir();(raiz/'audios').mkdir();(raiz/'sistema').mkdir()
    for nombre in ['vocabulario.txt']:
        shutil.copy2(proyecto/nombre,raiz/'sistema'/nombre)
    # paquete: whisper y huecos (asr), ia, controles, conocimiento, registro, plataforma, persistencia y usuarios
    shutil.copytree(proyecto/'transcripcion',raiz/'sistema'/'transcripcion',dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__'))
    shutil.copytree(proyecto/'conocimiento.ejemplo',raiz/'sistema'/'conocimiento.ejemplo',dirs_exist_ok=True)
    (raiz/'dictados.json').write_text(json.dumps(FICTICIOS,ensure_ascii=False),encoding='utf-8')
    guion=raiz/'sintetizar.ps1'
    guion.write_text('''$ErrorActionPreference='Stop'
Add-Type -AssemblyName System.Speech
$s=New-Object System.Speech.Synthesis.SpeechSynthesizer
try {
 $s.SelectVoice('Microsoft Sabina Desktop');$s.Rate=-1
 $formato=New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(16000,[System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen,[System.Speech.AudioFormat.AudioChannel]::Mono)
 $textos=Get-Content -LiteralPath (Join-Path $PSScriptRoot 'dictados.json') -Raw -Encoding UTF8 | ConvertFrom-Json
 for($i=0;$i -lt $textos.Count;$i++) {
  $s.SetOutputToWaveFile((Join-Path $PSScriptRoot ('audios/audio_'+($i+1)+'.wav')),$formato)
  $s.Speak($textos[$i]);$s.SetOutputToNull()
 }
} finally {$s.Dispose()}
''',encoding='utf-8-sig')
    if reanudar is None:
        sintesis=subprocess.run(['powershell','-NoProfile','-ExecutionPolicy','Bypass','-File',str(guion)],capture_output=True,text=True,timeout=120,creationflags=subprocess.CREATE_NO_WINDOW)
        if sintesis.returncode:raise RuntimeError('Falló la síntesis ficticia: '+sintesis.stderr[-2000:])
    metadata={'gpu_inicial':gpu(),'voz':'Microsoft Sabina Desktop','rate':-1,'guardia':'puerto 8765 cerrado; Ollama 11434 sin modelos; sin otros procesos Python',
              'sha_audios':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (raiz/'audios').glob('*.wav')}}
    if reanudar is None:(raiz/'entorno.json').write_text(json.dumps(metadata,indent=2),encoding='utf-8')
    env=dict(os.environ,OLLAMA_HOST='127.0.0.1:11435',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1')
    daemon=None;proceso=None
    def terminar(p):
        if p is not None and p.poll() is None:
            # Solo el árbol iniciado por este controlador; nunca la instancia de uso diario.
            subprocess.run(['taskkill','/PID',str(p.pid),'/T','/F'],capture_output=True,creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        with open(raiz/'ollama.log','w',encoding='utf-8') as log:
            daemon=subprocess.Popen([ollama,'serve'],env=env,stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW)
            for _ in range(60):
                if daemon.poll() is not None:raise RuntimeError('El daemon de ensayo no inició.')
                if escucha(11435):break
                time.sleep(.5)
            else:raise RuntimeError('Timeout del daemon de ensayo.')
            libre(permitidos)
            proceso=subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'--ejecutar','--trabajador',str(raiz),'--modelo',str(Path(modelo).parent)],env=env,creationflags=subprocess.CREATE_NO_WINDOW)
            permitidos.add(proceso.pid)
            print('CARPETA '+str(raiz),flush=True)
            previo=None
            while proceso.poll() is None:
                libre(permitidos)
                if daemon.poll() is not None:raise RuntimeError('El daemon de ensayo terminó inesperadamente.')
                if (raiz/'progreso.json').exists():
                    try:
                        progreso=json.loads((raiz/'progreso.json').read_text(encoding='utf-8'))
                        if progreso!=previo:print('PROGRESO '+json.dumps(progreso),flush=True);previo=progreso
                    except json.JSONDecodeError:pass
                time.sleep(1)
            if proceso.returncode:raise RuntimeError('Falló el trabajador; revisar resultados parciales.')
            print('FINALIZADO '+str(raiz/'resultados.json'),flush=True)
    finally:
        terminar(proceso)
        terminar(daemon)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--ejecutar',action='store_true')
    p.add_argument('--trabajador',type=Path,help=argparse.SUPPRESS)
    p.add_argument('--modelo',help=argparse.SUPPRESS)
    p.add_argument('--reanudar',type=Path,help='Carpeta de ensayo sintético previamente interrumpido')
    args=p.parse_args()
    if args.ejecutar and args.trabajador:trabajador(args.trabajador,args.modelo)
    elif args.ejecutar:ejecutar(args.reanudar)
    else:p.print_help()
