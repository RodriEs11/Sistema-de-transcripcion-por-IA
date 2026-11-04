// Explicación de cada marca.
/* ================================================ explicación de cada marca */
const TIPOS = {
  'm-numero':   ['No coincide con el dictado', 'var(--rojo-f)'],
  'm-completar':['Falta completar', 'var(--rojo-f)'],
  'm-dudoso':   ['Dudoso', 'var(--amar-f)'],
  'm-bajaconf': ['Whisper no estaba seguro', 'var(--amar-f)'],
  'm-verificar':['No dictado junto al hallazgo', 'var(--turq)'],
  'l-verificar':['Línea que no está en el dictado', 'var(--turq)'],
  'l-plantilla':['Frase de plantilla no dictada', 'var(--gris)']};
function tipoDe(el){ return Object.keys(TIPOS).find(k => el.classList.contains(k)); }
function resaltarMotivo(m){   // "Dictado: 12 / Informe: 2" -> los valores en negrita
  return esc(m).replace(/(Dictado|Informe): (.+?)(?= \/| ·| \(|\. |\.$|$)/g, '$1: <b>$2</b>');
}
function fragmentoDictado(el, k){
  if(!palabras.length) return '';
  const origen = typeof origenMarcaWord === 'function' ? (origenMarcaWord(el) || el) : el;
  const ln = origen.closest('.ln'), r = ln ? rangoDe(ln) : null, t = origen.dataset.t ? +origen.dataset.t : null;
  let a, b, claves = null;
  if(r){ a = Math.max(0, r[0]-4); b = Math.min(palabras.length-1, r[1]+4); claves = r[2]; }
  else if(t != null){
    a = palabras.findIndex(w => w.ini >= t - 1.5); if(a < 0) return '';
    b = a; while(b+1 < palabras.length && palabras[b+1].ini <= t + 3.5) b++;
  } else return k==='l-plantilla' ? '' : '<i>No encontré esta parte en el dictado: escuchá el audio.</i>';
  if(b - a > 30) b = a + 30;
  const txt = palabras.slice(a, b+1).map((w, j) => claves && claves.has(a+j) ? '<b>'+esc(w.p.trim())+'</b>' : esc(w.p.trim())).join(' ');
  return `Dictado (${mmss(palabras[a].ini)}): «${a > 0 ? '… ' : ''}${txt}${b < palabras.length-1 ? ' …' : ''}»`;
}
function mostrarExplica(el, fija=false){
  const k = tipoDe(el); if(!k || (!editor.contains(el) && !el.closest('#vpHojas'))) return;
  const box = $('#explica'), [tit, color] = TIPOS[k];
  box.querySelector('.ex-tit i').style.background = color;
  box.querySelector('.ex-tit span').textContent = tit;
  box.querySelector('.ex-mot').innerHTML = resaltarMotivo(el.dataset.motivo || el.getAttribute('title') || '');
  const d = box.querySelector('.ex-dic'), frag = fragmentoDictado(el, k);
  d.innerHTML = frag; d.style.display = frag ? '' : 'none';
  explicaDe = el; explicaFija = fija;
  box.style.display = 'block'; ubicarExplica();
}
function ubicarExplica(){
  if(!explicaDe) return;
  const box = $('#explica'), r = explicaDe.getBoundingClientRect(), hw = (explicaDe.closest('#vpHojas') ? $('#vpHojas') : $('.hojawrap')).getBoundingClientRect();
  if(!explicaDe.isConnected || r.bottom < hw.top || r.top > hw.bottom){ box.style.display = 'none'; return; }
  box.style.display = 'block';
  const w = box.offsetWidth, h = box.offsetHeight;
  const x = Math.min(Math.max(8, explicaDe.tagName==='MARK' ? r.left - 8 : r.left + 14), innerWidth - w - 8);
  let y = r.bottom + 6; if(y + h > innerHeight - 8) y = Math.max(8, r.top - h - 6);
  box.style.left = x + 'px'; box.style.top = y + 'px';
}
function ocultarExplica(){ clearTimeout(tExplica); explicaDe = null; explicaFija = false; $('#explica').style.display = 'none'; }
$('.hojawrap').addEventListener('scroll', () => explicaDe && ubicarExplica(), {passive:true});
addEventListener('resize', () => explicaDe && ubicarExplica());
const marcaBajo = t => t.closest && (t.closest('mark') || t.closest('.ln[data-linea]'));
editor.addEventListener('mouseover', e => {
  const el = marcaBajo(e.target);
  if(!el || !editor.contains(el) || el === explicaDe || (explicaFija && explicaDe)) return;
  if(!PREF.explicar()) return;                     // Configuración: explicación solo con F2
  clearTimeout(tExplica);
  tExplica = setTimeout(() => mostrarExplica(el, false), el.tagName==='MARK' ? 250 : 600);
});
editor.addEventListener('mouseout', e => {
  const el = marcaBajo(e.target); if(!el || (e.relatedTarget && el.contains(e.relatedTarget))) return;
  clearTimeout(tExplica); if(!explicaFija && explicaDe === el) ocultarExplica();
});
document.addEventListener('mousedown', e => {
  if(explicaFija && explicaDe && !explicaDe.contains(e.target) && !e.target.closest('#explica,#bSig,#bAcep,.player,.onda')) ocultarExplica();
});
/* borrador guardado con la versión anterior (el motivo estaba en title) */
function adaptarBorrador(){
  editor.querySelectorAll('mark[title], .ln[data-linea][title]').forEach(x => {
    if(!x.dataset.motivo) x.dataset.motivo = x.title; x.removeAttribute('title'); });
  editor.querySelectorAll('.activa, .sonando').forEach(x => x.classList.remove('activa', 'sonando'));
}
function htmlLimpio(){
  const c = editor.cloneNode(true);
  c.querySelectorAll('.activa, .sonando').forEach(x => x.classList.remove('activa', 'sonando'));
  return c.innerHTML;
}

