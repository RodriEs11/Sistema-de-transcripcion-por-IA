// Preferencias que siguen al transcriptor (no a la PC) y salir de la sesión.
/* ------------------------------------------------ preferencias que siguen al transcriptor (no a la PC) */
const PREF_SYNC = /^(pref_[A-Za-z0-9_]{1,40}|tema|listaOculta|velUltima|barraFormatoOculta|zoomVp|anchoLista|anchoLista2|propInforme|filtroCasos)$/;
function prefsLocales(){
  const o = {};
  try { for(const k of Object.keys(localStorage)) if(PREF_SYNC.test(k)) o[k] = localStorage.getItem(k); } catch(e){}
  return o;
}
const firmaPrefs = o => JSON.stringify(Object.keys(o).sort().map(k => [k, o[k]]));
let prefsEnviadas = null;
function prefsDelServidor(srv){
  if(srv == null){ prefsEnviadas = ''; return false; }    // nunca guardó: se suben las de esta PC
  const loc = prefsLocales();
  prefsEnviadas = firmaPrefs(srv);
  if(firmaPrefs(loc) === prefsEnviadas) return false;
  const marca = 'prefsDe:' + MI.usuario.clave + ':' + prefsEnviadas.length;
  try { if(sessionStorage.getItem('prefsAplicadas') === marca) return false; sessionStorage.setItem('prefsAplicadas', marca); } catch(e){ return false; }
  try { Object.keys(loc).forEach(k => localStorage.removeItem(k)); Object.entries(srv).forEach(([k, v]) => localStorage.setItem(k, v)); } catch(e){ return false; }
  location.reload();
  return true;
}
async function subirPrefs(beacon){
  if(!MI.usuario || prefsEnviadas === null) return;
  const o = prefsLocales(), f = firmaPrefs(o);
  if(f === prefsEnviadas) return;
  const cuerpo = JSON.stringify({preferencias: o});
  if(beacon){ try { navigator.sendBeacon('/api/usuario/preferencias', new Blob([cuerpo], {type: 'application/json'})); prefsEnviadas = f; } catch(e){} return; }
  try { await api('/api/usuario/preferencias', {preferencias: o}); prefsEnviadas = f; } catch(e){}
}
setInterval(() => subirPrefs(false), 5000);
addEventListener('pagehide', () => subirPrefs(true));
/* La app del trabajo la llama al cerrar su ventana (VentanaPrincipal.CerrarSesionUsuario): cierra el estudio abierto
   guardando sus cambios y después la sesión del transcriptor, para que el siguiente entre con su usuario.
   Devuelve true (en el momento) si había una sesión de transcriptor que cerrar. */
window.salirDeSesion = function(opciones){
  if(!MI.usuario) return false;
  if(opciones && opciones.navegar === false){      // la app se cierra: avisar al Servidor sin cambiar de pantalla
    subirPrefs(true);
    try { fetch('/salir', {keepalive: true, credentials: 'same-origin', redirect: 'manual', cache: 'no-store'}); } catch(e){}
    return true;
  }
  (async () => {
    if(actual){ const ok = await cerrarCaso(true); if(ok === false || actual) return; }
    await subirPrefs(false);
    location.href = '/salir';
  })();
  return true;
};
