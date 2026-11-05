// Prueba del orden de «Para revisar» en la pantalla de inicio (issue #29): el estudio más nuevo va primero,
// la tarjeta y la cifra apuntan al más reciente y uno que llega con la app abierta aparece arriba. Solo casos ficticios.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const http=require('node:http'),assert=require('node:assert/strict');
const {archivoWeb}=require('./web_pruebas.cjs');
const server=http.createServer((req,res)=>{
  if(req.url.startsWith('/audio/')){res.statusCode=404;res.end();return;}
  const [tipo,cuerpo]=archivoWeb(req.url);
  res.setHeader('Content-Type',tipo);
  res.end(cuerpo);
});
const caso=(nombre,paciente,fecha,extra={})=>({nombre,titulo:nombre,paciente,estado:'listo',fecha,origen:'Servidor',marcas:0,
  puede_borrar:true,estudios:'',medico:'',...extra});
// Se entregan desordenados a propósito: el orden de la pantalla no puede depender del que manda el servidor.
let casos=[caso('b','Paciente B',1793800000),caso('c','Paciente C',1793803600),caso('a','Paciente A',1793796400)];
setTimeout(()=>{console.error('La prueba del orden del inicio tardó demasiado.'); process.exit(1);},90000).unref();
(async()=>{
  await new Promise(r=>server.listen(0,'127.0.0.1',r));
  const browser=await chromium.launch({channel:process.env.BROWSER_CHANNEL||'msedge',headless:true});
  try{
    const page=await browser.newPage(),errores=[];
    page.on('pageerror',e=>errores.push(e.message));
    await page.route('**/api/**',async route=>{
      const u=new URL(route.request().url());let r={ok:true};
      if(u.pathname==='/api/casos')r={casos,ollama:true,ia_estado:'ok'};
      if(u.pathname==='/api/mi_pc')r={pc:'Servidor',remoto:false,medico:''};
      if(u.pathname==='/api/medicos')r={medicos:[]};
      if(u.pathname==='/api/formato')r={palabras_titulo:[],prefijos:[],exactas:[]};
      await route.fulfill({json:r});
    });
    await page.goto(`http://127.0.0.1:${server.address().port}`);
    await page.waitForFunction(()=>typeof armarVacio!=='undefined');
    const leer=()=>page.evaluate(()=>{
      const sec=[...document.querySelectorAll('#vacio .ini-sec')].find(x=>x.querySelector('h3').textContent.startsWith('Para revisar'));
      const una=(sel,campo)=>{const e=document.querySelector(sel);return e?(campo==='n'?e.dataset.n:e[campo]):'';};
      return {filas:sec?[...sec.querySelectorAll('.ini-abrir')].map(b=>b.dataset.n):[],
        rotulo:sec?sec.querySelector('h3').textContent:'',
        tarjeta:una('#vacio .vac-bot [data-acc="abrir"]','n'),
        textoTarjeta:una('#vacio .vac-card p','textContent'),
        cifra:una('#vacio .ini-cifra[data-acc="abrir"]','n'),
        tituloCifra:una('#vacio .ini-cifra[data-acc="abrir"]','title')};
    });
    await page.waitForFunction(()=>document.querySelector('#vacio .ini-cifra[data-acc="abrir"]'));
    // 1) al abrir: el más nuevo (c) arriba de todo, después b y a
    let v=await leer();
    assert.deepEqual(v.filas,['c','b','a']);
    assert.match(v.rotulo,/del más nuevo al más antiguo/);
    assert.equal(v.tarjeta,'c');
    assert.match(v.textoTarjeta,/El más reciente/);
    assert.equal(v.cifra,'c');
    assert.match(v.tituloCifra,/más reciente/);
    // 2) llega un estudio nuevo con la app abierta: aparece arriba sin recargar
    casos=[...casos,caso('d','Paciente D',1793807200)];
    await page.evaluate(()=>cargarLista());
    await page.waitForFunction(()=>document.querySelector('#vacio .ini-cifra[data-acc="abrir"]')?.dataset.n==='d');
    v=await leer();
    assert.deepEqual(v.filas,['d','c','b','a']);
    assert.equal(v.tarjeta,'d');
    assert.deepEqual(errores,[]);
    console.log('Orden de «Para revisar» en el inicio: correcto.');
  } finally { await browser.close(); server.close(); }
})().catch(e=>{console.error(e);process.exit(1);});
