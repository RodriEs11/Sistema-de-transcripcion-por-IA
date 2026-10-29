// Integración del editor A4 con audio, marcas y dictado. Solo datos ficticios.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const fs=require('node:fs'),path=require('node:path'),http=require('node:http'),assert=require('node:assert/strict');
const web=path.resolve(__dirname,'../web'), guardados=new Map();
const configuracion=JSON.parse(fs.readFileSync(path.resolve(__dirname,'../configuracion.ejemplo.json'),'utf8'));
const pagina=configuracion.pagina;
const palabras=['Hallazgo','dudoso','de','prueba.'].map((p,i)=>({p:p+' ',n:p.toLowerCase().replace('.',''),ini:i*.4,fin:(i+1)*.4,conf:1}));
const lineas=[{segs:[{t:'Informe ficticio'}]}, {segs:[{t:''}]},
  {segs:[{t:'Hallazgo '},{t:'dudoso',tipo:'dudoso',motivo:'Verificar el dictado ficticio',seg:.4},{t:' de prueba.'}]},
  {segs:[{t:'Cierre ficticio.'}]}];
const wav=Buffer.alloc(44+16000*2*10);
wav.write('RIFF');wav.writeUInt32LE(wav.length-8,4);wav.write('WAVEfmt ',8);wav.writeUInt32LE(16,16);
wav.writeUInt16LE(1,20);wav.writeUInt16LE(1,22);wav.writeUInt32LE(16000,24);wav.writeUInt32LE(32000,28);
wav.writeUInt16LE(2,32);wav.writeUInt16LE(16,34);wav.write('data',36);wav.writeUInt32LE(wav.length-44,40);
const server=http.createServer((req,res)=>{
  if(req.url.startsWith('/audio/')){
    res.setHeader('Content-Type','audio/wav');res.setHeader('Accept-Ranges','bytes');
    const range=/bytes=(\d+)-(\d*)/.exec(req.headers.range||'');
    if(range){
      const inicio=+range[1],fin=range[2]?Math.min(+range[2],wav.length-1):wav.length-1;
      res.statusCode=206;res.setHeader('Content-Range',`bytes ${inicio}-${fin}/${wav.length}`);
      res.setHeader('Content-Length',fin-inicio+1);res.end(wav.subarray(inicio,fin+1));
    }else{res.setHeader('Content-Length',wav.length);res.end(wav);}return;
  }
  const file=req.url==='/editor_word.js'?'editor_word.js':'index.html';
  res.setHeader('Content-Type',file.endsWith('.js')?'text/javascript':'text/html; charset=utf-8');res.end(fs.readFileSync(path.join(web,file)));
});
(async()=>{
  await new Promise(r=>server.listen(0,'127.0.0.1',r));
  const browser=await chromium.launch({channel:process.env.BROWSER_CHANNEL||'msedge',headless:true});
  try{
    const page=await browser.newPage({viewport:{width:1440,height:1000}}),errores=[];
    page.on('pageerror',e=>errores.push(e.message));
    await page.route('**/api/**',async route=>{
      const req=route.request(),u=new URL(req.url()),d=req.postDataJSON(),nombre=d?.nombre||u.searchParams.get('nombre');let r={ok:true};
      if(u.pathname==='/api/casos')r={casos:[],ollama:true,ia_estado:'ok'};
      if(u.pathname==='/api/mi_pc')r={pc:'Servidor',remoto:false,medico:''};
      if(u.pathname==='/api/medicos')r={medicos:[]};
      if(u.pathname==='/api/formato')r={palabras_titulo:['rx'],negrita_titulos:true,prefijos:[],exactas:[]};
      if(u.pathname==='/api/caso')r={nombre,titulo:nombre,paciente:'Caso ficticio',palabras,lineas,omisiones:[],omisiones_ok:[],estudios_nuevos:[],borrador:guardados.get(nombre)?.html||null};
      if(u.pathname==='/api/onda')r={dur:10,picos:Array(1600).fill(25)};
      if(u.pathname==='/api/vista_previa')r={pagina,fuente:'Tahoma',tamano:12,encabezado:configuracion.lineas_vacias_para_encabezado,parrafos:d.texto.split('\n').map(t=>{
        if(!t)return null;const f=guardados.get(nombre)?.formato?.parrafos.find(p=>p.t===t);return {t,b:false,a0:'',a:f?.a||'',r:f?.r||null};
      })};
      if(u.pathname==='/api/borrador')guardados.set(nombre,{...guardados.get(nombre),html:d.html});
      if(u.pathname==='/api/formato_caso')guardados.set(nombre,{...guardados.get(nombre),formato:d.formato});
      await route.fulfill({json:r});
    });
    await page.goto(`http://127.0.0.1:${server.address().port}`);await page.waitForFunction(()=>typeof FMT!=='undefined');
    await page.evaluate(()=>abrirCaso2('caso-uno'));
    await page.waitForFunction(()=>audio.readyState>=2);
    assert(await page.locator('#vp').evaluate(e=>e.classList.contains('integrado')&&!e.classList.contains('ampliado')));
    assert(await page.locator('.player').isVisible());assert(await page.locator('#dictado').isVisible());assert(await page.locator('#ondaCaja').isVisible());
    assert.equal(await page.locator('#vpHojas mark.m-dudoso').count(),1);
    // Margen superior de 2,5 cm sin renglones reservados en la revisión integrada.
    assert.equal(await page.locator('.vp-enc').count(),0);
    assert(Math.abs(await page.locator('.vp-pag').first().evaluate(e=>parseFloat(getComputedStyle(e).paddingTop))-2.5*96/2.54)<0.1);
    // Atajos de Word en español: Ctrl+S subraya; Q/T/D/J alinean el párrafo.
    await page.evaluate(()=>restaurarSel({a:{k:2,o:0},b:{k:2,o:8}}));
    await page.keyboard.press('Control+s');assert(await page.evaluate(()=>VP.parrafos[2].r.some(r=>r.u)));
    await page.keyboard.press('Control+s');assert(await page.evaluate(()=>VP.parrafos[2].r.every(r=>!r.u)));
    for(const [tecla,alineacion] of [['q','left'],['t','center'],['d','right'],['j','justify']]){
      await page.keyboard.press('Control+'+tecla);assert.equal(await page.evaluate(()=>VP.parrafos[2].a),alineacion);
    }
    assert.equal(await page.locator('#vpMenu [data-al] svg').count(),4);
    assert(await page.locator('#vpMenu [data-al]').evaluateAll(bs=>bs.every(b=>!b.textContent.trim()&&b.title&&b.getAttribute('aria-label'))));
    // Las dos paletas ofrecen los mismos doce colores, sin abrir el selector del sistema.
    for(const id of ['vpColoresPredeterminados','vpMenuColores']){
      assert.equal(await page.locator('#'+id+' button').count(),12);
      for(const color of ['#FF0000','#FFFF00','#0070C0','#000000']) assert.equal(await page.locator('#'+id+` [data-c="${color}"]`).count(),1);
    }
    await page.locator('#vpHojas p[data-k="2"]').click({button:'right'});
    await page.locator('#vpMenuColores [data-c="#FF0000"]').click();
    assert(await page.evaluate(()=>VP.parrafos[2].r.some(r=>r.c==='#FF0000')));
    await page.locator('#vpColorBtn').click();await page.locator('#vpColoresPredeterminados [data-c="#0070C0"]').click();
    assert(await page.evaluate(()=>VP.parrafos[2].r.some(r=>r.c==='#0070C0')));
    const doc=await page.locator('#vp').boundingBox(),dict=await page.locator('.dict').boundingBox();assert(doc.x+doc.width<=dict.x);
    await page.locator('#vpCerrar').click();assert(await page.locator('#vp').evaluate(e=>e.classList.contains('ampliado')));
    await page.locator('#vpCerrar').click();assert(await page.locator('#vp').evaluate(e=>!e.classList.contains('ampliado')));
    // Reproducción desde las hojas y cambio de presentación sin pausar el audio.
    await page.evaluate(()=>restaurarSel({a:{k:2,o:0},b:{k:2,o:0}}));await page.keyboard.press('F5');
    await page.waitForFunction(()=>!audio.paused);await page.keyboard.press('F9');
    assert(await page.locator('#vp').evaluate(e=>e.classList.contains('ampliado')));assert(await page.evaluate(()=>!audio.paused));
    await page.keyboard.press('Escape');assert(await page.locator('.player').isVisible());assert(await page.evaluate(()=>!audio.paused));
    await page.keyboard.press('F5');assert(await page.evaluate(()=>audio.paused));
    // Saltos y velocidad desde el editor, sin modificar su texto.
    await page.evaluate(()=>{window.llamadasAtajos=[];window.playOriginal=bPlay.onclick;window.siguienteOriginal=siguiente;bPlay.onclick=()=>llamadasAtajos.push('play');siguiente=()=>llamadasAtajos.push('marca');});
    await page.keyboard.press('Control+Space');
    await page.keyboard.press('Shift+F2');
    assert.deepEqual(await page.evaluate(()=>llamadasAtajos),[]);
    await page.keyboard.press('F5');await page.keyboard.press('F2');
    assert.deepEqual(await page.evaluate(()=>llamadasAtajos),['play','marca']);
    await page.evaluate(()=>{bPlay.onclick=playOriginal;siguiente=siguienteOriginal;});
    await page.evaluate(()=>new Promise(r=>{audio.addEventListener('seeked',r,{once:true});audio.currentTime=5;}));
    await page.keyboard.press('F6');assert.equal(await page.evaluate(()=>audio.currentTime),2);
    await page.keyboard.press('F7');assert.equal(await page.evaluate(()=>audio.currentTime),5);
    await page.keyboard.press('F3');assert.equal(await page.evaluate(()=>audio.playbackRate),0.75);
    await page.keyboard.press('F4');assert.equal(await page.evaluate(()=>audio.playbackRate),1);
    for(let i=0;i<15;i++)await page.keyboard.press('F3');
    assert.equal(await page.evaluate(()=>audio.playbackRate),0.25);
    for(let i=0;i<15;i++)await page.keyboard.press('F4');
    assert.equal(await page.evaluate(()=>audio.playbackRate),2.5);
    assert.equal(await page.evaluate(()=>leerLS('velUltima')),'2.5');
    // Cursor -> tramo del dictado, y audio -> línea del documento.
    await page.evaluate(()=>{restaurarSel({a:{k:2,o:3},b:{k:2,o:3}});seguirCursor();marcarLineaSonando(1);});
    assert(await page.locator('#dictado .eco').count()>0);assert(await page.locator('#vpHojas p.sonando').count()>0);
    // F2 selecciona una marca en la hoja visible; F10 la resuelve en ambos modelos.
    await page.keyboard.press('F2');assert.equal(await page.evaluate(()=>getSelection().toString()),'dudoso');
    await page.waitForFunction(()=>document.querySelector('#explica').style.display==='block');
    await page.keyboard.press('F10');assert.equal(await page.locator('#vpHojas mark').count(),0);assert.equal(await page.locator('#editor mark').count(),0);
    await page.evaluate(()=>audio.pause());
    // Formato por clic derecho y escritura directa mientras el reproductor sigue disponible.
    await page.evaluate(()=>restaurarSel({a:{k:2,o:0},b:{k:2,o:8}}));
    await page.locator('#vpHojas p[data-k="2"]').click({button:'right'});await page.locator('#vpMenu [data-cmd=bold]').click();
    assert(await page.evaluate(()=>VP.parrafos[2].r.some(r=>r.b)));
    assert(await page.locator('#vpMenu').isVisible());
    assert.equal(await page.evaluate(()=>getSelection().toString()),'Hallazgo');
    await page.locator('#vpMenu [data-cmd=italic]').click();
    await page.locator('#vpMenuColores [data-c="#FF0000"]').click();
    await page.locator('#vpMenuFuente').selectOption('Arial');
    await page.locator('#vpMenuTamano').fill('16');
    await page.locator('#vpMenuTamano').dispatchEvent('change');
    assert(await page.locator('#vpMenu').isVisible());
    assert.equal(await page.evaluate(()=>getSelection().toString()),'Hallazgo');
    assert(await page.evaluate(()=>VP.parrafos[2].r.some(r=>r.b&&r.i&&r.c==='#FF0000'&&r.f==='Arial'&&r.s===16)));
    await page.keyboard.press('Escape');assert(await page.locator('#vpMenu').isVisible());
    // Portapapeles real con permisos limitados al origen local de la prueba.
    await page.context().grantPermissions(['clipboard-read','clipboard-write']);
    await page.locator('#vpMenuCopiar').click();
    assert.equal(await page.evaluate(()=>navigator.clipboard.readText()),'Hallazgo');
    assert(await page.locator('#vpMenu').isVisible());
    await page.evaluate(()=>navigator.clipboard.writeText('Pegado ficticio'));
    await page.locator('#vpMenuPegar').click();
    await page.waitForFunction(()=>VP.parrafos[2].t.startsWith('Pegado ficticio'));
    assert(await page.locator('#vpMenu').isVisible());
    await page.evaluate(()=>deshacerFmt(true));
    await page.locator('#vpMenuLimpiar').click();
    assert(await page.locator('#vpMenu').isVisible());
    await page.evaluate(()=>deshacerFmt(true));
    await page.locator('#bPlay').click();assert(await page.locator('#vpMenu').isHidden());
    await page.evaluate(()=>audio.pause());
    await page.evaluate(()=>restaurarSel({a:{k:3,o:0},b:{k:3,o:0}}));await page.keyboard.type('Nuevo ');
    assert(await page.evaluate(()=>textoFinal().includes('Nuevo Cierre ficticio.')));
    // Las autocorrecciones de Word siguen insertando texto y formato en las hojas.
    await page.evaluate(()=>{ponerAutocorreccion({entradas:[{g:'PRUEBA',p:[{t:'Texto expandido',r:[{t:'Texto expandido',i:1}]}]}]});restaurarSel({a:{k:3,o:0},b:{k:3,o:0}});});
    await page.keyboard.type('PRUEBA ');
    assert(await page.evaluate(()=>VP.parrafos[3].t.startsWith('Texto expandido ')));
    assert(await page.evaluate(()=>VP.parrafos[3].r.some(r=>r.i)));
    await page.evaluate(()=>guardarFormato(true));
    // Cambiar de caso no pierde el formato; vuelve a abrirse integrado, sin F9.
    await page.evaluate(()=>abrirCaso2('caso-dos'));await page.evaluate(()=>abrirCaso2('caso-uno'));
    assert(await page.evaluate(()=>VP.parrafos[2].r.some(r=>r.b)));
    assert(await page.evaluate(()=>textoFinal().includes('Texto expandido')));
    assert(await page.locator('#vp').evaluate(e=>!e.classList.contains('ampliado')));
    await page.screenshot({path:path.join(__dirname,'revision_word_resultado.png'),fullPage:true});
    assert.deepEqual(errores,[]);
    // Configuración, conflictos, ayudas, persistencia y restablecimiento de atajos.
    await page.locator('#bConfig').click();await page.locator('#tab-teclado').click();
    assert.equal(await page.locator('#atajo-play').inputValue(),'F5');
    await page.locator('#atajo-play').selectOption('F6');
    assert.equal(await page.locator('#atajo-play').inputValue(),'F5');
    await page.locator('#atajo-play').selectOption('F8');
    assert.equal(await page.locator('#bPlay').getAttribute('aria-keyshortcuts'),'F8');
    assert(await page.locator('[data-atajo=play]').evaluateAll(es=>es.every(e=>e.textContent==='F8')));
    const velocidad=await page.evaluate(()=>audio.playbackRate);
    await page.keyboard.press('F3');assert.equal(await page.evaluate(()=>audio.playbackRate),velocidad);
    await page.locator('#cfgListo').click();
    await page.keyboard.press('F8');await page.waitForFunction(()=>!audio.paused);
    await page.keyboard.press('F8');assert(await page.evaluate(()=>audio.paused));
    await page.reload();await page.waitForFunction(()=>typeof FMT!=='undefined');
    assert.equal(await page.evaluate(()=>atajos.play),'F8');
    await page.locator('#bConfig').click();await page.locator('#tab-teclado').click();
    await page.locator('#cfgAtajosRestablecer').click();
    assert.equal(await page.locator('#atajo-play').inputValue(),'F5');
    await page.locator('#cfgListo').click();
    assert.deepEqual(errores,[]);
    console.log('OK: atajos configurables, saltos, velocidad y límites, persistencia, menú sin cierre, selección, copiar/pegar, editor y audio.');
  }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;}).finally(()=>server.close());
