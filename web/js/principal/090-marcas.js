// Marcas del informe.
/* ------------------------------------------------ marcas */
const marcasPend = () => [...editor.querySelectorAll('mark, .ln[data-linea]')];
function actualizarPend(){
  const n = marcasPend().length + omis.filter(o => !omisOk.includes(o.dato)).length, p = $('#pend');
  // texto largo y corto: la barra usa el corto cuando no hay lugar (ver ajustarBarra)
  p.innerHTML = n ? `<span class="et-larga">${n} ${n===1?'marca pendiente':'marcas pendientes'}</span><span class="et-corta">${n} ${n===1?'marca':'marcas'}</span>`
                  : '<span class="et-larga">Sin marcas pendientes</span><span class="et-corta">Sin marcas</span>';
  p.title = n ? `${n} ${n===1?'marca pendiente':'marcas pendientes'} de revisar` : 'No quedan marcas por revisar';
  p.classList.toggle('cero', !n);
  dibujarOnda(); ajustarBarra();
}
function tiempoDe(el){
  if(el.dataset.t) return +el.dataset.t;
  const ln = el.closest('.ln'); return ln && ln.dataset.seg ? +ln.dataset.seg : null;
}
function escuchar(t){ if(t==null || !audio.src) return; audio.currentTime = Math.max(0, t-1); audio.play(); }
function seleccionar(el, sonar=true){
  if(activa) activa.classList.remove('activa');
  activa = el; el.classList.add('activa');
  if(typeof seleccionarMarcaWord === 'function' && seleccionarMarcaWord(el, sonar)) return;
  el.scrollIntoView({block:'center', behavior:'smooth'});
  const r = document.createRange(), s = getSelection();
  if(el.tagName==='MARK') r.selectNodeContents(el); else { r.setStart(el, 0); r.collapse(true); }
  editor.focus({preventScroll:true}); s.removeAllRanges(); s.addRange(r);
  if(sonar) escuchar(tiempoDe(el));
  setTimeout(() => { if(activa===el) mostrarExplica(el, true); }, 260);   // después del scroll suave
}
function siguiente(dir=1){
  const ms = marcasPend(); if(!ms.length){ toast('No quedan marcas pendientes.'); return; }
  let i = activa ? ms.indexOf(activa) : -1;
  if(i<0 && activa){ i = ms.findIndex(m => activa.compareDocumentPosition(m) & Node.DOCUMENT_POSITION_FOLLOWING) - (dir>0?1:0); }
  i = (i + dir + ms.length) % ms.length;
  seleccionar(ms[i]);
}
function resolver(el){
  if(!el) return;
  if(el.tagName==='MARK'){ const p = el.parentNode; while(el.firstChild) p.insertBefore(el.firstChild, el); p.removeChild(el); }
  else { el.classList.remove('l-plantilla','l-verificar','activa'); delete el.dataset.linea; delete el.dataset.motivo; el.removeAttribute('title'); }
  if(el===activa) activa = null;
  if(explicaDe===el) ocultarExplica();
  actualizarPend(); programarBorrador();
  if(typeof refrescarMarcasWord === 'function') refrescarMarcasWord();
}
function marcaEnCursor(){
  const s = getSelection(); if(!s.rangeCount) return null;
  const n = s.anchorNode, el = n && (n.nodeType===1 ? n : n.parentElement);
  if(el && el.closest('#vpHojas')) return origenMarcaWord(el.closest('[data-marca-word]'));
  if(!el || !editor.contains(el)) return null;
  return el.closest('mark') || el.closest('.ln[data-linea]');
}
function aceptar(){
  const el = (activa && editor.contains(activa)) ? activa : marcaEnCursor();
  if(!el){ toast('Poné el cursor sobre una marca (o usá ' + atajos.siguiente + ').'); return; }
  resolver(el); siguiente(1);
}
editor.addEventListener('click', e => {
  const m = e.target.closest('mark');
  if(e.altKey){ const ln = e.target.closest('.ln'); if(ln){ const r = rangoDe(ln); escuchar(r ? palabras[r[0]].ini : tiempoDe(ln)); } return; }
  if(m){ if(activa) activa.classList.remove('activa'); activa = m; m.classList.add('activa'); escuchar(tiempoDe(m)); }
});
editor.addEventListener('input', () => {
  if(explicaFija) ocultarExplica();
  const el = marcaEnCursor(); if(el) resolver(el);
  else { actualizarPend(); programarBorrador(); }
});
/* El editor de respaldo usa el mismo lector de formato que las hojas A4. */
function pareceTitulo(l){
  const x = (l || '').trim();
  if(!x || x.startsWith('-') || /[.:]$/.test(x) || x.length > 110) return false;
  const w = (sinAcentos(x.toLowerCase()).match(/[a-z]+/) || [''])[0];
  return (FORMATO.palabras_titulo || []).includes(w);
}
editor.addEventListener('paste', e => {
  e.preventDefault();
  const html = e.clipboardData.getData('text/html'), t = e.clipboardData.getData('text/plain');
  if(!html && !t) return;
  const pars = interpretarPegadoWord(html, t);
  document.execCommand('insertHTML', false, pars.map(p => {
    const el = parrafoVp(p); el.className = 'ln'; return el.outerHTML;
  }).join(''));
  actualizarPend(); programarBorrador();
});

