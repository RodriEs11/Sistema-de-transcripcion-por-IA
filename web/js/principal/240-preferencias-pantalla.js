// Preferencias de la pantalla (en esta PC) y ocultar la lista.
/* ================================================ preferencias de la pantalla (se guardan en esta PC)
   En la app quedan en el perfil de WebView2 de cada usuario de Windows; en el navegador, en ese navegador. */
const PREF = {
  leer: k => leerLS('pref_' + k),
  poner(k, v){ grabarLS('pref_' + k, v); aplicarPrefs(); },
  salto: () => +PREF.leer('salto') || 3,
  retroceso: () => { const v = PREF.leer('retroceso'); return v === '' ? 1 : +v; },
  explicar: () => PREF.leer('explicar') !== 'no',
};
function aplicarPrefs(){
  for(const k of ['leyenda', 'atajos', 'letra']){ const v = PREF.leer(k); if(v) document.body.dataset[k] = v; else delete document.body.dataset[k]; }
  const s = PREF.salto();
  $('#bAtras').textContent = '−' + s + 's'; $('#bAtras').title = `Atrás ${s} segundos`;
  $('#bAdel').textContent = '+' + s + 's'; $('#bAdel').title = `Adelante ${s} segundos`;
  document.querySelectorAll('.salto-txt').forEach(x => x.textContent = s);
  actualizarAtajos();
  $('#seguir').checked = PREF.leer('seguir') !== 'no';
  requestAnimationFrame(() => { ajustarBarra(); dibujarOnda(); });
}
$('#seguir').addEventListener('change', e => { grabarLS('pref_seguir', e.target.checked ? '' : 'no'); pintarConfig(); });
{ const v = PREF.leer('velInicial') || leerLS('velUltima');
  if(v && [...$('#vel').options].some(o => o.value === v)) $('#vel').value = v; }
iniciarVolumen();                                   // el volumen guardado en esta PC (100 % si nunca se cambió)

/* ================================================ ocultar / mostrar la lista de informes */
const listaOculta = () => leerLS('listaOculta') === '1';
function aplicarLista(){
  const ocultar = listaOculta() && !esCompacto();
  document.querySelector('.app').classList.toggle('plegada', ocultar);
  $('#bOcultarLista').setAttribute('aria-expanded', String(!ocultar));
  $('#bMostrarLista').setAttribute('aria-expanded', String(!ocultar));
  if(typeof pintarConfig === 'function' && !$('#config').hidden) pintarConfig();
  requestAnimationFrame(() => { ajustarBarra(); dibujarOnda(); });
}
function ponerLista(mostrar){
  grabarLS('listaOculta', mostrar ? '' : '1'); ocultarExplica(); aplicarLista();
  (mostrar ? $('#bOcultarLista') : $('#bMostrarLista')).focus({preventScroll: true});
}
function actualizarRiel(lista){
  const n = (lista || []).filter(c => c.estado === 'listo').length, b = $('#rielPend');
  b.hidden = !n; b.textContent = n;
  b.title = n === 1 ? '1 informe para revisar' : n + ' informes para revisar';
}
$('#bOcultarLista').onclick = () => ponerLista(false);
$('#bMostrarLista').onclick = () => ponerLista(true);
$('#rielPend').onclick = () => ponerLista(true);

