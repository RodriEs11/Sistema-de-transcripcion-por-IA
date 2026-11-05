// Configuración.
/* ================================================ configuración
   Pantalla y Audio: preferencias de esta página (PREF). Esta PC y Conexión: las guarda la aplicación del trabajo;
   la app manda su estado con ponerConfigApp() / abrirConfiguracion() y recibe los cambios con
   postMessage({accion:'cfg', que, valor}). En el navegador (o con una app vieja) esas secciones no aparecen. */
const CFG = {app: null, tab: 'pantalla', previo: null};
function hacerApp(que, valor){ if(EN_APP) try { chrome.webview.postMessage({accion: 'cfg', que, valor}); } catch(e){} }
function mostrarGuardado(){ const g = $('#cfgGuardado'); g.classList.add('ver'); clearTimeout(g._t); g._t = setTimeout(() => g.classList.remove('ver'), 1400); }
function elegirTab(t){
  const tabs = [...document.querySelectorAll('.cfg-tabs [role=tab]')].filter(b => !b.hidden);
  if(!tabs.some(b => b.dataset.tab === t)) t = 'pantalla';
  CFG.tab = t;
  for(const b of document.querySelectorAll('.cfg-tabs [role=tab]')){
    const si = b.dataset.tab === t; b.setAttribute('aria-selected', String(si)); b.tabIndex = si ? 0 : -1; }
  document.querySelectorAll('.cfg-panel').forEach(p => p.hidden = p.dataset.panel !== t);
  $('.cfg-paneles').scrollTop = 0;
}
function pintarConfig(){
  const A = CFG.app;
  document.querySelectorAll('#config .solo-app').forEach(x => x.hidden = !A);
  $('#cfgSub').textContent = (MI.usuario ? '· ' + MI.usuario.nombre + ' ' : '') + (A ? '· ' + A.pc : MI.remoto ? '· ' + MI.pc : '· PC del servidor');
  $('#cfgNota').textContent = MI.usuario ? 'Los cambios se guardan solos en tu usuario: los tenés en cualquier PC.' : 'Los cambios se guardan solos en esta PC.';
  $('#cuentaCambiar').hidden = !(MI.usuario && MI.usuario.cambiar);
  // pantalla y audio
  const tema = leerLS('tema');
  document.querySelectorAll('#config .segm').forEach(g => {
    const v = g.dataset.pref === 'tema' ? (tema === 'dark' || tema === 'light' ? tema : '') : PREF.leer(g.dataset.pref);
    g.querySelectorAll('button').forEach(b => b.setAttribute('aria-checked', String(b.dataset.v === v)));
  });
  document.querySelectorAll('#config select[data-pref]').forEach(s => s.value = PREF.leer(s.dataset.pref));
  document.querySelectorAll('#config [data-pref-si]').forEach(c => c.checked = PREF.leer(c.dataset.prefSi) !== 'no');
  $('#cfgLista').checked = !listaOculta(); $('#cfgLista').disabled = esCompacto();
  $('#cfgFilaAdmin').hidden = $('#bAdmin').hidden;
  if(!A) return;
  // aplicación del trabajo
  document.querySelectorAll('#config [data-app]').forEach(c => { c.checked = !!A[c.dataset.app]; const f = c.closest('.cfg-fila'); if (f) f.hidden = !(c.dataset.app in A); });
  $('#cfgCarpetaAudios').textContent = 'Los que el sistema de gestión deja en ' + (A.carpetaAudios || 'la carpeta temporal') + '.';
  $('#cfgCompacto').textContent = A.compacto ? 'Volver al tamaño normal' : 'Pasar a modo compacto';
  $('#cfgCarpetaWord').textContent = A.carpetaWord || '—';
  $('#cfgWordDefecto').hidden = !A.wordPropia;
  const pend = A.pendientes || 0, cp = $('#cfgPendientes');
  cp.textContent = pend ? (pend === 1 ? '1 audio guardado en esta PC' : pend + ' audios guardados en esta PC') + ', esperando para enviarse.'
                        : 'Qué audios se tomaron y se enviaron, y los errores. No queda ninguno por enviar.';
  cp.className = pend ? 'mal' : '';
  const ac = A.autoc || {}, ca = $('#cfgAutoc');
  ca.textContent = ac.error ? ac.error : (ac.n || 0) + ' entradas con formato del Normal.dotm de esta PC.';
  ca.className = ac.error ? 'mal' : '';
  $('#cfgServidor').textContent = A.servidor || 'Sin dirección';
  $('#cfgEstadoSrv').textContent = A.estado || ''; $('#cfgEstadoSrv').className = A.conectado ? 'bien' : 'mal';
  $('#cfgPc').textContent = 'Conectada como ' + A.pc + '. Si se desconecta, hay que volver a escribir la contraseña.';
  $('#cfgVersion').textContent = 'Versión ' + A.version + (A.actualizacion ? ' · hay una versión nueva (' + A.actualizacion + ') lista para instalar' : ' · al día');
  $('#cfgActualizar').hidden = !A.actualizacion;
  $('#cfgActualizar').textContent = A.actualizacion ? 'Actualizar a la ' + A.actualizacion : 'Actualizar ahora';
}
function abrirConfig(tab, pedirEstado = true){
  cerrarMas(); cerrarAyuda(); ocultarExplica();
  if(EN_APP && pedirEstado) try { chrome.webview.postMessage({accion: 'configuracion'}); } catch(e){}
  const d = $('#config');
  if(d.hidden) CFG.previo = document.activeElement;
  pintarConfig(); elegirTab(tab || CFG.tab);
  d.hidden = false;
  const t = document.querySelector('.cfg-tabs [aria-selected=true]'); if(t) t.focus();
}
function cerrarConfig(){
  const d = $('#config'); if(d.hidden) return;
  if(MI.usuario && MI.usuario.cambiar){ elegirTab('cuenta'); $('#mcActual').focus(); toast('Primero elegí tu contraseña.'); return; }
  d.hidden = true;
  try { CFG.previo && CFG.previo.focus && CFG.previo.focus({preventScroll: true}); } catch(e){}
}
window.abrirConfiguracion = function(estado, tab){       // la app la llama desde Opciones → Configuración…
  if(estado) CFG.app = estado;
  abrirConfig(tab, !estado);
  return true;
};
window.ponerConfigApp = function(estado){ CFG.app = estado || null; if(!$('#config').hidden){ pintarConfig(); elegirTab(CFG.tab); } };
$('#bConfig').onclick = () => abrirConfig();
$('#rielConfig').onclick = () => abrirConfig();
$('#cfgX').onclick = cerrarConfig; $('#cfgListo').onclick = cerrarConfig;
$('#config').addEventListener('mousedown', e => { if(e.target === $('#config')) cerrarConfig(); });
document.querySelectorAll('.cfg-tabs [role=tab]').forEach(b => b.onclick = () => elegirTab(b.dataset.tab));
$('.cfg-tabs').addEventListener('keydown', e => {
  if(!['ArrowDown', 'ArrowUp', 'ArrowLeft', 'ArrowRight'].includes(e.key)) return;
  e.preventDefault();
  const tabs = [...document.querySelectorAll('.cfg-tabs [role=tab]')].filter(b => !b.hidden), i = tabs.findIndex(b => b.dataset.tab === CFG.tab);
  const j = (i + (e.key === 'ArrowDown' || e.key === 'ArrowRight' ? 1 : tabs.length - 1)) % tabs.length;
  elegirTab(tabs[j].dataset.tab); tabs[j].focus();
});
document.addEventListener('keydown', e => {          // con la configuración abierta no actúan los atajos del informe
  if($('#config').hidden || $('#confirma').classList.contains('abierto') || !$('#reglasDlg').hidden) return;
  if(e.key === 'Escape'){ e.preventDefault(); e.stopPropagation(); cerrarConfig(); return; }
  if(e.key === 'Tab'){
    const foc = [...$('#config').querySelectorAll('button,select,input')].filter(x => !x.disabled && x.offsetParent && x.tabIndex !== -1);
    const i = foc.indexOf(document.activeElement);
    if(e.shiftKey && i <= 0){ e.preventDefault(); foc[foc.length - 1].focus(); }
    else if(!e.shiftKey && i === foc.length - 1){ e.preventDefault(); foc[0].focus(); }
  }
}, true);
// controles de Pantalla y Audio
document.querySelectorAll('#config .segm').forEach(g => g.addEventListener('click', e => {
  const b = e.target.closest('button'); if(!b) return;
  if(g.dataset.pref === 'tema'){
    if(b.dataset.v){ document.documentElement.dataset.theme = b.dataset.v; grabarLS('tema', b.dataset.v); }
    else { delete document.documentElement.dataset.theme; try { localStorage.removeItem('tema'); } catch(e){} }
    aplicarTema();
  } else PREF.poner(g.dataset.pref, b.dataset.v);
  pintarConfig(); mostrarGuardado();
}));
document.querySelectorAll('#config select[data-pref]').forEach(s => s.onchange = () => {
  PREF.poner(s.dataset.pref, s.value);
  if(s.dataset.pref === 'velInicial' && s.value){ $('#vel').value = s.value; audio.playbackRate = +s.value; }
  mostrarGuardado();
});
document.querySelectorAll('#config [data-pref-si]').forEach(c => c.onchange = () => { PREF.poner(c.dataset.prefSi, c.checked ? '' : 'no'); mostrarGuardado(); });
$('#cfgLista').onchange = e => { grabarLS('listaOculta', e.target.checked ? '' : '1'); aplicarLista(); mostrarGuardado(); };
$('#cfgPaneles').onclick = () => {
  [$('#divLista'), $('#divCols'), document.querySelector('.div-lista2')].forEach(d => d && d.dispatchEvent(new Event('dblclick')));
  mostrarGuardado(); toast('Los paneles volvieron al tamaño original.');
};
$('#cfgAyuda').onclick = () => { cerrarConfig(); abrirAyuda($('#caso').hidden ? document.body : null); };
$('#cfgAdmin').onclick = () => { cerrarConfig(); $('#bAdmin').click(); };
$('#cfgOriginal').onclick = async () => {
  if(!await confirmar('¿Volver a la configuración original de la pantalla?',
      '<p>Tema, tamaño del texto, lista, anchos de los paneles y opciones del audio vuelven a como venían. No se toca ningún informe.</p>', 'Restablecer', 'prim')) return;
  try { Object.keys(localStorage).filter(k => k.startsWith('pref_')).forEach(k => localStorage.removeItem(k));
        ['tema', 'listaOculta', 'velUltima', 'barraFormatoOculta', 'volumen', 'volumenAntes'].forEach(k => localStorage.removeItem(k)); } catch(e){}
  delete document.documentElement.dataset.theme;
  $('#vel').value = '1'; audio.playbackRate = 1;
  volumenAntes = 100; ponerVolumen(100, false);
  $('#cfgPaneles').onclick();
  aplicarTema(); aplicarPrefs(); aplicarLista(); aplicarBarraFormato(); pintarConfig(); mostrarGuardado();
};
// controles de la aplicación del trabajo
document.querySelectorAll('#config [data-app]').forEach(c => c.onchange = () => { hacerApp(c.dataset.app, c.checked); mostrarGuardado(); });
document.querySelectorAll('#config [data-app-accion]').forEach(b => b.onclick = () => {
  const que = b.dataset.appAccion;
  if(que === 'compacto' || que === 'recargar' || que === 'actualizar') cerrarConfig();
  hacerApp(que, true);
});
$('#cfgDireccion').onclick = async () => {
  const v = await pedirTexto({titulo: 'Dirección del Servidor', html: '<p>Pegá la dirección que muestra la ventana del Servidor (termina en <b>devtunnels.ms</b> o en <b>trycloudflare.com</b>).</p>',
    etiqueta: 'Dirección', valor: (CFG.app && CFG.app.servidor) || '', placeholder: 'https://…devtunnels.ms', boton: 'Conectar',
    validar: t => /^(https?:\/\/)?([\w-]+(\.[\w-]+)*\.[a-z]{2,}|localhost|\d{1,3}(\.\d{1,3}){3})(:\d{1,5})?(\/\S*)?$/i.test(t) ? ''
      : 'No parece una dirección. Copiala completa, por ejemplo https://algo-8766.brs.devtunnels.ms o http://127.0.0.1:8865'});
  if(v) { hacerApp('direccion', v); toast('Probando la dirección nueva…'); }
};
$('#cfgDesvincular').onclick = async () => {
  if(!await confirmar('¿Desconectar esta PC del Servidor?',
      '<p>Esta PC deja de estar autorizada y vas a tener que volver a escribir la contraseña para usarla.</p>', 'Desconectar')) return;
  cerrarConfig(); hacerApp('desvincular', true);
};
aplicarPrefs(); aplicarLista();

