// Prueba de desconexión, cierre, serialización y recuperación. Solo casos ficticios.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const fs=require('node:fs'),path=require('node:path'),http=require('node:http'),assert=require('node:assert/strict');
const web=path.resolve(__dirname,'../web');
const {archivoWeb}=require('./web_pruebas.cjs');
const pagina=JSON.parse(fs.readFileSync(path.resolve(__dirname,'../configuracion.ejemplo.json'),'utf8')).pagina;
let falla=false, activos=0, maxActivos=0, guardados=[], liberados=[], desbloquear=null, demorar=false;
let respuestaInvalida=null;
let formatoInvalido=false;
const revisiones=new Map();
const borradores=new Map();
const server=http.createServer((req,res)=>{
  if(req.url.startsWith('/audio/')) { res.statusCode=404;res.end();return; }
  const [tipo,cuerpo]=archivoWeb(req.url);
  res.setHeader('Content-Type',tipo);
  res.end(cuerpo);
});
(async()=>{
  await new Promise(r=>server.listen(0,'127.0.0.1',r));
  const browser=await chromium.launch({channel:process.env.BROWSER_CHANNEL||'msedge',headless:true});
  try {
    const page=await browser.newPage(),errores=[];
    page.on('pageerror',e=>errores.push(e.message));
    await page.route('**/api/**',async route=>{
      const req=route.request(),u=new URL(req.url()),d=req.postDataJSON();let r={ok:true};
      if(u.pathname==='/api/casos')r={casos:[],ollama:true,ia_estado:'ok'};
      if(u.pathname==='/api/mi_pc')r={pc:'Servidor',remoto:false,medico:''};
      if(u.pathname==='/api/medicos')r={medicos:[]};
      if(u.pathname==='/api/formato')r={palabras_titulo:[],prefijos:[],exactas:[]};
      if(u.pathname==='/api/caso')r={nombre:u.searchParams.get('nombre'),palabras:[],lineas:[{segs:[{t:'Texto ficticio'}]}],omisiones:[],omisiones_ok:[],borrador_revision:revisiones.get(u.searchParams.get('nombre'))||0};
      if(u.pathname==='/api/caso' && borradores.has(r.nombre))r.borrador=borradores.get(r.nombre);
      if(u.pathname==='/api/onda')r={dur:1,picos:[]};
      if(u.pathname==='/api/vista_previa')r={pagina,fuente:'Tahoma',tamano:12,encabezado:0,parrafos:[{t:'Texto ficticio',b:false,a:'',a0:''}]};
      if(u.pathname==='/api/formato_caso' && formatoInvalido)r={};
      if(u.pathname==='/api/caso/soltar')liberados.push(d.nombre);
      if(u.pathname==='/api/borrador'){
        activos++;maxActivos=Math.max(maxActivos,activos);
        if(demorar){demorar=false;await new Promise(resolve=>desbloquear=resolve);}
        activos--;
        if(falla){await route.fulfill({status:503,json:{error:'Fallo ficticio de escritura'}});return;}
        if(respuestaInvalida){await route.fulfill({json:respuestaInvalida});return;}
        if(d.revision !== (revisiones.get(d.nombre)||0)){await route.fulfill({status:409,json:{error:'El borrador cambió en otra sesión ficticia'}});return;}
        r.revision=(revisiones.get(d.nombre)||0)+1;revisiones.set(d.nombre,r.revision);
        guardados.push(d);
        borradores.set(d.nombre,d.html);
      }
      await route.fulfill({json:r});
    });
    await page.goto(`http://127.0.0.1:${server.address().port}`);
    await page.waitForFunction(()=>typeof FMT!=='undefined');
    await page.evaluate(()=>abrirCaso2('uno'));
    // Un 200 ambiguo o sin revisión no puede permitir cerrar ni ocultar cambios.
    for(const respuesta of [{},{ok:true},{ok:true,revision:'incorrecta'},{ok:true,revision:0}]){
      respuestaInvalida=respuesta;
      assert.equal(await page.evaluate(()=>cerrarCaso()),false);
      assert.equal(await page.evaluate(()=>actual),'uno');
      assert.equal(liberados.length,0);
      assert.equal(await page.evaluate(()=>borradorPendiente()),true);
    }
    respuestaInvalida=null;
    falla=true;
    assert.equal(await page.evaluate(()=>cerrarCaso()),false);
    assert.match(await page.locator('#estadoBorrador').textContent(),/No se pudo guardar/);
    await page.evaluate(()=>{editor.innerHTML='<div class="ln">Edición ficticia pendiente</div>';});
    assert.equal(await page.evaluate(()=>cerrarCaso()),false);
    assert.equal(await page.evaluate(()=>actual),'uno');
    assert.equal(liberados.length,0);
    assert(await page.locator('#reintentarBorrador').isVisible());
    assert.equal(await page.evaluate(()=>{const e=new Event('beforeunload',{cancelable:true});window.dispatchEvent(e);return e.defaultPrevented;}),true);
    await page.evaluate(()=>abrirCaso2('dos'));
    assert.equal(await page.evaluate(()=>actual),'uno');
    // Liberación administrativa no descarta los cambios locales no confirmados.
    await page.evaluate(()=>casoLiberado());
    assert.equal(await page.evaluate(()=>actual),'uno');
    assert.match(await page.evaluate(()=>editor.textContent),/Edición ficticia/);
    // Reintentar confirma; una edición durante un envío no queda marcada como guardada.
    falla=false;
    await page.locator('#reintentarBorrador').click();
    await page.waitForFunction(()=>!borradorPendiente());
    demorar=true;
    await page.evaluate(()=>{editor.innerHTML='<div class="ln">Primero</div>';window.primera=guardarBorrador();});
    for(let i=0;i<100&&!desbloquear;i++)await new Promise(r=>setTimeout(r,10));
    assert(desbloquear,'No inició escritura diferida');
    await page.evaluate(()=>{editor.innerHTML='<div class="ln">Segundo</div>';window.segunda=guardarBorrador();});
    assert.equal(activos,1);desbloquear();
    await page.evaluate(()=>Promise.all([primera,segunda]));
    assert.equal(maxActivos,1);
    assert.match(guardados.at(-2).html,/Primero/);assert.match(guardados.at(-1).html,/Segundo/);
    assert.equal(await page.evaluate(()=>borradorPendiente()),false);
    // El formato usa la misma cola y no anuncia éxito al fallar su borrador.
    falla=true;
    assert.equal(await page.evaluate(async()=>{FMT.pendiente=true;try{await guardarFormato(true);return false;}catch(e){return true;}}),true);
    assert.equal(await page.evaluate(()=>FMT.pendiente),true);
    falla=false;
    formatoInvalido=true;
    assert.equal(await page.evaluate(async()=>{try{await guardarFormato(true);return false;}catch(e){return true;}}),true);
    assert.equal(await page.evaluate(()=>FMT.pendiente),true);
    formatoInvalido=false;
    await page.evaluate(async()=>{await guardarFormato(true);await guardarBorrador();});
    await page.evaluate(()=>cerrarCaso());
    assert.equal(await page.evaluate(()=>actual),null);
    assert.equal(liberados.at(-1),'uno');
    await page.evaluate(()=>abrirCaso2('uno'));
    // Vaciar el borrador es una edición válida: reabrir no restaura el informe original.
    await page.evaluate(()=>{editor.innerHTML='';});
    await page.evaluate(()=>cerrarCaso());
    assert.equal(borradores.get('uno'),'');
    await page.evaluate(()=>abrirCaso2('uno'));
    assert.equal(await page.evaluate(()=>editor.textContent),'');
    await page.evaluate(()=>{editor.innerHTML='<div class="ln">Edición local en conflicto</div>';});
    revisiones.set('uno',revisiones.get('uno')+1);const cantidad=guardados.length;
    assert.equal(await page.evaluate(()=>cerrarCaso()),false);
    assert.equal(guardados.length,cantidad);
    assert.equal(await page.evaluate(()=>actual),'uno');
    assert.match(await page.locator('#estadoBorrador').textContent(),/otra sesión/);
    // Una conexión lenta no debe acumular consultas del listado.
    await page.evaluate(()=>cargarLista());
    let consultas=0,terminar;
    await page.route('**/api/casos',async route=>{
      consultas++;await new Promise(r=>terminar=r);
      await route.fulfill({json:{casos:[],ollama:true,ia_estado:'ok'}});
    });
    await page.evaluate(()=>{window.listasPendientes=[cargarLista(),cargarLista(),cargarLista()];});
    for(let i=0;i<100&&!terminar;i++)await new Promise(r=>setTimeout(r,10));
    assert(terminar);assert.equal(consultas,1);terminar();
    await page.evaluate(()=>Promise.all(listasPendientes));
    assert.deepEqual(errores,[]);
    console.log('OK: error visible, cierre bloqueado, beforeunload, reintento, orden de escrituras y formato.');
  } finally {await browser.close();await new Promise(r=>server.close(r));}
})().catch(e=>{console.error(e);process.exitCode=1;});
