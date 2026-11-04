"""Mide escrituras indexadas sintéticas. No importa servidor ni accede a datos de la instalación."""
from pathlib import Path
import json
import statistics
import sys
import tempfile
import time
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from transcripcion.aprendizaje import almacen as AL


def main():
    respaldo = Path(__file__).resolve().parents[1]/'respaldo'
    respaldo.mkdir(exist_ok=True)
    resultados = []
    with tempfile.TemporaryDirectory(prefix='indice_aprendizaje_',dir=respaldo) as tmp:
        for cantidad in [100,1000,10000]:
            hist=Path(tmp)/f'historial_{cantidad}.csv'
            with AL.abrir(hist) as c:
                for i in range(cantidad):
                    c.execute('INSERT INTO historial VALUES (?,?,?,?,?)',('2026-10-29',str(i),'2026-10-29 12:00',100,'5.0'))
                    AL.actualizar_ejemplo(c,str(i),'inicial',lambda i=i:[('replace',f'errado{i}','corregido')])
            muestras=[]
            for i in range(7):
                inicio=time.perf_counter()
                with AL.abrir(hist) as c:
                    c.execute('UPDATE historial SET palabras=? WHERE dia=? AND informe=?',(101+i,'2026-10-29','0'))
                    AL.actualizar_ejemplo(c,'0',str(i),lambda:[('replace','texto','nuevo')])
                    c.execute('SELECT op,de,a,n FROM frecuencias WHERE n>=2 ORDER BY n DESC,op DESC,de DESC,a DESC LIMIT 40').fetchall()
                muestras.append((time.perf_counter()-inicio)*1000)
            resultados.append({'informes':cantidad,'mediana_ms':round(statistics.median(muestras),2),'max_ms':round(max(muestras),2)})
    print(json.dumps(resultados,indent=2))


if __name__=='__main__':
    main()
