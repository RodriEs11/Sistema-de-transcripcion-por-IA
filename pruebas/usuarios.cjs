// Prueba funcional de transcriptores con estilo propio contra el servidor real en modo simulado.
// Datos ficticios en una carpeta temporal dentro de respaldo/: entrar, contraseña inicial, plantillas «solo para mí»,
// notas propias de un médico, formato del Word y aviso de informe armado con el estilo de otro.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const {spawn}=require('node:child_process');
const path=require('node:path'),assert=require('node:assert/strict');
const raiz=path.resolve(__dirname,'..');
const python=process.env.PYTHON || path.join(raiz,'.venv',process.platform==='win32'?'Scripts/python.exe':'bin/python');
const codigo=`
import json, sys, tempfile, threading
from pathlib import Path
from unittest.mock import patch
import servidor as S, nucleo as N, usuarios as U, remoto as R
Path('respaldo').mkdir(exist_ok=True)
with tempfile.TemporaryDirectory(prefix='ui_usuarios_', dir='respaldo') as c:
    c = Path(c); conoc = c / 'conocimiento'; datos = c / 'Informes' / 'revision' / 'datos'
    datos.mkdir(parents=True); (c / 'Audios_nuevos').mkdir(); conoc.mkdir()
    (conoc / 'plantillas.md').write_text('# x\\n\\n## MAMOGRAFÍA\\nTITULO: MAMOGRAFÍA\\n- Mamas de densidad tipo B.\\n', encoding='utf-8')
    (conoc / 'reglas_dictado.md').write_text('- Regla ficticia.\\n', encoding='utf-8')
    n = 'Servidor_20261102-120000_ficticio'
    (datos / f'{n}.json').write_text(json.dumps({'texto': 'mamografía densidad b', 'palabras': []}), encoding='utf-8')
    (datos / f'{n}.dictado.txt').write_text('mamografía densidad b', encoding='utf-8')
    (datos / f'{n}.informe_ia.txt').write_text('MAMOGRAFÍA\\n\\n-Mamas de densidad tipo B.\\n\\nLo saluda atte.\\n', encoding='utf-8')
    (datos / f'{n}.estilo.txt').write_text('beto', encoding='utf-8')
    with patch.object(N, 'CONOC', conoc), patch.object(N, 'DIR_MED', conoc / 'medicos'), \\
         patch.object(U, 'ARCH', c / 'usuarios.json'), patch.object(U, 'CARPETA', conoc / 'usuarios'), \\
         patch.object(R, 'ARCH_SESIONES', c / 'sesiones.json'), patch.object(S, 'DATOS', datos), \\
         patch.object(S, 'NUEVOS', c / 'Audios_nuevos'), patch.object(S, 'INFORMES', c / 'Informes'):
        U.crear('Ana Prueba', 'inicial1'); U.crear('Beto', 'inicial2')
        N.guardar_medico('Dr. Ficticio', 'Notas generales.', crear=True)
        http = S.ThreadingHTTPServer(('127.0.0.1', 0), S.H)
        S.PUERTO = http.server_port
        hilo = threading.Thread(target=http.serve_forever, daemon=True); hilo.start()
        sys.stdout.write(str(S.PUERTO) + '\\n'); sys.stdout.flush()
        sys.stdin.readline()
        print(json.dumps({'general': N.leer('plantillas.md'), 'propias': U.leer_archivo('ana-prueba', 'plantillas.md'),
                          'notas': N.notas_medico('Dr. Ficticio'), 'notas_ana': N.notas_medico('Dr. Ficticio', 'ana-prueba'),
                          'formato': U.formato('ana-prueba'), 'prefs': U.preferencias('ana-prueba')}))
        sys.stdout.flush()
        http.shutdown(); http.server_close(); hilo.join()
`;
(async()=>{
  const hijo=spawn(python,['-u','-c',codigo],{cwd:raiz,env:{...process.env,SIMULAR_IA:'1'},windowsHide:true,stdio:['pipe','pipe','pipe']});
  let diagnostico='',salida=''; hijo.stderr.on('data',d=>diagnostico+=d);
  let browser;
  try{
    const puerto=await new Promise((resolve,reject)=>{
      const t=setTimeout(()=>reject(new Error('El servidor de prueba no inició. '+diagnostico)),20000);
      hijo.once('error',reject);
      hijo.once('exit',c=>{clearTimeout(t); reject(new Error('Servidor finalizó: '+c+' '+diagnostico));});
      hijo.stdout.once('data',d=>{clearTimeout(t); resolve(Number(d.toString().trim()));});
    });
    const url=`http://127.0.0.1:${puerto}`;
    browser=await chromium.launch({channel:process.env.BROWSER_CHANNEL||'msedge',headless:true});
    const page=await browser.newPage({viewport:{width:1440,height:950}}), errores=[];
    page.on('pageerror',e=>errores.push(e.message));
    const foto=async n=>{ if(process.env.CAPTURAS) await page.screenshot({path:path.join(process.env.CAPTURAS,n+'.png')}); };
    // 1) sin sesión: pide usuario; una contraseña mal no entra
    await page.goto(url+'/');
    assert.match(page.url(),/\/ingresar$/);
    await page.getByLabel('Usuario').fill('ana prueba');
    await page.getByLabel('Contraseña').fill('mal');
    await page.getByRole('button',{name:'Entrar'}).click();
    await page.getByText('Usuario o contraseña incorrectos.').waitFor();
    await foto('1-entrar');
    await page.getByLabel('Contraseña').fill('inicial1');
    await page.getByRole('button',{name:'Entrar'}).click();
    await page.waitForURL(url+'/');
    // 2) contraseña inicial: se abre Mi cuenta y no se puede cerrar sin cambiarla
    await page.locator('#quienNom',{hasText:'Ana Prueba'}).waitFor();
    await page.locator('#cuentaCambiar').waitFor();
    await page.waitForTimeout(300); await foto('2-mi-cuenta');
    await page.keyboard.press('Escape');
    assert.equal(await page.locator('#config').isVisible(),true);
    await page.locator('#mcActual').fill('inicial1');
    await page.locator('#mcNueva').fill('propia123');
    await page.locator('#mcNueva2').fill('propia123');
    await page.getByRole('button',{name:'Cambiar contraseña'}).click();
    await page.getByText('✓ Contraseña cambiada.').waitFor();
    // formato propio del Word
    await page.locator('#mfTamano').selectOption('11');
    await page.getByRole('button',{name:'Guardar formato'}).click();
    await page.getByText('✓ Guardado',{exact:false}).first().waitFor();
    await page.locator('#cfgListo').click();
    assert.equal(await page.locator('#config').isVisible(),false);
    // 3) plantillas: guardar solo para mí
    await page.locator('#bVerPlant').click();
    await page.locator('#listaPl li',{hasText:'MAMOGRAFÍA'}).click();
    await page.locator('#plCuerpo').fill('TITULO: MAMOGRAFÍA\n- Mamas de densidad tipo B.\n- Frase de Ana.');
    await page.locator('#bGuardarPl').click();
    await page.getByText('solo para vos o para todos',{exact:false}).waitFor();
    await page.waitForTimeout(300); await foto('3-destino');
    assert.equal(await page.locator('#cfCampo').isVisible(),false);
    await page.getByRole('button',{name:'Solo para mí'}).click();
    await page.getByText('Guardadas solo para vos.',{exact:false}).waitFor();
    await foto('4-plantilla-propia');
    await page.locator('#listaPl li .etq-mia',{hasText:'mía'}).waitFor();
    await page.locator('#plOrigen').waitFor();
    // 4) notas propias de un médico
    await page.locator('#bVerMed').click();
    await page.locator('#listaMed li',{hasText:'Dr. Ficticio'}).click();
    await page.locator('#medNotas').fill('Notas de Ana.');
    await page.locator('#bGuardarMed').click();
    await page.getByRole('button',{name:'Solo para mí'}).click();
    await page.getByText('Notas guardadas solo para vos.').waitFor();
    await page.locator('#medOrigen').waitFor();
    // 5) informe armado con el estilo de otro: aviso con «Regenerar con mi estilo»
    await page.locator('#casos li').first().click();
    await page.locator('#estiloAviso',{hasText:'estilo de Beto'}).waitFor();
    assert.equal(await page.getByRole('button',{name:'Regenerar con mi estilo'}).isVisible(),true);
    await foto('5-aviso-estilo');
    if(process.env.CAPTURAS){ const adm=await browser.newPage({viewport:{width:1300,height:900}}); await adm.goto(url+'/admin');
      await adm.locator('#usuarios table').waitFor(); await adm.locator('#secUsu').screenshot({path:path.join(process.env.CAPTURAS,'6-panel.png')}); await adm.close(); }
    // 6) preferencias: siguen al usuario
    await page.evaluate(()=>localStorage.setItem('pref_salto','5'));
    await page.waitForTimeout(5600);
    // 7) salir: vuelve a pedir usuario
    await page.locator('#bCerrar').click().catch(()=>{});
    await page.locator('#bSalir').click();
    await page.waitForURL(/\/ingresar$/);
    assert.deepEqual(errores,[]);
    hijo.stdin.write('\n');
    const final=await new Promise(r=>{hijo.stdout.on('data',d=>{salida+=d; if(salida.includes('}\n')) r(JSON.parse(salida.trim().split('\n').pop()));});});
    assert.ok(!final.general.includes('Frase de Ana'));
    assert.ok(final.propias.includes('Frase de Ana'));
    assert.equal(final.notas,'Notas generales.');
    assert.equal(final.notas_ana,'Notas de Ana.');
    assert.deepEqual(final.formato,{tamano_fuente:11});
    assert.equal(final.prefs.pref_salto,'5');
    console.log('Transcriptores: entrar, contraseña inicial, plantillas y notas propias, formato, aviso de estilo, preferencias y salir OK.');
  } finally {
    if(browser) await browser.close();
    if(hijo.exitCode===null){ try{hijo.stdin.write('\n');}catch(e){} setTimeout(()=>hijo.kill(),3000).unref(); }
  }
})().catch(e=>{console.error(e); process.exit(1);});
