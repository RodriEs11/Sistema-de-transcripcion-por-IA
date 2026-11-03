"""Prepara respaldos y artefactos; nunca publica, reinicia, migra o modifica datos de origen."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import time
import urllib.request

SIN_VENTANA = getattr(subprocess, 'CREATE_NO_WINDOW', 0)


def acl_protegida(ruta):
    """Consultar el descriptor de Windows sin cargar módulos de PowerShell."""
    import ctypes
    from ctypes import wintypes as W
    api=ctypes.WinDLL('advapi32',use_last_error=True)
    api.GetFileSecurityW.argtypes=[W.LPCWSTR,W.DWORD,W.LPVOID,W.DWORD,ctypes.POINTER(W.DWORD)]
    api.GetFileSecurityW.restype=W.BOOL
    api.GetSecurityDescriptorControl.argtypes=[W.LPVOID,ctypes.POINTER(W.WORD),ctypes.POINTER(W.DWORD)]
    api.GetSecurityDescriptorControl.restype=W.BOOL
    longitud=W.DWORD();api.GetFileSecurityW(str(ruta),4,None,0,ctypes.byref(longitud))
    if not longitud.value:raise OSError('No se pudo consultar la protección del destino')
    descriptor=ctypes.create_string_buffer(longitud.value)
    if not api.GetFileSecurityW(str(ruta),4,descriptor,len(descriptor),ctypes.byref(longitud)):raise OSError('No se pudo leer la ACL')
    control=W.WORD();revision=W.DWORD()
    if not api.GetSecurityDescriptorControl(descriptor,ctypes.byref(control),ctypes.byref(revision)):raise OSError('Descriptor no verificable')
    return bool(control.value & 0x1000)


def guardar(ruta, datos):
    Path(ruta).write_text(json.dumps(datos, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


def sha(ruta):
    h = hashlib.sha256()
    with Path(ruta).open('rb') as f:
        for bloque in iter(lambda: f.read(1024*1024), b''): h.update(bloque)
    return h.hexdigest()


def copiar_verificado(origen, destino):
    origen, destino = Path(origen), Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    if origen.is_symlink() or origen.is_junction(): raise ValueError('No se sigue un enlace durante el respaldo')
    for _ in range(3):
        antes = origen.stat()
        shutil.copy2(origen, destino)
        huella = sha(destino)
        despues = origen.stat()
        if ((antes.st_size, antes.st_mtime_ns) == (despues.st_size, despues.st_mtime_ns)
                and huella == sha(origen)):
            return {'bytes': destino.stat().st_size, 'sha256': huella, 'metodo': 'copia_verificada'}
    raise RuntimeError('El origen siguió cambiando; no se confirma el respaldo')


def copiar_sqlite(origen, destino):
    destino.parent.mkdir(parents=True, exist_ok=True)
    fuente = sqlite3.connect(Path(origen).resolve().as_uri()+'?mode=ro', uri=True, timeout=5)
    copia = None
    try:
        copia = sqlite3.connect(destino)
        fuente.backup(copia)
        if copia.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('La copia SQLite no pasó integridad')
    finally:
        if copia is not None: copia.close()
        fuente.close()
    return {'bytes': destino.stat().st_size, 'sha256': sha(destino), 'metodo': 'sqlite_backup'}


def respaldar_arbol(origen, destino):
    origen, destino = Path(origen), Path(destino)
    inventario = {}
    if not origen.exists(): return inventario
    for carpeta, directorios, archivos in os.walk(origen, followlinks=False):
        if any((Path(carpeta)/d).is_symlink() or (Path(carpeta)/d).is_junction() for d in directorios):
            raise ValueError('Hay un directorio enlazado: requiere revisar la cobertura')
        for nombre in archivos:
            f = Path(carpeta)/nombre
            # Los journals pertenecen al snapshot obtenido por backup API, no se copian como si fueran datos independientes.
            if any(nombre.endswith(s) and (f.with_name(nombre[:-len(s)])).suffix in ('.sqlite3','.db') for s in ('-wal','-shm','-journal')):
                continue
            rel = f.relative_to(origen)
            dest = destino/rel
            if f.suffix in ('.sqlite3','.db'):
                with f.open('rb') as lector: cabecera=lector.read(16)
                if cabecera == b'SQLite format 3\0':
                    dato = copiar_sqlite(f,dest)
                else:
                    dato = copiar_verificado(f,dest)
                    dato['requiere_revision_sqlite'] = True
            else: dato = copiar_verificado(f,dest)
            inventario[str(rel)] = dato
    return inventario


def leer_json(ruta):
    return json.loads(Path(ruta).read_text(encoding='utf-8-sig'))


def estado_en_vivo(puerto=8765):
    try:
        with urllib.request.urlopen(f'http://127.0.0.1:{puerto}/api/admin/estado',timeout=3) as r: d=json.load(r)
        if not isinstance(d,dict) or not isinstance(d.get('cola',{}).get('items'),list) or not isinstance(d.get('abiertos'),list):
            raise ValueError('Estado incompleto')
        filas=d['cola']['items']
        return {'verificado':True, 'version':d.get('servidor',{}).get('version'),
                'simulado':d.get('servidor',{}).get('simulado'),
                'pendientes':len(filas),'pausas':sum(x.get('estado')=='en pausa' or x.get('pausa_pedida',False) for x in filas),
                'abiertos':len(d['abiertos']), 'en_proceso':d.get('casos',{}).get('en_proceso'),
                'capturado':time.time()}
    except Exception:
        return {'verificado':False, 'pendientes':None,'pausas':None,'abiertos':None,'en_proceso':None,'capturado':time.time()}


def auditar(raiz, cliente_local, piloto, puerto=8765):
    # No importar servidor/informe/nucleo: sus imports crean carpetas o preparan conocimiento.
    import borradores as B
    raiz, cliente_local = Path(raiz), Path(cliente_local)
    cfg=leer_json(raiz/'configuracion.json')
    audios=(raiz/Path(cfg['carpeta_audios_nuevos'])).resolve()
    informes=(raiz/Path(cfg['carpeta_informes'])).resolve();datos=informes/'revision'/'datos'
    nombres={p.name[:-len('.borrador.json')] for p in datos.glob('*.borrador.json')}
    nombres.update(p.name[:-len('.borrador.html')] for p in datos.glob('*.borrador.html'))
    borradores={'json':len(list(datos.glob('*.borrador.json'))),'html':len(list(datos.glob('*.borrador.html'))),'invalidos':0}
    for nombre in nombres:
        try: B.leer(datos,nombre)
        except Exception: borradores['invalidos']+=1
    pendientes=cliente_local/'pendientes'
    local={'audios':len(list(pendientes.glob('*.audio'))),'temporales':len(list(pendientes.glob('*.audio.pendiente'))),
           'recuperacion':sum(p.is_file() for p in (pendientes/'recuperacion').rglob('*'))}
    c=leer_json(cliente_local/'config.json') if (cliente_local/'config.json').exists() else {}
    local['corresponde_al_piloto']=str(c.get('pc','')).lower()==piloto.lower()
    acceso=leer_json(raiz/'acceso_remoto.json') if (raiz/'acceso_remoto.json').exists() else {}
    pcs={x.get('pc') for x in acceso.get('clientes',{}).values() if x.get('pc')}
    actual=estado_en_vivo(puerto)
    cola={'sqlite_existe':(datos.parent/'cola_procesamiento.sqlite3').exists(),
          'legacy_existe':(datos.parent/'cola_al_reiniciar.json').exists(), 'estados':None, 'legacy_pendientes':None}
    if cola['legacy_existe']:
        d=leer_json(datos.parent/'cola_al_reiniciar.json')
        cola['legacy_pendientes']=len(d['nombres']) if isinstance(d.get('nombres'),list) else None
    if cola['sqlite_existe']:
        db=sqlite3.connect((datos.parent/'cola_procesamiento.sqlite3').as_uri()+'?mode=ro',uri=True,timeout=5)
        try:
            if db.execute('PRAGMA user_version').fetchone()[0]!=1: raise ValueError('Esquema de cola desconocido')
            cola['estados']=dict(db.execute('SELECT estado,count(*) FROM tareas GROUP BY estado'))
            cola['pausados']=db.execute('SELECT count(*) FROM tareas WHERE pausado=1 AND estado NOT IN (\'listo\',\'cancelado\')').fetchone()[0]
        finally:db.close()
    aprendizaje=sum(1 for _ in (datos/'_aprendizaje').glob('*.json'))
    bloqueos=['Confirmar captura, colas cifradas y cierre de estudios en cada PC; incluye pc-test.']
    if not actual['verificado']:bloqueos.append('Servidor local sin estado verificable: no se confirman cola, pausas ni ediciones en memoria.')
    if actual['verificado'] and (actual['pendientes'] or actual['abiertos'] or actual['en_proceso'] or actual['simulado'] is not False):
        bloqueos.append('La ventana del servidor no está libre o no es verificable como producción.')
    if borradores['invalidos']:bloqueos.append('Resolver borradores inválidos preservando originales.')
    if any(local[x] for x in ('audios','temporales','recuperacion')):bloqueos.append('Resolver y confirmar la cola cifrada local antes de actualizar.')
    if aprendizaje:bloqueos.append('Drenar aprendizaje antes de un rollback completo.')
    return {'fecha':time.strftime('%Y-%m-%d %H:%M:%S%z'), 'piloto':piloto,'piloto_registrado':piloto.lower() in {p.lower() for p in pcs},
            'pcs_registradas':len(pcs),'servidor':actual,'borradores':borradores,'cola_servidor':cola,'cola_local':local,
            'aprendizaje_pendiente':aprendizaje,'bloqueos':bloqueos,'activacion_autorizada':False}, audios, informes


def version_exe(ruta):
    datos=Path(ruta).read_bytes();marca='FileVersion'.encode('utf-16-le')+b'\0\0';i=datos.find(marca)
    if i<0:return None
    i+=len(marca)
    while datos[i:i+2]==b'\0\0':i+=2
    fin=i
    while datos[fin:fin+2]!=b'\0\0' and fin-i<64:fin+=2
    v=datos[i:fin].decode('utf-16-le').split('.')
    while len(v)>2 and v[-1]=='0':v.pop()
    return '.'.join(v)


def cliente_publico(origen,destino,exe):
    origen, destino = Path(origen),Path(destino)
    for f in origen.rglob('*'):
        if not f.is_file():continue
        rel=f.relative_to(origen)
        if f.suffix.lower()=='.dll' or str(rel) in ('LEEME.txt','Transcripcion.exe.config'):
            copiar_verificado(f,destino/rel)
    copiar_verificado(exe,destino/'Transcripcion.exe')


def version_codigo(raiz):
    import re
    m=re.search(r'public const string VERSION = "([0-9.]+)";',(Path(raiz)/'cliente_codigo'/'Programa.cs').read_text(encoding='utf-8-sig'))
    if not m:raise ValueError('No se encontró Programa.VERSION')
    return m.group(1)


def version_servidor(texto):
    import re
    m=re.search(r'^VERSION = "([0-9.]+)"',texto,re.MULTILINE)
    return m.group(1) if m else '?'


def preparar(raiz,salida,candidato,cliente_local,piloto):
    raiz,salida=Path(raiz).resolve(),Path(salida).resolve()
    if not salida.is_relative_to(raiz/'respaldo') or not salida.is_dir() or any(salida.iterdir()):
        raise ValueError('Usar una carpeta nueva y vacía bajo respaldo, con ACL privada ya aplicada')
    if os.name=='nt':
        if not acl_protegida(salida):raise ValueError('Falta proteger los permisos del destino')
    privado=salida/'privado';privado.mkdir()
    estado,audios,informes=auditar(raiz,cliente_local,piloto)
    guardar(salida/'estado_previo.json',estado)
    inventario={}
    grupos={'audios':audios,'informes':informes,'cliente_local':Path(cliente_local),'cliente_distribuido':raiz/'cliente'}
    grupos.update({k:raiz/k for k in ('conocimiento','ejemplos','referencias','voces','resultados','registros')})
    for nombre,origen in grupos.items():
        inventario[nombre]={'origen':str(origen),'archivos':respaldar_arbol(origen,privado/nombre)}
        print(f'Respaldo {nombre}: {len(inventario[nombre]["archivos"])} archivos verificados',flush=True)
    # usuarios.json: transcriptores y sus contraseñas (PBKDF2); sesiones.json: sesiones abiertas (por huella)
    for nombre in ('configuracion.json','acceso_remoto.json','usuarios.json','sesiones.json'):
        if (raiz/nombre).exists():inventario[nombre]={'archivos':{nombre:copiar_verificado(raiz/nombre,privado/nombre)}}
    guardar(privado/'inventario.json',inventario)
    # Fuentes declaradas por Git, incluidos cambios no publicados; no copiar el workspace completo.
    r=subprocess.run(['git','ls-files','--cached','--others','--exclude-standard'],cwd=raiz,capture_output=True,text=True,check=True,creationflags=SIN_VENTANA)
    actual=salida/'entrega'/'candidato'/'sistema';actual.mkdir(parents=True)
    for nombre in r.stdout.splitlines():
        p=Path(nombre)
        if p.is_absolute() or '..' in p.parts:raise ValueError('Ruta Git inválida')
        if p.parts[0] in ('respaldo','conocimiento','ejemplos','referencias','resultados','registros','voces','.venv'):raise ValueError('Datos privados en lista de fuentes')
        if (raiz/p).is_file():copiar_verificado(raiz/p,actual/p)
    cliente_publico(raiz/'cliente',actual/'cliente',candidato)
    app=version_codigo(raiz)
    if version_exe(actual/'cliente'/'Transcripcion.exe')!=app:raise ValueError(f'Candidato distinto de App {app}')
    previo=salida/'entrega'/'rollback'/'sistema';previo.mkdir(parents=True)
    import io,tarfile
    archivado=subprocess.run(['git','archive','HEAD'],cwd=raiz,capture_output=True,check=True,creationflags=SIN_VENTANA)
    with tarfile.open(fileobj=io.BytesIO(archivado.stdout)) as t:
        for miembro in t:
            p=Path(miembro.name)
            if not miembro.isfile():continue
            if p.is_absolute() or '..' in p.parts:raise ValueError('Ruta de archivo inválida')
            destino=previo/p;destino.parent.mkdir(parents=True,exist_ok=True)
            with t.extractfile(miembro) as lector:destino.write_bytes(lector.read())
    cliente_publico(raiz/'cliente',previo/'cliente',raiz/'cliente'/'Transcripcion.exe')
    # LEEME de rollback debe corresponder al código anterior, no al candidato en el workspace.
    anterior=subprocess.run(['git','show','HEAD:cliente/LEEME.txt'],cwd=raiz,capture_output=True,check=True,creationflags=SIN_VENTANA)
    (previo/'cliente'/'LEEME.txt').write_bytes(anterior.stdout)
    anterior_app=version_exe(previo/'cliente'/'Transcripcion.exe')
    if not anterior_app or anterior_app==app:raise ValueError(f'El rollback no contiene una App anterior a la {app}')
    anterior_srv=subprocess.run(['git','show','HEAD:servidor.py'],cwd=raiz,capture_output=True,text=True,check=True,creationflags=SIN_VENTANA).stdout
    cabecera=subprocess.run(['git','rev-parse','HEAD'],cwd=raiz,capture_output=True,text=True,check=True,creationflags=SIN_VENTANA).stdout.strip()
    guardar(salida/'entrega'/'procedencia.json',{'commit_base':cabecera,'fuentes_con_cambios_sin_commit':True,'candidato':f'{app} / {version_servidor((raiz/"servidor.py").read_text(encoding="utf-8"))}',
            'rollback':f'{anterior_app} / {version_servidor(anterior_srv)}','piloto':piloto})
    manifiesto={f.relative_to(salida/'entrega').as_posix():sha(f) for f in (salida/'entrega').rglob('*') if f.is_file()}
    guardar(salida/'manifiesto_entrega.json',manifiesto)
    guardar(salida/'estado_final.json',auditar(raiz,cliente_local,piloto)[0])
    guardar(salida/'resumen_respaldo.json',{'archivos':sum(len(x['archivos']) for x in inventario.values()),
            'bytes':sum(a['bytes'] for x in inventario.values() for a in x['archivos'].values()),
            'sqlite_verificados':sum(a['metodo']=='sqlite_backup' for x in inventario.values() for a in x['archivos'].values()),
            'revisar_bases':sum(a.get('requiere_revision_sqlite',False) for x in inventario.values() for a in x['archivos'].values()),
            'instantanea_global_transaccional':False})


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--preparar',action='store_true');p.add_argument('--salida',type=Path)
    p.add_argument('--candidato',type=Path);p.add_argument('--cliente-local',type=Path);p.add_argument('--piloto',default='pc-test')
    a=p.parse_args()
    if not a.preparar:p.print_help()
    else:
        if not all((a.salida,a.candidato,a.cliente_local)):p.error('Faltan salida, candidato o cliente local')
        try:preparar(Path(__file__).parent,a.salida,a.candidato,a.cliente_local,a.piloto)
        except Exception as ex:
            if a.salida.resolve().is_relative_to(Path(__file__).resolve().parent/'respaldo') and a.salida.is_dir():
                guardar(a.salida/'preparacion_fallida.json',{'tipo':type(ex).__name__,'completa':False})
            p.exit(1,'Preparación incompleta; revisar archivos privados. No se activó la entrega.\n')
        print(f'Preparación guardada en {a.salida.resolve()}; activación bloqueada hasta completar la ventana.')
