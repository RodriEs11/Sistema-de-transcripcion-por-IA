// Elementos de la pantalla, estado global y utilidades (api, toast, confirmar…).
const $ = s => document.querySelector(s);
const audio = $('#audio'), editor = $('#editor'), dict = $('#dictado');
let omis = [], omisOk = [];
let actual = null, palabras = [], activa = null, tBorrador = null, ultimaPausa = 0, casosCache = [];
let explicaDe = null, explicaFija = false, tExplica = null;                 // explicación de la marca
let onda = null, rafOnda = 0;                                               // forma de onda
let cacheRango = new Map(), lineaCursor = null, rangoCursor = null, lineaSonando = null, codTok = null;  // sincronización

/* ------------------------------------------------ util */
const esc = s => s.replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
/* Servidor en Linux o en Windows: nombres de sus scripts (.sh / .bat) en los textos */
let ES_LINUX = /Linux|X11|CrOS/.test(navigator.userAgent) && !/Android|Windows/.test(navigator.userAgent);
function deSistema(h){
  return ES_LINUX ? String(h).replace(/\b(iniciar_servidor|interfaz|configurar_acceso|configurar_tunel|instalar)\.bat\b/g, '$1.sh')
    .replace(/cloudflared\.exe/g, 'cloudflared').replace(/Abrí Ollama( \(el ícono de la llama\))?/g, 'Iniciá Ollama (sudo systemctl start ollama)') : h;
}
const mmss = t => isFinite(t) ? Math.floor(t/60)+':'+String(Math.floor(t%60)).padStart(2,'0') : '0:00';
/* Cuando el servidor no está, lo que responde no es del servidor: el túnel devuelve una página de error (HTML)
   o directamente no hay respuesta. Nunca se intenta leer eso como JSON: se convierte en un error claro. */
const MSG_SIN_CONEXION = 'Sin conexión con el servidor';
class SinConexion extends Error { constructor(){ super(MSG_SIN_CONEXION); this.sinConexion = true; } }
async function pedir(ruta, opciones){
  let r;
  try { r = await fetch(ruta, opciones); }
  catch(e){ throw new SinConexion(); }                            // sin red / el servidor no contesta
  const txt = await r.text().catch(() => '');
  let j = null;
  if((r.headers.get('content-type') || '').includes('json') || /^\s*[\[{]/.test(txt)) { try { j = JSON.parse(txt); } catch(e){} }
  if(j === null){
    // una página HTML o una respuesta vacía en lugar de los datos: es el túnel o un servidor caído (502, 503, 530...)
    if(!r.ok || /^\s*</.test(txt)) throw new SinConexion();
    j = {};
  }
  if(r.status===401 && j.entrar){ location.href = '/entrar'; throw new Error('Sesión vencida'); }
  if(!r.ok){ const e = new Error(j.error || ('Error '+r.status)); e.status = r.status; throw e; }
  return j;
}
function api(ruta, datos){
  return pedir(ruta, datos===undefined ? {} : {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(datos)});
}
function toast(msg, botones=[], ms=4500){
  $('#toastTxt').textContent = msg; const b = $('#toastBtns'); b.innerHTML='';
  botones.forEach(([t,f])=>{const x=document.createElement('button');x.className='chico';x.textContent=t;x.onclick=()=>{f();ocultar()};b.appendChild(x)});
  const el=$('#toast'); el.style.display='flex'; clearTimeout(el._t);
  const ocultar=()=>el.style.display='none'; if(ms) el._t=setTimeout(ocultar, ms);
}

