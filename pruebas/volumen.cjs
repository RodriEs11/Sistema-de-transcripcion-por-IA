// Selector de volumen del reproductor (issue #31). Solo datos ficticios.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const fs=require('node:fs'),path=require('node:path'),http=require('node:http'),assert=require('node:assert/strict');
const {archivoWeb}=require('./web_pruebas.cjs');
const configuracion=JSON.parse(fs.readFileSync(path.resolve(__dirname,'../configuracion.ejemplo.json'),'utf8'));
const palabras=['Dictado','ficticio','de','prueba.'].map((p,i)=>({p:p+' ',n:p.toLowerCase().replace('.',''),ini:i*.4,fin:(i+1)*.4,conf:1}));
const lineas=[{segs:[{t:'Informe ficticio'}]},{segs:[{t:'Cierre ficticio.'}]}];
const wav=Buffer.alloc(44+16000*2*4);
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
  const [tipo,cuerpo]=archivoWeb(req.url);
  res.setHeader('Content-Type',tipo);res.end(cuerpo);
});
const estado=page=>page.evaluate(()=>({
  valor:+$('#vol').value,volumen:audio.volume,nivel:$('#volumen').dataset.nivel,
  guardado:localStorage.getItem('volumen'),antes:localStorage.getItem('volumenAntes'),
  titulo:$('#vol').title,texto:$('#vol').getAttribute('aria-valuetext'),
  pulsado:$('#bVol').getAttribute('aria-pressed'),etiqueta:$('#bVol').getAttribute('aria-label'),
  x:getComputedStyle(document.querySelector('#bVol .vol-x')).display,
  onda1:getComputedStyle(document.querySelector('#bVol .vol-onda1')).display,
  onda2:getComputedStyle(document.querySelector('#bVol .vol-onda2')).display,
}));
const mover=(page,v)=>page.evaluate(v=>{const r=$('#vol');r.value=String(v);
  r.dispatchEvent(new Event('input',{bubbles:true}));r.dispatchEvent(new Event('change',{bubbles:true}));},v);
async function abrir(page){
  await page.waitForFunction(()=>typeof FMT!=='undefined');
  await page.evaluate(()=>abrirCaso2('caso-uno'));
  await page.waitForFunction(()=>audio.readyState>=2 && !$('#caso').hidden);
}
(async()=>{
  await new Promise(r=>server.listen(0,'127.0.0.1',r));
  const browser=await chromium.launch({channel:process.env.BROWSER_CHANNEL||'msedge',headless:true});
  try{
    const page=await browser.newPage({viewport:{width:1366,height:768}}),errores=[];
    page.setDefaultTimeout(15000);page.on('pageerror',e=>errores.push(e.message));
    await page.route('**/api/**',async route=>{
      const req=route.request(),u=new URL(req.url()),d=req.postDataJSON(),nombre=d?.nombre||u.searchParams.get('nombre')||'caso-uno';let r={ok:true};
      if(u.pathname==='/api/casos')r={casos:[],ollama:true,ia_estado:'ok'};
      if(u.pathname==='/api/mi_pc')r={pc:'Servidor',remoto:false,medico:''};
      if(u.pathname==='/api/medicos')r={medicos:[]};
      if(u.pathname==='/api/formato')r={palabras_titulo:['rx'],negrita_titulos:true,prefijos:[],exactas:[]};
      if(u.pathname==='/api/caso')r={nombre,titulo:nombre,paciente:'Caso ficticio',palabras,lineas,omisiones:[],omisiones_ok:[],estudios_nuevos:[],borrador:null};
      if(u.pathname==='/api/onda')r={dur:4,picos:Array(400).fill(25)};
      if(u.pathname==='/api/vista_previa')r={pagina:configuracion.pagina,fuente:'Tahoma',tamano:12,encabezado:configuracion.lineas_vacias_para_encabezado,
        parrafos:d.texto.split('\n').map(t=>t?{t,b:false,a0:'',a:'',r:null}:null)};
      await route.fulfill({json:r});
    });
    await page.goto(`http://127.0.0.1:${server.address().port}`);
    await abrir(page);

    // Se ve, a la derecha de +3s y antes de la barra de posición, y la fila no se desborda en 1366 × 768.
    const caja=await page.evaluate(()=>{const b=s=>document.querySelector(s).getBoundingClientRect(),f=document.querySelector('.f1');
      return {adel:b('#bAdel'),vol:b('#volumen'),prog:b('#prog'),rango:b('#vol'),desborda:f.scrollWidth>f.clientWidth+1};});
    assert.ok(caja.vol.width>0 && caja.rango.width>=40,'el selector de volumen se ve');
    assert.ok(caja.vol.left>=caja.adel.right && caja.vol.right<=caja.prog.left,'va entre +3s y la barra de posición');
    assert.ok(Math.abs(caja.vol.top+caja.vol.height/2-(caja.adel.top+caja.adel.height/2))<4,'alineado con los botones del audio');
    assert.equal(caja.desborda,false,'la fila del reproductor entra en 1366 px');

    // Sin nada guardado: 100 %, ícono con dos ondas.
    let e=await estado(page);
    assert.deepEqual([e.valor,e.volumen,e.nivel,e.x,e.onda2],[100,1,'alto','none','inline'],'arranca al 100 %');

    // El porcentaje se aplica tal cual al audio.
    await mover(page,30);e=await estado(page);
    assert.deepEqual([e.volumen,e.nivel,e.titulo,e.texto,e.guardado],[.3,'bajo','Volumen: 30 %','30 %','30'],'30 % = 0,3');
    assert.deepEqual([e.onda1,e.onda2,e.x],['inline','none','none'],'nivel bajo: una sola onda');
    await mover(page,75);e=await estado(page);
    assert.deepEqual([e.volumen,e.nivel],[.75,'alto'],'75 % = 0,75');

    // 0 %: ícono silenciado.
    await mover(page,0);e=await estado(page);
    assert.deepEqual([e.volumen,e.nivel,e.pulsado,e.etiqueta,e.x,e.onda1,e.onda2],[0,'silencio','true','Activar el sonido','inline','none','none'],'0 % muestra el parlante tachado');
    assert.equal(e.antes,'75','silenciar con el deslizador recuerda el nivel anterior');
    await page.click('#bVol');e=await estado(page);
    assert.deepEqual([e.valor,e.volumen,e.nivel],[75,.75,'alto'],'el parlante vuelve al nivel anterior');

    // El parlante silencia y restaura.
    await mover(page,55);await page.click('#bVol');e=await estado(page);
    assert.deepEqual([e.valor,e.volumen,e.nivel,e.guardado,e.antes],[0,0,'silencio','0','55'],'el parlante silencia');
    await page.click('#bVol');e=await estado(page);
    assert.deepEqual([e.valor,e.volumen],[55,.55],'y vuelve al 55 %');

    // Rueda del mouse: de a 5 %, con límites en 0 y 100, sin desplazar la página.
    const r=await page.locator('#vol').boundingBox();await page.mouse.move(r.x+r.width/2,r.y+r.height/2);
    await page.mouse.wheel(0,-100);e=await estado(page);assert.equal(e.valor,60,'rueda arriba: +5 %');
    await page.mouse.wheel(0,100);await page.mouse.wheel(0,100);e=await estado(page);assert.equal(e.valor,50,'rueda abajo: −5 %');
    for(let i=0;i<15;i++)await page.mouse.wheel(0,-100);
    e=await estado(page);assert.deepEqual([e.valor,e.volumen],[100,1],'no pasa de 100 %');
    await page.mouse.move(0,0);

    // Teclado sobre el deslizador.
    await page.focus('#vol');await page.keyboard.press('ArrowLeft');e=await estado(page);
    assert.deepEqual([e.valor,e.volumen],[95,.95],'flecha izquierda: −5 %');

    // Lo que suena aparte usa el mismo volumen: el arrastre sobre la onda y las muestras de Médicos.
    await mover(page,40);
    const aparte=await page.evaluate(()=>{
      const ctx=ctxScrub(),valores=[],crear=ctx.createGain.bind(ctx);
      ctx.createGain=()=>{const g=crear(),orig=g.gain.linearRampToValueAtTime.bind(g.gain);
        g.gain.linearRampToValueAtTime=(v,t)=>{valores.push(v);return orig(v,t);};return g;};
      const buf=scrub.buf;scrub.buf=ctx.createBuffer(1,24000,24000);granoScrub(0,.1);scrub.buf=buf;ctx.createGain=crear;
      const b=document.createElement('button');escucharMuestra('caso-uno',b);const muestra=AUDIO_M.volume;pararMuestra();
      ponerVolumen(20);const muestraDespues=AUDIO_M.volume;ponerVolumen(40);
      return {pico:Math.max(...valores),muestra,muestraDespues};
    });
    assert.ok(Math.abs(aparte.pico-.4)<1e-6,'el arrastre sobre la onda suena al 40 %');
    assert.equal(aparte.muestra,.4,'las muestras de voz usan el volumen del reproductor');
    assert.equal(aparte.muestraDespues,.2,'y lo siguen si se cambia mientras suenan');

    // Se guarda en esta PC (no viaja con las preferencias del transcriptor) y vuelve al recargar.
    const sync=await page.evaluate(()=>({volumen:PREF_SYNC.test('volumen'),antes:PREF_SYNC.test('volumenAntes'),locales:Object.keys(prefsLocales())}));
    assert.deepEqual([sync.volumen,sync.antes,sync.locales.includes('volumen')],[false,false,false],'el volumen es de la PC');
    await page.reload();await abrir(page);e=await estado(page);
    assert.deepEqual([e.valor,e.volumen,e.nivel],[40,.4,'bajo'],'al recargar sigue en 40 %');
    await page.evaluate(()=>abrirCaso2('caso-dos'));await page.waitForFunction(()=>actual==='caso-dos'&&audio.readyState>=2);
    e=await estado(page);assert.deepEqual([e.valor,e.volumen],[40,.4],'se mantiene al abrir otro informe');

    // Silenciado también se conserva (el ícono lo muestra al volver).
    await page.click('#bVol');await page.reload();await abrir(page);e=await estado(page);
    assert.deepEqual([e.valor,e.volumen,e.nivel],[0,0,'silencio'],'silenciado sigue silenciado al recargar');
    await page.click('#bVol');e=await estado(page);assert.equal(e.valor,40,'y el parlante recuerda el 40 % después de recargar');

    // Valores guardados inválidos: 100 %.
    await page.evaluate(()=>{localStorage.setItem('volumen','abc');localStorage.setItem('volumenAntes','-3');});
    await page.reload();await abrir(page);e=await estado(page);assert.deepEqual([e.valor,e.volumen],[100,1],'valor guardado inválido: 100 %');

    // «Volver a la configuración original de la pantalla» lo deja en 100 %.
    await mover(page,25);
    await page.evaluate(()=>{$('#cfgOriginal').onclick();});await page.click('#cfSi');
    await page.waitForFunction(()=>localStorage.getItem('volumen')===null);
    e=await estado(page);assert.deepEqual([e.valor,e.volumen,e.antes],[100,1,null],'restablecer vuelve al 100 %');

    // Otros anchos: el deslizador queda mientras entre y la fila del reproductor nunca se desborda.
    const medir=async ancho=>{await page.setViewportSize({width:ancho,height:700});await page.waitForTimeout(150);
      return page.evaluate(()=>{const f=document.querySelector('.f1');
        return {rango:getComputedStyle($('#vol')).display,boton:$('#bVol').getBoundingClientRect().width>0,desborda:f.scrollWidth>f.clientWidth+1};});};
    assert.deepEqual(await medir(800),{rango:'block',boton:true,desborda:false},'800 px: completo');
    assert.deepEqual(await medir(700),{rango:'block',boton:true,desborda:false},'700 px: el reproductor en su fila, completo');
    await page.evaluate(()=>{localStorage.setItem('listaOculta','');aplicarLista();});
    assert.deepEqual(await medir(1100),{rango:'block',boton:true,desborda:false},'1100 px con la lista: completo');
    await page.evaluate(()=>{localStorage.setItem('listaOculta','1');aplicarLista();});
    // Barra muy angosta: queda solo el parlante, que sigue silenciando.
    assert.deepEqual(await medir(460),{rango:'none',boton:true,desborda:false},'460 px: solo el parlante');
    await page.click('#bVol');e=await estado(page);assert.equal(e.volumen,0,'el parlante silencia en la barra angosta');

    if(process.env.CAPTURAS){
      await page.setViewportSize({width:1366,height:768});await page.click('#bVol');await mover(page,35);
      await page.locator('#barraCaso').screenshot({path:process.env.CAPTURAS+'/volumen-1366.png'});
      await mover(page,0);await page.locator('#barraCaso').screenshot({path:process.env.CAPTURAS+'/volumen-silencio.png'});
      for(const ancho of [1100,700,460]){await page.setViewportSize({width:ancho,height:700});await page.waitForTimeout(150);
        await page.locator('#barraCaso').screenshot({path:`${process.env.CAPTURAS}/volumen-${ancho}.png`});}
    }
    assert.deepEqual(errores,[],'sin errores en la página');
    console.log('OK: selector de volumen (posición, porcentaje, silenciado, rueda y teclado, onda y muestras, persistencia por PC, restablecer y barra angosta).');
  }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;}).finally(()=>server.close());
