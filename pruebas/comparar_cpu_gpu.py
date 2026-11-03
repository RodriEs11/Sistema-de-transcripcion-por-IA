"""Comparación opt-in aislada: lotes GPU actuales vs Whisper GPU / Gemma CPU.

No modifica configuración, no detiene producción y solo usa corpus sintético
previamente validado. Sin --ejecutar muestra ayuda. Windows, entorno .venv.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import gc
import hashlib
import json
import math
import os
from pathlib import Path
import queue
import shutil
import statistics
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone

import validar_gpu_real as G

ORDEN = ['actual', 'paralelo', 'paralelo', 'actual', 'actual', 'paralelo']
MODELO = 'gemma4:12b'
EJEMPLOS = [
    {'dictado': 'Ecografía tiroidea normal.', 'informe': 'ECOGRAFÍA TIROIDEA\n\nTiroides de tamaño y ecoestructura conservados. Lo saluda atte.'},
    {'dictado': 'Radiografía de tórax sin hallazgos agudos.', 'informe': 'RADIOGRAFÍA DE TÓRAX\n\nNo se identifican signos de proceso pleuropulmonar agudo. Lo saluda atte.'},
    {'dictado': 'Ecografía abdominal sin alteraciones.', 'informe': 'ECOGRAFÍA ABDOMINAL\n\nNo se identifican alteraciones significativas. Lo saluda atte.'},
]


def guardar(ruta, datos):
    temporal = ruta.with_suffix('.tmp')
    temporal.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding='utf-8')
    temporal.replace(ruta)


def estado_produccion():
    with urllib.request.urlopen('http://127.0.0.1:8765/api/admin/estado', timeout=3) as r:
        e = json.load(r)
    # No conservar nombres, registros, pacientes, sesiones ni contenido de casos.
    return {'version': e['servidor']['version'], 'cola': len(e['cola']['items']),
            'abiertos': len(e['abiertos']), 'pausada': e['cola']['pausada'],
            'en_pausa': bool(e['cola']['en_pausa']),
            'trabajando': bool(e['ia']['trabajando'] or e['whisper']['trabajando']),
            'reinicio': bool(e.get('mantenimiento', {}).get('reinicio'))}


def validar_libre(e, modelos):
    if any(e[k] for k in ('cola', 'abiertos', 'pausada', 'en_pausa', 'trabajando', 'reinicio')):
        raise RuntimeError('Hay actividad de producción; no se ejecuta la prueba.')
    if modelos:
        raise RuntimeError('La instancia habitual todavía tiene modelos cargados.')


def validar_corpus(origen):
    if json.loads((origen/'dictados.json').read_text(encoding='utf-8')) != G.FICTICIOS:
        raise ValueError('El corpus no coincide con los dictados ficticios conocidos.')
    firmas = json.loads((origen/'entorno.json').read_text(encoding='utf-8'))['sha_audios']
    nombres = {f'audio_{i}.wav' for i in range(1, 5)}
    if set(firmas) != nombres or {p.name for p in (origen/'audios').glob('*.wav')} != nombres:
        raise ValueError('Se requieren exactamente los cuatro WAV ficticios.')
    for nombre, firma in firmas.items():
        if hashlib.sha256((origen/'audios'/nombre).read_bytes()).hexdigest() != firma:
            raise ValueError('Cambió el corpus sintético.')
    return firmas


def resumen(pruebas):
    if len(pruebas) != len(ORDEN):
        raise ValueError('Faltan ensayos completos.')
    for n, (p, modo) in enumerate(zip(pruebas, ORDEN), 1):
        if p['ensayo'] != n or p['modo'] != modo or [a['audio'] for a in p['audios']] != [1, 2, 3, 4]:
            raise ValueError('Secuencia incompleta o inválida.')
        tiempos = [a['listo_s'] for a in p['audios']]
        if any(not isinstance(v, (int, float)) or isinstance(v, bool) or not math.isfinite(v) or v <= 0
               for v in [p['total_s'], *tiempos]):
            raise ValueError('Tiempo inválido.')
        if tiempos != sorted(tiempos) or tiempos[-1] > p['total_s']:
            raise ValueError('Cronología inválida.')
        if modo == 'paralelo' and p['solapamiento_s'] <= 0:
            raise ValueError('No hubo solapamiento entre ASR e IA.')
    salida = {}
    for modo in ('actual', 'paralelo'):
        grupo = [p for p in pruebas if p['modo'] == modo]
        salida[modo] = {k: statistics.median(p[k] for p in grupo)
                       for k in ('total_s', 'primero_s', 'espera_media_s', 'informes_min', 'solapamiento_s')}
        salida[modo]['rango_total_s'] = [min(p['total_s'] for p in grupo), max(p['total_s'] for p in grupo)]
        audios = [a for p in grupo for a in p['audios']]
        salida[modo]['tokens_s'] = sum(a['metricas']['eval_count'] for a in audios) / sum(a['metricas']['eval_duration_s'] for a in audios)
        salida[modo]['asr_acumulado_s'] = statistics.median(sum(a['asr_fin_s']-a['asr_inicio_s'] for a in p['audios']) for p in grupo)
        salida[modo]['omisiones'] = sum(a['omisiones'] for a in audios)
        salida[modo]['huecos'] = sum(a['huecos'] for a in audios)
    return salida


def trabajador(raiz, modo, numero, modelo_whisper):
    sys.path.insert(0, str(raiz/'sistema'))
    import fase1_transcribir as F
    import huecos as H
    import nucleo as N
    import ctranslate2
    puerto = 11435 if modo == 'actual' else 11436
    N.OLLAMA = f'http://127.0.0.1:{puerto}'
    post_original = N._post
    if modo == 'paralelo':
        def post_cpu(payload, timeout=600):
            payload = dict(payload, options=dict(payload['options'], num_gpu=0))
            return post_original(payload, timeout=timeout)
        N._post = post_cpu
    audios = sorted((raiz/'audios').glob('*.wav'))
    vocab = F.leer_vocabulario(F.VOCAB_DEF)
    registros = []
    cargas = []
    inicio = time.perf_counter()
    ahora = lambda: time.perf_counter()-inicio

    def transcribir(modelo, i):
        t0 = ahora()
        t = F.transcribir(modelo, audios[i], vocab)
        palabras, huecos = H.reparar(modelo, F.cargar_audio(audios[i]), t['palabras'], vocab)
        return {'audio': i+1, 'texto': H.texto_de(palabras), 'palabras': palabras,
                'huecos': len(huecos), 'asr_inicio_s': t0, 'asr_fin_s': ahora()}

    def adaptar(t):
        t0 = ahora()
        metricas = {}
        salida, _, entrada, tokens = N.llamar_ia(MODELO, N.armar_mensajes(t['texto'], EJEMPLOS), metricas=metricas)
        marcado = N.marcar(salida, t['texto'], t['palabras'])
        omisiones = N.omisiones(t['texto'], salida, t['palabras'])
        listo = ahora()
        modelos = G.api(puerto, 'ps')['models']
        if len(modelos) != 1 or modelos[0]['name'] != MODELO:
            raise RuntimeError('No se puede verificar la residencia del modelo.')
        if (modo == 'paralelo') != (modelos[0]['size_vram'] == 0):
            raise RuntimeError('Gemma no está ejecutándose en el dispositivo esperado.')
        r = {k: v for k, v in t.items() if k not in ('texto', 'palabras')}
        r.update(ia_inicio_s=t0, listo_s=listo, metricas=metricas, tokens_entrada=entrada,
                 tokens_salida=tokens, omisiones=len(omisiones), lineas=len(marcado),
                 gemma_vram=modelos[0]['size_vram'])
        guardar(raiz/f'ensayo_{numero}_audio_{t["audio"]}.json',
                dict(r, transcripcion=t['texto'], salida=salida, marcado=marcado, omisiones_detalle=omisiones))
        registros.append(r)
        print(f'LISTO ensayo={numero} modo={modo} audio={t["audio"]} espera={listo:.2f}s', flush=True)

    def cargar():
        t0 = ahora()
        m = F.cargar_modelo(modelo_whisper, 'cuda')
        if m.model.device != 'cuda':
            raise RuntimeError('Whisper no está en CUDA.')
        cargas.append(ahora()-t0)
        return m

    precarga = None
    if modo == 'actual':
        for pos in (0, 2):
            G.api(puerto, 'generate', {'model': MODELO, 'keep_alive': 0}, timeout=120)
            modelo = cargar()
            trans = [transcribir(modelo, i) for i in range(pos, pos+2)]
            del modelo
            gc.collect()
            for t in trans:
                adaptar(t)
    else:
        cola = queue.Queue()
        def consumidor():
            t0 = ahora()
            r = G.api(puerto, 'generate', {'model': MODELO, 'keep_alive': '15m',
                      'options': {'num_ctx': 12288, 'num_gpu': 0}}, timeout=600)
            prec = {'inicio_s': t0, 'fin_s': ahora(), 'load_duration_s': r.get('load_duration', 0)/1e9}
            while True:
                t = cola.get()
                if t is None:
                    return prec
                adaptar(t)
        with ThreadPoolExecutor(max_workers=1) as pool:
            futuro = pool.submit(consumidor)
            try:
                modelo = cargar()
                for i in range(4):
                    if futuro.done():
                        futuro.result()
                    cola.put(transcribir(modelo, i))
            finally:
                cola.put(None)
            precarga = futuro.result()
            del modelo
            gc.collect()
    total = ahora()
    solapamiento = sum(max(0, min(a['asr_fin_s'], b['listo_s'])-max(a['asr_inicio_s'], b['ia_inicio_s']))
                        for a in registros for b in registros)
    guardar(raiz/f'ensayo_{numero}.json', {'ensayo': numero, 'modo': modo,
            'total_s': total, 'primero_s': registros[0]['listo_s'],
            'espera_media_s': statistics.mean(r['listo_s'] for r in registros),
            'informes_min': 240/total, 'solapamiento_s': solapamiento,
            'cargas_whisper_s': cargas, 'precarga_gemma': precarga,
            'ctranslate2': ctranslate2.__version__, 'audios': registros})


def ejecutar(origen, espera):
    proyecto = Path(__file__).resolve().parents[1]
    base = proyecto/'respaldo'
    origen = origen.resolve()
    if not origen.is_relative_to(base.resolve()) or origen == base.resolve():
        raise ValueError('El corpus debe estar dentro de respaldo/.')
    firmas = validar_corpus(origen)
    from huggingface_hub import try_to_load_from_cache
    modelo = try_to_load_from_cache('Systran/faster-whisper-large-v3', 'model.bin')
    if not isinstance(modelo, str) or not Path(modelo).is_file():
        raise RuntimeError('Falta Whisper local; no se descargan pesos.')
    ollama = shutil.which('ollama')
    if not ollama:
        raise RuntimeError('No se encontró Ollama.')
    if any(G.escucha(p) for p in (11435, 11436)):
        raise RuntimeError('Un puerto de ensayo está ocupado.')
    inicial = estado_produccion()
    # Se admite servidor vivo e inactivo; nunca se detiene ni se pausa.
    validar_libre(inicial, [])
    python_inicial = G.python_pids()
    fecha = datetime.now(timezone(timedelta(hours=-3))).strftime('%Y%m%d_%H%M%S')
    raiz = base/f'comparacion_cpu_gpu_{fecha}'
    raiz.mkdir()
    (raiz/'sistema').mkdir()
    (raiz/'audios').mkdir()
    for nombre in ('fase1_transcribir.py', 'huecos.py', 'nucleo.py', 'registro.py', 'plataforma.py', 'persistencia.py', 'vocabulario.txt'):
        shutil.copy2(proyecto/nombre, raiz/'sistema'/nombre)
    shutil.copytree(proyecto/'conocimiento.ejemplo', raiz/'sistema'/'conocimiento.ejemplo')
    for nombre in firmas:
        shutil.copy2(origen/'audios'/nombre, raiz/'audios'/nombre)
    shutil.copy2(origen/'dictados.json', raiz/'dictados.json')
    shutil.copy2(Path(__file__), raiz/Path(__file__).name)
    shutil.copy2(Path(G.__file__), raiz/Path(G.__file__).name)
    config = proyecto/'configuracion.json'
    huella_config = hashlib.sha256(config.read_bytes()).hexdigest()
    guardar(raiz/'protocolo.json', {'orden': ORDEN, 'corpus_origen': str(origen), 'sha_audios': firmas,
            'produccion_inicial': inicial, 'config_sha256_antes': huella_config,
            'modelo_gemma': MODELO, 'modelo_whisper': str(Path(modelo).parent),
            'gpu': G.gpu(), 'python_inicial': sorted(python_inicial),
            'fuentes': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (raiz/'sistema').glob('*.py')},
            'nota': 'Cola inicial de cuatro, ASR sin caché. Actual: lotes 2/180 secuenciales. Paralelo: CPU precargada y Whisper residente. Tiempo desde modelos descargados; cachés de SO no vaciadas.'})
    print('CARPETA '+str(raiz), flush=True)
    limite = time.monotonic()+espera
    while True:
        validar_libre(estado_produccion(), [])
        if not G.api(11434, 'ps').get('models'):
            break
        if time.monotonic() >= limite:
            raise RuntimeError('Gemma de uso no se liberó naturalmente; no se descargó ni se inició ensayo.')
        print('ESPERA liberación natural de Gemma habitual', flush=True)
        time.sleep(15)

    def guardia():
        validar_libre(estado_produccion(), G.api(11434, 'ps').get('models'))
        if G.python_pids()-python_inicial-permitidos:
            # Admitir redirectores propios únicamente si descienden de los PID propios.
            r = subprocess.run(['powershell', '-NoProfile', '-Command',
                "Get-CimInstance Win32_Process -Filter \"Name='python.exe' OR Name='pythonw.exe'\" | Select-Object ProcessId,ParentProcessId | ConvertTo-Json -Compress"],
                capture_output=True, text=True, timeout=10, creationflags=G.SIN_VENTANA)
            r.check_returncode()
            familia = json.loads(r.stdout or '[]')
            if isinstance(familia, dict): familia = [familia]
            for _ in familia:
                for p in familia:
                    if p['ParentProcessId'] in permitidos: permitidos.add(p['ProcessId'])
            if G.python_pids()-python_inicial-permitidos:
                raise RuntimeError('Apareció otro Python; ensayo cancelado.')

    def terminar(p):
        if p is not None and p.poll() is None:
            subprocess.run(['taskkill', '/PID', str(p.pid), '/T', '/F'],
                           capture_output=True, creationflags=G.SIN_VENTANA)

    permitidos = {os.getpid()}
    pruebas = []
    daemon = proceso = None
    try:
        for numero, modo in enumerate(ORDEN, 1):
            guardia()
            puerto = 11435 if modo == 'actual' else 11436
            env = dict(os.environ, OLLAMA_HOST=f'127.0.0.1:{puerto}', HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1')
            if modo == 'paralelo':
                env.update(CUDA_VISIBLE_DEVICES='-1', HIP_VISIBLE_DEVICES='-1', GGML_VK_VISIBLE_DEVICES='-1', OLLAMA_VULKAN='0')
            with open(raiz/f'ollama_{numero}_{modo}.log', 'w', encoding='utf-8') as log, open(raiz/f'trabajador_{numero}.log', 'w', encoding='utf-8') as salida:
                daemon = subprocess.Popen([ollama, 'serve'], env=env, stdout=log, stderr=log, creationflags=G.SIN_VENTANA)
                for _ in range(60):
                    guardia()
                    if daemon.poll() is not None: raise RuntimeError('Falló el daemon de ensayo.')
                    if G.escucha(puerto): break
                    time.sleep(.5)
                else: raise RuntimeError('Timeout al iniciar daemon.')
                proceso = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), '--trabajador', str(raiz),
                    '--modo', modo, '--numero', str(numero), '--modelo', str(Path(modelo).parent)],
                    env=dict(os.environ, HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1'),
                    stdout=salida, stderr=salida, creationflags=G.SIN_VENTANA)
                permitidos.add(proceso.pid)
                print(f'INICIO ensayo={numero} modo={modo}', flush=True)
                ultimo = time.monotonic()
                while proceso.poll() is None:
                    guardia()
                    if daemon.poll() is not None: raise RuntimeError('Terminó el daemon inesperadamente.')
                    if time.monotonic()-ultimo >= 20:
                        print(f'EN CURSO ensayo={numero} modo={modo}', flush=True)
                        ultimo = time.monotonic()
                    time.sleep(1)
                if proceso.returncode: raise RuntimeError(f'Falló ensayo {numero}; revisar su log.')
                p = json.loads((raiz/f'ensayo_{numero}.json').read_text(encoding='utf-8'))
                pruebas.append(p)
                guardar(raiz/'resultados.json', {'completo': False, 'orden': ORDEN, 'pruebas': pruebas})
                print(f'FIN ensayo={numero} primero={p["primero_s"]:.2f}s total={p["total_s"]:.2f}s', flush=True)
                G.api(puerto, 'generate', {'model': MODELO, 'keep_alive': 0}, timeout=120)
                terminar(daemon)
                daemon = proceso = None
                time.sleep(2)
        agregado = resumen(pruebas)
        guardar(raiz/'resultados.json', {'completo': True, 'orden': ORDEN, 'pruebas': pruebas, 'resumen': agregado})
        print(json.dumps(agregado, ensure_ascii=False), flush=True)
    finally:
        terminar(proceso)
        terminar(daemon)
        guardar(raiz/'cierre.json', {'config_sin_cambios': hashlib.sha256(config.read_bytes()).hexdigest() == huella_config,
                'produccion_final': estado_produccion(), 'ollama_habitual_modelos': len(G.api(11434, 'ps')['models']),
                'puertos_ensayo_cerrados': not any(G.escucha(p) for p in (11435, 11436)), 'gpu_final': G.gpu()})


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--ejecutar', action='store_true')
    p.add_argument('--corpus', type=Path)
    p.add_argument('--espera', type=int, default=1200, help='Máximo de segundos para liberación natural del modelo habitual')
    p.add_argument('--trabajador', type=Path, help=argparse.SUPPRESS)
    p.add_argument('--modo', choices=['actual', 'paralelo'], help=argparse.SUPPRESS)
    p.add_argument('--numero', type=int, help=argparse.SUPPRESS)
    p.add_argument('--modelo', help=argparse.SUPPRESS)
    a = p.parse_args()
    if a.trabajador:
        trabajador(a.trabajador, a.modo, a.numero, a.modelo)
    elif a.ejecutar:
        if not a.corpus: p.error('Falta --corpus con el ensayo sintético previo.')
        ejecutar(a.corpus, a.espera)
    else:
        p.print_help()
