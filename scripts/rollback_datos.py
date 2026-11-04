"""Preparar compatibilidad de datos en una copia nueva; nunca restaurar sobre producción."""
import argparse
import csv
import json
import os
from pathlib import Path
import shutil
import sqlite3
from contextlib import closing
from transcripcion.casos import borradores as B


def preparar(origen, salida):
    origen, salida = Path(origen).resolve(), Path(salida).resolve()
    if salida == origen or salida.is_relative_to(origen) or origen.is_relative_to(salida):
        raise ValueError('La salida debe ser una copia separada del origen')
    if salida.exists(): raise FileExistsError('La salida ya existe; no se sobrescribe')
    if origen.is_symlink() or origen.is_junction(): raise ValueError('No convertir un origen enlazado')
    for carpeta, directorios, archivos in os.walk(origen,followlinks=False):
        if any((Path(carpeta)/n).is_symlink() or (Path(carpeta)/n).is_junction() for n in directorios+archivos):
            raise ValueError('La copia de recuperación no debe contener enlaces')
    datos = origen/'informes'/'revision'/'datos'
    if not datos.is_dir(): raise ValueError('Falta el árbol de respaldo informes/revision/datos')
    pendientes=datos/'_aprendizaje'
    if list(pendientes.glob('*.json')) or (pendientes/'_recalcular').exists():
        raise ValueError('Primero drenar aprendizaje con el servidor nuevo o conservarlo; no degradar con trabajo pendiente')
    cola=datos.parent/'cola_procesamiento.sqlite3'
    if cola.exists():
        with closing(sqlite3.connect(cola.as_uri()+'?mode=ro',uri=True)) as db:
            if db.execute('PRAGMA user_version').fetchone()[0]!=1: raise ValueError('Cola desconocida')
            if db.execute("SELECT count(*) FROM tareas WHERE estado NOT IN ('listo','cancelado')").fetchone()[0]:
                raise ValueError('No degradar con tareas, pausas, errores o borrados por resolver')
    # Validar todo antes de copiar o convertir. No sustituir datos corruptos por defaults.
    borradores={f.name[:-len('.borrador.json')]:B.leer(datos,f.name[:-len('.borrador.json')]) for f in datos.glob('*.borrador.json')}
    historial=origen/'resultados'/'historial.sqlite3'
    filas=procesados=None
    if historial.exists():
        with closing(sqlite3.connect(historial.as_uri()+'?mode=ro',uri=True)) as db:
            if db.execute('PRAGMA user_version').fetchone()[0]!=1: raise ValueError('Historial desconocido')
            db.row_factory=sqlite3.Row
            filas=[dict(r) for r in db.execute('SELECT fecha,informe,palabras,porcentaje_corregido FROM historial ORDER BY fecha,informe')]
            procesados={r['ruta']:{'mtime':r['mtime'],'ejemplo':r['ejemplo']} for r in db.execute('SELECT ruta,mtime,ejemplo FROM procesados')}
    shutil.copytree(origen,salida,symlinks=True)
    destino=salida/'informes'/'revision'/'datos'
    originales=salida/'formatos_nuevos_conservados';originales.mkdir()
    for n,d in borradores.items():
        (destino/(n+'.borrador.html')).write_text(d['html'],encoding='utf-8')
        (destino/(n+'.omisiones_ok.json')).write_text(json.dumps(d['omisiones_ok'],ensure_ascii=False),encoding='utf-8')
        (destino/(n+'.borrador.json')).replace(originales/(n+'.borrador.json'))
    if filas is not None:
        with (salida/'resultados'/'historial.csv').open('w',encoding='utf-8-sig',newline='') as f:
            w=csv.DictWriter(f,fieldnames=['fecha','informe','palabras','porcentaje_corregido'],delimiter=';');w.writeheader();w.writerows(filas)
        (salida/'ejemplos').mkdir(exist_ok=True)
        (salida/'ejemplos'/'_procesados.json').write_text(json.dumps(procesados,ensure_ascii=False),encoding='utf-8')
        # El programa anterior ignora SQLite; apartarlo evita reutilizar luego un índice desactualizado.
        (salida/'resultados'/'historial.sqlite3').replace(originales/'historial.sqlite3')
    resultado={'borradores_convertidos':len(borradores),'historial_exportado':filas is not None,
               'historial_filas':len(filas or []),'solo_copia':True,'restaurado_en_produccion':False}
    (salida/'compatibilidad.json').write_text(json.dumps(resultado,indent=2),encoding='utf-8')
    return resultado


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--origen',type=Path,required=True);p.add_argument('--salida',type=Path,required=True)
    a=p.parse_args()
    try:r=preparar(a.origen,a.salida)
    except Exception as ex:p.exit(1,f'No se preparó la compatibilidad ({type(ex).__name__}); no se restauró producción.\n')
    print(json.dumps(r))
