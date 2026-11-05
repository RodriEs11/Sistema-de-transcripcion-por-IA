// Cargar audios (página y app del trabajo), arrastrar y soltar.
/* ------------------------------------------------ cargar audios
   Un audio cargado nunca se pierde ni da error por falta de conexión:
   - En la app del trabajo (1.6 o más nueva) el audio se le pasa a la app, que lo guarda cifrado en esta PC y lo
     envía con la misma cola que los audios del sistema: funciona igual con o sin conexión, y se envía solo cuando
     el servidor vuelve (aunque se cierre la ventana).
   - En el navegador se envía directo. Si no hay conexión queda esperando en esta página (con un aviso arriba de
     la lista) y se envía solo apenas el servidor vuelve. Si se intenta cerrar la página, se avisa antes. */
const EXT_AUDIO = ['.wav','.mp3','.m4a','.ogg','.flac','.wma','.aac','.opus'];
const MAX_AUDIO = 100 * 1024 * 1024;
let APP = null;                                          // la app del trabajo lo completa al cargar la página
window.ponerApp = function(d){ APP = d || null; };
const enEspera = [];                                     // navegador sin conexión: {f, medico}
let enviandoEspera = false;
const ext = n => (n.match(/\.[^.]+$/) || [''])[0].toLowerCase();
const tamTxt = b => b >= 1048576 ? (b/1048576).toFixed(1).replace('.', ',') + ' MB' : Math.max(1, Math.round(b/1024)) + ' KB';
function validarAudio(f){
  if(!EXT_AUDIO.includes(ext(f.name))) return `«${f.name}» no es un audio que se pueda procesar (se aceptan ${EXT_AUDIO.join(' ').replace(/\./g, '')}).`;
  if(!f.size) return `«${f.name}» está vacío.`;
  if(f.size > MAX_AUDIO) return `«${f.name}» es demasiado grande (${tamTxt(f.size)}; el máximo es 100 MB).`;
  return '';
}
async function subir(files){
  const lista = [...files], malos = [];
  const buenos = lista.filter(f => { const m = validarAudio(f); if(m) malos.push(m); return !m; });
  if(malos.length) toast(malos.join(' '), [], 8000);
  if(!buenos.length) return;
  if(EN_APP && APP && APP.cola){ for(const f of buenos) await pasarALaApp(f); return; }
  let enviados = 0, guardados = 0;
  for(const f of buenos){
    if(SRV.ok === false){ enEspera.push({f}); guardados++; continue; }
    try { await enviarAudio(f); enviados++; }
    catch(e){
      if(e.sinConexion){ marcarSinConexion(); enEspera.push({f}); guardados++; }
      else toast(`No se pudo cargar «${f.name}»: ${e.message}`, [], 8000);
    }
  }
  if(guardados) toast(guardados === 1 ? `Sin conexión con el servidor: «${buenos.find(f => enEspera.some(x => x.f === f)).name}» queda esperando y se envía solo cuando vuelva.`
                                       : `Sin conexión con el servidor: ${guardados} audios quedan esperando y se envían solos cuando vuelva.`, [], 8000);
  else if(enviados) toast(enviados === 1 ? `Audio cargado: «${buenos[0].name}» · procesando…` : `${enviados} audios cargados · procesando…`);
  ponerEspera();
  cargarLista();
}
// Sin médico: lo reconoce el servidor por la voz (#30).
function enviarAudio(f){
  return pedir('/api/subir?archivo='+encodeURIComponent(f.name), {method:'POST', body:f});
}
function marcarSinConexion(){ if(SRV.ok !== false){ SRV.ok = false; SRV.desde = Date.now(); } ponerEstadoSrv(); }
function ponerEspera(){
  const box = $('#esperaEnvio'), n = enEspera.length;
  box.hidden = !n || EN_APP && !!APP;
  if(!n) return;
  box.innerHTML = `<b>${n === 1 ? '1 audio esperando para enviarse' : n + ' audios esperando para enviarse'}</b>`
    + `${n === 1 ? 'Se envía solo' : 'Se envían solos'} cuando vuelva la conexión con el servidor. No cierres esta página mientras tanto.`;
}
async function enviarEnEspera(){                         // se llama cuando el servidor vuelve a responder
  if(enviandoEspera || !enEspera.length) return;
  enviandoEspera = true; let ok = 0;
  try {
    while(enEspera.length){
      const x = enEspera[0];
      try { await enviarAudio(x.f); ok++; enEspera.shift(); }
      catch(e){ if(e.sinConexion){ marcarSinConexion(); break; } toast(`No se pudo cargar «${x.f.name}»: ${e.message}`, [], 8000); enEspera.shift(); }
    }
  } finally { enviandoEspera = false; ponerEspera(); }
  if(ok){ toast(ok === 1 ? 'Volvió la conexión: se envió el audio que estaba esperando.' : `Volvió la conexión: se enviaron los ${ok} audios que estaban esperando.`); cargarLista(); }
}
addEventListener('beforeunload', e => { if(enEspera.length){ e.preventDefault(); e.returnValue = ''; } });
/* app del trabajo: el audio va en base64 por el canal de mensajes de WebView2; la app contesta con audioEnCola() */
const esperandoApp = new Map();
let idApp = 0;
function leerBase64(f){
  return new Promise((res, rej) => { const fr = new FileReader();
    fr.onload = () => res(String(fr.result).replace(/^data:[^,]*,/, '')); fr.onerror = () => rej(fr.error || new Error('no se pudo leer el archivo')); fr.readAsDataURL(f); });
}
async function pasarALaApp(f){
  const id = 'a' + (++idApp);
  let datos;
  try { datos = await leerBase64(f); } catch(e){ toast(`No se pudo leer «${f.name}»: ${e.message}`, [], 8000); return; }
  const respuesta = new Promise(res => { esperandoApp.set(id, res); setTimeout(() => { if(esperandoApp.delete(id)) res(null); }, 20000); });
  try { chrome.webview.postMessage({accion:'audio', id, nombre: f.name, datos}); }
  catch(e){ esperandoApp.delete(id); toast(`No se pudo pasar «${f.name}» a la aplicación: ${e.message}`, [], 8000); return; }
  datos = null;
  const r = await respuesta;
  if(!r) toast(`La aplicación no confirmó «${f.name}». Probá de nuevo con Opciones → Cargar audio.`, [], 9000);
  else if(!r.ok) toast(`No se pudo cargar «${f.name}»: ${r.msg}`, [], 9000);
  else toast(r.msg === 'guardado' ? `Sin conexión: «${f.name}» quedó guardado en esta PC y se envía solo cuando vuelva.`
                                  : `Audio cargado: «${f.name}» · enviando al servidor…`, [], 6000);
  setTimeout(cargarLista, 1500);
}
window.audioEnCola = function(id, ok, msg){ const res = esperandoApp.get(id); if(res){ esperandoApp.delete(id); res({ok, msg}); } };
const drop = $('#drop');
$('#archivos').onchange = e => { const fs = [...e.target.files]; e.target.value = ''; subir(fs); };
['dragenter','dragover'].forEach(ev => document.addEventListener(ev, e => { if(e.dataTransfer?.types?.includes('Files')){ e.preventDefault(); drop.classList.add('sobre'); }}));
['dragleave','drop'].forEach(ev => document.addEventListener(ev, e => { if(ev==='dragleave' && e.relatedTarget) return; drop.classList.remove('sobre'); }));
document.addEventListener('drop', e => { if(e.dataTransfer?.files?.length){ e.preventDefault(); subir(e.dataTransfer.files); }});

