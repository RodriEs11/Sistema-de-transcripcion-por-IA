// Prueba funcional del panel contra la API real en modo simulado y catálogo ficticio.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const {spawn}=require('node:child_process');
const path=require('node:path'),fs=require('node:fs'),assert=require('node:assert/strict');
const raiz=path.resolve(__dirname,'..');
const python=process.env.PYTHON || path.join(raiz,'.venv',process.platform==='win32'?'Scripts/python.exe':'bin/python');
const codigo=`
import sys, tempfile, threading
from pathlib import Path
from unittest.mock import patch
import servidor as S
from transcripcion import ajustes
from transcripcion.conocimiento import medicos as MED
with tempfile.TemporaryDirectory(prefix='ui_medicos_', dir='respaldo') as carpeta:
    aj = ajustes.para_pruebas(Path(carpeta)); ajustes.preparar_carpetas(aj); S.configurar(aj)
    conoc = Path(carpeta) / 'conocimiento'
    with patch.object(S.CON, 'CONOC', conoc), patch.object(MED, 'DIR_MED', conoc / 'medicos'):
        S.CON.preparar_conocimiento()
        http = S.ThreadingHTTPServer(('127.0.0.1', 0), S.H)
        S.SIS.puerto = http.server_port
        hilo = threading.Thread(target=http.serve_forever, daemon=True)
        hilo.start()
        sys.stdout.write(str(S.SIS.puerto) + '\\n'); sys.stdout.flush()
        sys.stdin.readline()
        http.shutdown(); http.server_close(); hilo.join()
`;
(async()=>{
  const hijo=spawn(python,['-u','-c',codigo],{cwd:raiz,env:{...process.env,SIMULAR_IA:'1'},windowsHide:true,stdio:['pipe','pipe','pipe']});
  let diagnostico=''; hijo.stderr.on('data',d=>diagnostico+=d);
  let browser;
  try{
    const puerto=await new Promise((resolve,reject)=>{
      const temporizador=setTimeout(()=>reject(new Error('El servidor de prueba no inició. '+diagnostico)),15000);
      hijo.once('error',reject);
      hijo.once('exit',c=>{clearTimeout(temporizador); reject(new Error('Servidor finalizó: '+c+' '+diagnostico));});
      hijo.stdout.once('data',d=>{clearTimeout(temporizador); resolve(Number(d.toString().trim()));});
    });
    const url=`http://127.0.0.1:${puerto}`;
    browser=await chromium.launch({channel:process.env.BROWSER_CHANNEL||'msedge',headless:true});
    const page=await browser.newPage({viewport:{width:1440,height:1100}}), errores=[];
    page.on('pageerror',e=>errores.push(e.message));
    await page.goto(url+'/admin/medicos');
    await page.getByText('Todavía no hay médicos.',{exact:false}).waitFor();
    await page.getByRole('button',{name:'Agregar médico',exact:true}).click();
    await page.getByLabel('Nombre del médico',{exact:true}).fill('Dra. Pérez');
    await page.getByLabel('Notas para la IA').fill('Nota ficticia <script>alert(1)</script>');
    await page.getByRole('button',{name:'Guardar',exact:true}).click();
    await page.getByText('Médico guardado.',{exact:true}).waitFor();
    assert.equal(await page.locator('#lista tr').count(),1);
    await page.getByRole('button',{name:'Agregar médico',exact:true}).click();
    await page.getByLabel('Nombre del médico',{exact:true}).fill('  DRA.   PEREZ  ');
    await page.getByRole('button',{name:'Guardar',exact:true}).click();
    await page.getByText('Ya existe un médico con ese nombre.',{exact:true}).waitFor();
    await page.getByRole('button',{name:'Cancelar',exact:true}).click();
    await page.getByRole('button',{name:'Modificar',exact:true}).click();
    assert.equal(await page.getByLabel('Notas para la IA').inputValue(),'Nota ficticia <script>alert(1)</script>');
    await page.getByLabel('Nombre del médico',{exact:true}).fill('Dra. Ensayo');
    await page.getByLabel('Notas para la IA').fill('Notas modificadas de prueba.');
    await page.getByRole('button',{name:'Guardar',exact:true}).click();
    await page.getByText('Médico guardado.',{exact:true}).waitFor();
    await page.reload();
    await page.getByRole('cell',{name:'Dra. Ensayo',exact:true}).waitFor();
    // El servidor también impide duplicados que no estaban en una lista desactualizada.
    await page.request.post(url+'/api/admin/medicos/agregar',{headers:{'X-Panel':'1'},data:{nombre:'Dr. Simulado',notas:''}});
    await page.getByRole('button',{name:'Agregar médico',exact:true}).click();
    await page.getByLabel('Nombre del médico',{exact:true}).fill('DR. SIMULADO');
    await page.getByRole('button',{name:'Guardar',exact:true}).click();
    await page.getByText('Ya existe un médico con ese nombre: Dr. Simulado.',{exact:true}).waitFor();
    await page.getByRole('button',{name:'Cancelar',exact:true}).click();
    await page.getByRole('button',{name:'Actualizar',exact:true}).click();
    await page.getByText('Listado actualizado.',{exact:true}).waitFor();
    const captura=path.join(raiz,'respaldo','medicos-panel-claro.png');
    await page.screenshot({path:captura,fullPage:true});
    await page.getByRole('button',{name:'Cambiar entre modo claro y oscuro'}).click();
    await page.setViewportSize({width:390,height:844});
    await page.screenshot({path:path.join(raiz,'respaldo','medicos-panel-movil.png'),fullPage:true});
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
    page.once('dialog',d=>d.dismiss());
    await page.locator('#lista tr').filter({hasText:'Dra. Ensayo'}).getByRole('button',{name:'Eliminar',exact:true}).click();
    assert.equal(await page.locator('#lista tr').count(),2);
    page.once('dialog',d=>d.accept());
    await page.locator('#lista tr').filter({hasText:'Dra. Ensayo'}).getByRole('button',{name:'Eliminar',exact:true}).click();
    await page.getByText('Médico eliminado.',{exact:true}).waitFor();
    assert.equal(await page.locator('#lista tr').count(),1);
    assert.deepEqual(errores,[]);
    process.stdout.write('Panel de médicos: CRUD, duplicados, persistencia, escape de HTML, confirmación, tema y móvil OK.\n');
  }finally{
    if(browser) await browser.close();
    hijo.stdin.end('\n');
    await new Promise(r=>{if(hijo.exitCode!==null)return r();hijo.once('exit',r);});
  }
})().catch(e=>{process.stderr.write(e.stack+'\n');process.exitCode=1;});
