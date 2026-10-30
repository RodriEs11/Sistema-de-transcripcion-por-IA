"""Resume una campaña completa de validar_gpu_real.py; no carga modelos ni usa red."""
import argparse
import json
import math
from pathlib import Path
import statistics

ORDEN = [1, 2, 4, 4, 2, 1, 2, 4, 1]


def resumir(datos):
    pruebas = datos.get('pruebas', [])
    if datos.get('completo') is not True or datos.get('orden') != ORDEN or len(pruebas) != len(ORDEN):
        raise ValueError('Se requieren los nueve ensayos completos del protocolo 1/2/4.')
    for numero, (p, lote) in enumerate(zip(pruebas, ORDEN), 1):
        if p['ensayo'] != numero or p['lote'] != lote or [a['audio'] for a in p['audios']] != [1, 2, 3, 4]:
            raise ValueError('Orden o cantidad de audios inválidos.')
        tiempos = [a['listo_s'] for a in p['audios']]
        valores = [p['total_s'], p['primero_s'], p['espera_media_s'], p['ultimo_s'], p['informes_min'], *tiempos]
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v <= 0 for v in valores):
            raise ValueError('Los tiempos y tasas deben ser finitos y positivos.')
        if tiempos != sorted(tiempos) or tiempos[-1] > p['total_s']:
            raise ValueError('Cronología de informes inválida.')
        esperado = [tiempos[0], statistics.mean(tiempos), tiempos[-1], 240/p['total_s']]
        if any(not math.isclose(v, e, rel_tol=1e-6) for v, e in zip(valores[1:5], esperado)):
            raise ValueError('Los agregados del ensayo no coinciden con sus audios.')
    resumen = {'ensayos': len(pruebas), 'informes': sum(len(p['audios']) for p in pruebas),
               'nota': 'Medianas de tres ensayos por lote; esperas desde una cola inicial de cuatro audios.', 'lotes': {}}
    for lote in (1, 2, 4):
        grupo = [p for p in pruebas if p['lote'] == lote]
        mediana = lambda clave: statistics.median(p[clave] for p in grupo)
        agregados = {clave: mediana(clave) for clave in ('total_s', 'primero_s', 'espera_media_s', 'ultimo_s', 'informes_min')}
        agregados['rango_total_s'] = [min(p['total_s'] for p in grupo), max(p['total_s'] for p in grupo)]
        agregados['asr_s'] = statistics.median(sum(a['asr_s'] for a in p['audios']) for p in grupo)
        agregados['cargas_whisper_s'] = statistics.median(sum(p['cargas_whisper_s']) for p in grupo)
        agregados['cargas_ia_s'] = statistics.median(sum(a['metricas'].get('load_duration_s', 0) for a in p['audios']) for p in grupo)
        audios = [a for p in grupo for a in p['audios']]
        evaluacion = sum(a['metricas'].get('eval_duration_s', 0) for a in audios)
        agregados['tokens_s'] = sum(a['metricas'].get('eval_count', 0) for a in audios)/evaluacion if evaluacion else None
        resumen['lotes'][str(lote)] = agregados
    return resumen


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('resultados', type=Path)
    parser.add_argument('--salida', type=Path, help='Guardar también el agregado JSON en UTF-8')
    args = parser.parse_args()
    if args.salida and args.salida.resolve() == args.resultados.resolve():
        parser.error('La salida no puede reemplazar los resultados individuales.')
    texto = json.dumps(resumir(json.loads(args.resultados.read_text(encoding='utf-8'))), ensure_ascii=False, indent=2)
    if args.salida: args.salida.write_text(texto+'\n', encoding='utf-8')
    print(texto)
