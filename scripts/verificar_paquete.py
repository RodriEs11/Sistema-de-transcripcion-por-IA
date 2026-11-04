"""Verifica integridad del paquete preparado; no publica ni interpreta datos privados."""
import argparse
import json
from pathlib import Path
from preparar_activacion import sha


def verificar(paquete):
    paquete=Path(paquete).resolve();base=paquete/'entrega'
    esperado=json.loads((paquete/'manifiesto_entrega.json').read_text(encoding='utf-8'))
    if not esperado or not isinstance(esperado,dict):raise ValueError('Manifiesto vacío o inválido')
    actuales={p.relative_to(base).as_posix() for p in base.rglob('*') if p.is_file()}
    if actuales != set(esperado):raise ValueError('Cambió la lista de archivos de la entrega')
    for nombre,huella in esperado.items():
        f=(base/nombre).resolve()
        if not f.is_relative_to(base) or (base/nombre).is_symlink():raise ValueError('Ruta fuera de la entrega')
        if f.name in ('configuracion.json','acceso_remoto.json','conexion.json','usuarios.json','sesiones.json') or f.suffix in ('.wav','.docx','.sqlite3'):
            raise ValueError('Hay datos privados en el conjunto publicable')
        if sha(f)!=huella:raise ValueError('Cambió el contenido de la entrega')
    return {'integridad':'ok','archivos':len(esperado),'autoriza_activar':False}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('paquete',type=Path);a=p.parse_args()
    try:r=verificar(a.paquete)
    except Exception as ex:p.exit(1,f'Paquete no verificado ({type(ex).__name__}). No publicar.\n')
    print(json.dumps(r))
