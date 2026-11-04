// Vistas de la pantalla.
/* ------------------------------------------------ vistas */
function mostrar(v){
  cerrarMedicosCaso();
  $('#vacio').hidden = v!=='vacio';
  for(const [id,k] of [['#caso','caso'],['#vPlant','plant'],['#vMed','med'],['#vVoces','voces']]){ const el=$(id); el.hidden = v!==k; el.style.display = v===k ? 'flex' : 'none'; }
  if(v!=='med' && v!=='voces') pararMuestra();
  if(v!=='caso' && typeof ocultarEditorWord === 'function') ocultarEditorWord();
  if(v==='vacio' && typeof cargarLista === 'function'){ vacioHtml = ''; cargarLista(); }   // la pantalla vacía se arma con la lista
  for(const [id,k] of [['#bInicio','vacio'],['#bVerPlant','plant'],['#bVerMed','med']]){
    const b = $(id); if(b){ b.classList.toggle('on', v===k); if(v===k) b.setAttribute('aria-current', 'page'); else b.removeAttribute('aria-current'); } }
}
mostrar('vacio');

