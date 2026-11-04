// Archivos de la página principal para los servidores de prueba de Playwright, armados igual que en el servidor
// (transcripcion/http/paginas.py): /js/principal.js y /css/principal.css son las partes de su carpeta unidas en orden.
const fs=require('node:fs'),path=require('node:path');
const web=path.resolve(__dirname,'../web');

function unirPartes(carpeta,extension){
  const d=path.join(web,carpeta);
  return fs.readdirSync(d).filter(f=>f.endsWith(extension)).sort()
    .map(f=>fs.readFileSync(path.join(d,f),'utf8').replace(/\r\n/g,'\n')).join('');
}

// [tipo, contenido] para una dirección de la página; cualquier otra devuelve index.html, como hacían las pruebas.
function archivoWeb(url){
  const ruta=url.split('?')[0];
  if(ruta==='/editor_word.js')return['text/javascript',fs.readFileSync(path.join(web,'editor_word.js'))];
  if(ruta==='/js/principal.js')return['text/javascript; charset=utf-8',unirPartes('js/principal','.js')];
  if(ruta==='/css/principal.css')return['text/css; charset=utf-8',unirPartes('css/principal','.css')];
  return['text/html; charset=utf-8',fs.readFileSync(path.join(web,'index.html'))];
}

module.exports={archivoWeb,unirPartes};
