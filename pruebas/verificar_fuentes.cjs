const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const {unirPartes}=require('./web_pruebas.cjs');
for(const archivo of fs.readdirSync('web')){
  if(fs.statSync('web/'+archivo).isDirectory())continue;   // plantillas/ (marcadores {{…}}), js/ y css/ (abajo)
  const texto=fs.readFileSync('web/'+archivo,'utf8');
  if(archivo.endsWith('.js'))new vm.Script(texto,{filename:archivo});
  if(archivo.endsWith('.html'))for(const script of texto.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/gi))new vm.Script(script[1],{filename:archivo});
}
// Script de la página principal: cada parte es código completo y todas juntas son el script que envía el servidor.
for(const parte of fs.readdirSync('web/js/principal').filter(f=>f.endsWith('.js')))
  new vm.Script(fs.readFileSync('web/js/principal/'+parte,'utf8'),{filename:'js/principal/'+parte});
const principal=unirPartes('js/principal','.js');
new vm.Script(principal,{filename:'js/principal.js'});
const nombres=[...principal.matchAll(/^\s*(?:async\s+)?function\s+(\w+)/gm)].map(m=>m[1]);
const repetidas=nombres.filter((n,i)=>nombres.indexOf(n)!==i);
assert.deepEqual(repetidas,[],'Funciones repetidas en web/js/principal');
const index=fs.readFileSync('web/index.html','utf8');
assert.ok(index.includes('<link rel="stylesheet" href="/css/principal.css">'),'index.html no carga /css/principal.css');
assert.ok(index.includes('<script src="/js/principal.js"></script>'),'index.html no carga /js/principal.js');
console.log(`Sintaxis JS correcta; ${nombres.length} funciones en ${fs.readdirSync('web/js/principal').length} partes de la página principal, sin repetidas.`);
