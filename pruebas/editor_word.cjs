// Datos ficticios: no inicia el servidor de producción ni lee informes de pacientes.
// PLAYWRIGHT_MODULE permite usar la instalación de Playwright del entorno de desarrollo.
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const assert = require('node:assert/strict');
const web = path.resolve(__dirname, '../web');
const p = t => ({t, b:false, a:'', a0:'', r:null});
const textoLargo = 'Párrafo de prueba con palabras y medidas ficticias. '.repeat(600);
let modelo = [p('Informe ficticio'), null, p(textoLargo), p('Último párrafo.')];
let formato = null, borrador = '';
const pagina = {nombre:'A4', ancho_cm:21, alto_cm:29.7, margen_superior_cm:7.5, margen_inferior_cm:4, margen_izquierdo_cm:1.3, margen_derecho_cm:3};
const server = http.createServer((req,res) => {
  const file = req.url === '/editor_word.js' ? 'editor_word.js' : 'index.html';
  res.setHeader('Content-Type', file.endsWith('.js') ? 'text/javascript' : 'text/html; charset=utf-8');
  res.end(fs.readFileSync(path.join(web,file)));
});
(async () => {
  await new Promise(r=>server.listen(0,'127.0.0.1',r));
  const browser = await chromium.launch({channel:process.env.BROWSER_CHANNEL || 'msedge',headless:true});
  try {
    const page = await browser.newPage({viewport:{width:1440,height:1000}}), errores=[];
    page.on('pageerror', e=>errores.push(e.message));
    await page.route('**/api/**', async route=>{
      const req=route.request(), u=new URL(req.url()), d=req.postDataJSON(); let r={ok:true};
      if(u.pathname==='/api/casos') r={casos:[],ollama:true,ia_estado:'ok'};
      if(u.pathname==='/api/mi_pc') r={pc:'Servidor',remoto:false,medico:''};
      if(u.pathname==='/api/medicos') r={medicos:[]};
      if(u.pathname==='/api/formato') r={palabras_titulo:['rx','ecografia'],negrita_titulos:true,prefijos:[],exactas:[]};
      if(u.pathname==='/api/vista_previa') r={parrafos:modelo,pagina,fuente:'Tahoma',tamano:12,encabezado:6};
      if(u.pathname==='/api/formato_caso') formato=d.formato;
      if(u.pathname==='/api/borrador') borrador=d.html;
      await route.fulfill({json:r});
    });
    await page.goto(`http://127.0.0.1:${server.address().port}/`);
    await page.waitForFunction(()=>typeof FMT!=='undefined');
    await page.evaluate(async pars=>{
      actual='prueba-ficticia'; mostrar('caso');
      armarEditor(pars.map(p=>({segs:[{t:p?.t||''}],titulo:false}))); await abrirVistaPrevia();
    }, modelo);
    assert.deepEqual(errores,[]);
    const hojas = await page.locator('.vp-pag').count(); assert(hojas>2);
    assert.equal(await page.locator('.vp-ed > p').evaluateAll(ps=>ps.filter(p=>p.dataset.k==='2').map(p=>p.textContent).join('')),textoLargo);
    assert(await page.locator('.vp-pag').evaluateAll(hs=>hs.every(h=>Math.abs(h.offsetWidth-21*96/2.54)<1 && Math.abs(h.offsetHeight-29.7*96/2.54)<1)));
    assert(await page.locator('.vp-cuerpo').evaluateAll(cs=>cs.every(c=>c.scrollHeight<=c.clientHeight+1)));
    for(const zoom of ['0.75','1','1.25']){
      await page.selectOption('#vpZoom',zoom);
      assert.equal(await page.locator('.vp-pag').count(),hojas);
      assert(await page.locator('.vp-cuerpo').evaluateAll(cs=>cs.every(c=>c.scrollHeight<=c.clientHeight+1)));
    }
    await page.selectOption('#vpZoom','ajustar');
    // Fuente, tamaño y estilo aplicados a parte de un párrafo y conservados en el modelo.
    await page.evaluate(()=>restaurarSel({a:{k:0,o:0},b:{k:0,o:7}}));
    await page.locator('#vpFmt [data-cmd=bold]').click();
    await page.selectOption('#vpFuente','Arial');
    await page.locator('#vpTamano').fill('24'); await page.locator('#vpTamano').press('Enter');
    assert(await page.evaluate(()=>VP.parrafos[0].r.some(r=>r.b&&r.f==='Arial'&&r.s===24)));
    // Menú contextual: el clic derecho mantiene la selección.
    await page.evaluate(()=>restaurarSel({a:{k:0,o:0},b:{k:0,o:7}}));
    await page.locator('.vp-ed > p').first().click({button:'right'});
    await page.locator('#vpMenu [data-cmd=italic]').click();
    assert(await page.evaluate(()=>VP.parrafos[0].r.some(r=>r.i)));
    // Selección y formato entre varias hojas.
    await page.evaluate(()=>{
      restaurarSel({a:{k:2,o:10},b:{k:2,o:9000}}); cambiarFormato(estilo('foreColor','#C00000'));
    });
    assert(await page.evaluate(()=>VP.parrafos[2].r.some(r=>r.c==='#C00000'&&r.t.length===8990)));
    // Editar, dividir párrafos y deshacer sin perder texto ni marcas de párrafos no editados.
    await page.evaluate(()=>{ restaurarSel({a:{k:3,o:0},b:{k:3,o:0}}); });
    await page.keyboard.type('Texto nuevo. ');
    assert(await page.evaluate(()=>VP.parrafos[3].t.startsWith('Texto nuevo. ')));
    await page.keyboard.press('Enter');
    assert.equal(await page.evaluate(()=>VP.parrafos.length),5);
    await page.keyboard.press('Control+z'); assert.equal(await page.evaluate(()=>VP.parrafos.length),4);
    await page.evaluate(()=>guardarFormato());
    assert(formato.parrafos.some(p=>p.r.some(r=>r.s===24&&r.f==='Arial')));
    assert(borrador.includes('Texto nuevo. '));
    // Recálculo al reducir el documento: no quedan hojas vacías anteriores.
    await page.evaluate(()=>{restaurarSel({a:{k:2,o:0},b:{k:2,o:VP.parrafos[2].t.length}}); reemplazarWord('Breve.','insertText');});
    assert.equal(await page.locator('.vp-pag').count(),1);
    // Guardado y reapertura del formato simulado del backend.
    modelo=await page.evaluate(()=>copiaWord(VP.parrafos));
    await page.evaluate(()=>cerrarVistaPrevia()); await page.evaluate(()=>abrirVistaPrevia());
    assert(await page.evaluate(()=>VP.parrafos[0].r.some(r=>r.s===24&&r.f==='Arial'&&r.i)));
    // Deshacer una corrección también restaura las marcas originales de revisión.
    await page.evaluate(()=>{
      const el=editor.firstElementChild;
      el.innerHTML='<mark class="m-dudoso">Informe</mark> ficticio';
      restaurarSel({a:{k:0,o:0},b:{k:0,o:7}}); reemplazarWord('Cambio','insertText');
      deshacerFmt(true);
    });
    assert.equal(await page.locator('#editor mark.m-dudoso').count(),1);
    // El menú queda dentro de una ventana pequeña y Escape no cierra el documento.
    await page.setViewportSize({width:800,height:650});
    await page.evaluate(()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r))));
    await page.locator('.vp-ed > p').first().click({button:'right'});
    const menu=await page.locator('#vpMenu').boundingBox();
    assert(menu.x>=0 && menu.y>=0 && menu.x+menu.width<=800 && menu.y+menu.height<=650);
    await page.keyboard.press('Escape');
    assert(await page.locator('#vp').evaluate(el=>el.classList.contains('abierta')));
    await page.setViewportSize({width:1440,height:1000});
    await page.screenshot({path:path.join(__dirname,'editor_word_resultado.png'),fullPage:true});
    // Documento de muchos párrafos: edición al final conserva las hojas iniciales y coincide con repaginación completa.
    const rendimiento = await page.evaluate(()=>{
      VP.parrafos=Array.from({length:180},(_,i)=>({t:`Párrafo ficticio ${i}. `+'Texto de ensayo. '.repeat(15),b:false,a:'',a0:''}));
      sincronizarInforme();paginar(VP);
      const primera=document.querySelector('.vp-pag');
      const modelo=copiaWord(VP.parrafos);modelo[178].t+=' Cambio al final.';
      const inicio=performance.now();ponerModelo(modelo,{a:{k:178,o:0},b:{k:178,o:0}});const incremental=performance.now()-inicio;
      const conservada=primera===document.querySelector('.vp-pag');
      const contenido=()=>[...document.querySelectorAll('.vp-ed > p')].map(p=>[p.dataset.k,p.dataset.desde,p.dataset.hasta,p.textContent]);
      const parcial=contenido(), t=performance.now();paginar(VP);const completa=performance.now()-t;
      let iguales=JSON.stringify(parcial)===JSON.stringify(contenido());
      // Inserción, borrado y formato en distintas posiciones, incluidos párrafos que cruzan hojas.
      for(const posicion of [5,90,179]){
        const k=Math.min(posicion,VP.parrafos.length-1);
        const nuevo=copiaWord(VP.parrafos);nuevo[k].t+=' Texto agregado. '.repeat(20);
        ponerModelo(nuevo,{a:{k,o:0},b:{k,o:0}});const p=contenido();paginar(VP);
        iguales=iguales && JSON.stringify(p)===JSON.stringify(contenido());
        const reducido=copiaWord(VP.parrafos);reducido.splice(k,1);
        ponerModelo(reducido,{a:{k:0,o:0},b:{k:0,o:0}});const r=contenido();paginar(VP);
        iguales=iguales && JSON.stringify(r)===JSON.stringify(contenido());
      }
      return {conservada,iguales,incremental,completa};
    });
    assert(rendimiento.conservada);assert(rendimiento.iguales);
    console.log('Medición editor ficticio (ms):',JSON.stringify(rendimiento));
    assert.deepEqual(errores,[]);
    console.log(`OK: ${hojas} hojas A4, párrafo largo completo, formato, menú, edición, deshacer, guardado y reapertura.`);
  } finally { await browser.close(); }
})().catch(e=>{console.error(e);process.exitCode=1;}).finally(()=>server.close());
