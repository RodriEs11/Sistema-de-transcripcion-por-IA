// Lista de informes y filtro.
/* ------------------------------------------------ lista */
const TACHO = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 7h16M10 11v6M14 11v6M5 7l1 12a2 2 0 0 0 2 2h8a2 2 0 0 0 2-2l1-12M9 7V4h6v3"/></svg>';
const ETIQ = {nuevo:'nuevo', 'en cola':'en cola', transcribiendo:'transcribiendo', 'en pausa':'en pausa', generando:'generando', listo:'para revisar', revisado:'revisado', error:'error'};
/* pausa de la transcripción: solo en la PC del servidor (el servidor manda puede_pausar / puede_reanudar) */
const ICO_PAUSA = '<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><rect x="6" y="4.5" width="4.2" height="15" rx="1.2"/><rect x="13.8" y="4.5" width="4.2" height="15" rx="1.2"/></svg>';
const ICO_SEGUIR = '<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M7 4.8v14.4a1 1 0 0 0 1.5.86l11.6-7.2a1 1 0 0 0 0-1.72L8.5 3.94A1 1 0 0 0 7 4.8z"/></svg>';
function botonPausa(c){         // "Pausar" / "Reanudar" / "Cancelar pausa" (null si no corresponde)
  if(!c.puede_pausar && !c.puede_reanudar) return null;
  const rean = !!c.puede_reanudar, b = document.createElement('button');
  b.type = 'button'; b.className = 'chico bpausa';
  b.innerHTML = (rean ? ICO_SEGUIR : ICO_PAUSA) + (rean ? (c.pausa_pedida ? 'Cancelar pausa' : 'Reanudar') : 'Pausar');
  b.title = rean ? (c.pausa_pedida ? 'Todavía no se detuvo: sigue transcribiendo como si nada.' : 'Sigue transcribiendo desde donde quedó.')
                 : 'Detiene la transcripción al terminar el tramo que está transcribiendo (unos segundos). Lo transcrito se conserva y los audios que siguen en la cola esperan hasta que la reanudes.';
  b.onclick = ev => { ev.stopPropagation(); pausarCaso(c.nombre, !rean, b); };
  return b;
}
async function pausarCaso(n, pausar, boton){
  if(boton) boton.disabled = true;
  try { const r = await api(pausar ? '/api/caso/pausar' : '/api/caso/reanudar', {nombre: n}); if(r.msg) toast(r.msg, [], 5000); }
  catch(e){ toast(e instanceof SinConexion ? 'Sin conexión con el servidor.' : e.message); }
  cargarLista();
}
/* PC desde la que se usa la página: "Servidor" en esta PC, info-01... por el túnel */
let MI = {pc:'Servidor', remoto:false, usuario:null, con_usuarios:false};
let filtro = (()=>{ try { return localStorage.getItem('filtroCasos') || ''; } catch(e){ return ''; } })();
function ponerFiltro(f){ filtro = f; try { localStorage.setItem('filtroCasos', f); } catch(e){}
  $('#tabMia').classList.toggle('on', f==='mia'); $('#tabTodas').classList.toggle('on', f!=='mia'); cargarLista(); }
async function cargarMiPc(){
  try { MI = await api('/api/mi_pc'); } catch(e){ return; }
  $('#tabMia').textContent = 'Esta PC';
  if(MI.remoto){ document.title = 'Informes · ' + MI.pc; }
  ponerFiltro(filtro || (MI.remoto ? 'mia' : 'todas'));
  $('#bAdmin').hidden = !!MI.remoto && !MI.admin;   // en el trabajo, solo si el panel está habilitado (pide su contraseña)
  if(typeof cargarMedicos === 'function') cargarMedicos();
  if(MI.con_usuarios && !MI.usuario){ location.href = '/entrar'; return; }
  $('#quien').hidden = !MI.usuario; $('#quienNom').textContent = MI.usuario ? MI.usuario.nombre : '';
  document.querySelectorAll('.solo-usuario').forEach(x => x.hidden = !MI.usuario);
  document.querySelectorAll('#config .cfg-tabs [data-tab=cuenta]').forEach(x => x.hidden = !MI.usuario);
  if(MI.usuario){
    document.title = 'Informes · ' + MI.usuario.nombre + (MI.remoto ? ' · ' + MI.pc : '');
    if(prefsDelServidor(MI.preferencias)) return;            // recarga con las preferencias de este usuario
    if(MI.usuario.cambiar) setTimeout(() => abrirConfig('cuenta'), 300);
  }
}
