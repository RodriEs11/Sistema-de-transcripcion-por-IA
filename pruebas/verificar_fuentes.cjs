const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
for(const archivo of fs.readdirSync('web')){
  if(fs.statSync('web/'+archivo).isDirectory())continue;   // web/plantillas: páginas con marcadores {{…}}
  const texto=fs.readFileSync('web/'+archivo,'utf8');
  if(archivo.endsWith('.js'))new vm.Script(texto,{filename:archivo});
  if(archivo.endsWith('.html'))for(const script of texto.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/gi))new vm.Script(script[1],{filename:archivo});
}
const nombres=[...fs.readFileSync('web/index.html','utf8').matchAll(/^\s*(?:async\s+)?function\s+(\w+)/gm)].map(m=>m[1]);
assert.equal(new Set(nombres).size,nombres.length,'Funciones repetidas en index.html');
console.log('Sintaxis JS y funciones de index correctas.');
