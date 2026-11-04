// Sincronización informe <-> dictado.
/* ================================================ sincronización informe <-> dictado */
// Cada línea del informe se ubica en el dictado buscando el tramo con más palabras y números en común.
const STOP_AL = new Set(('dimensiones uterinas longitudinal anteroposterior transverso transversal endometrio espesor ' +
  'ovario derecho izquierdo mide lobulo istmo categorizacion conjunta central ecogenico como para sobre entre desde ' +
  'hasta este esta estos estas tiene presenta pero porque cual cuales donde cuando nivel ambas ambos').split(' '));
const sinAcentosL = t => t.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
function clavesDe(texto){
  let t = sinAcentosL(texto).replace(/\[completar:?|\[\[\??/g, ' ').replace(/\]+/g, ' ').replace(/\bbi-?rads?\b/g, 'birads');
  t = t.replace(/(\d),(\d)/g, '$1.$2').replace(/\b([hcdlst])\s*(\d{1,2})\b/g, '$1$2')
       .replace(/\b([cdls]\d{1,2})\s*[-,]?\s*([cdls]\d{1,2})\b/g, '$1$2');
  const nums = t.match(/(?<![a-z0-9.])\d+(?:\.\d+)?|\b[hcdlst]\d{1,2}(?:[cdls]\d{1,2})?\b/g) || [];
  const pals = (t.match(/[a-z]{4,}/g) || []).filter(p => !STOP_AL.has(p));
  return [...new Set(nums)].map(x => [x, 2]).concat([...new Set(pals)].map(p => [p, 1]));
}
function tokCodigo(i){   // Whisper da "hora" y "12" como dos palabras: se juntan en "h12"
  if(!codTok){
    const L = {hora:'h', horas:'h', hache:'h', h:'h', ele:'l', l:'l', ese:'s', s:'s', ce:'c', c:'c', d:'d'};
    codTok = palabras.map((w, j) => { const sig = palabras[j+1];
      if(L[w.n] && sig && /^\d{1,2}$/.test(sig.n)) return L[w.n] + sig.n;
      return /^[hcdlst]\d{1,2}([cdls]\d{1,2})?$/.test(w.n || '') ? w.n : null; });
  }
  return codTok[i];
}
function parecido(a, b){   // 0..1 (distancia de edición)
  const m = a.length, n = b.length; let prev = Array.from({length:n+1}, (_, j) => j);
  for(let i=1; i<=m; i++){ const cur = [i];
    for(let j=1; j<=n; j++) cur[j] = Math.min(prev[j]+1, cur[j-1]+1, prev[j-1] + (a[i-1]===b[j-1] ? 0 : 1));
    prev = cur; }
  return 1 - prev[n] / Math.max(m, n, 1);
}
function igual(c, i){
  const t = palabras[i].n || '';
  if(/^\d/.test(c)) return c === t;
  if(/^[hcdlst]\d/.test(c)){ const k = tokCodigo(i); return !!k && (k === c || (c.length > 3 && c.startsWith(k))); }
  if(c === 'birads') return /^(bi?rr?ads?|birra|vrads?)/.test(t) || t === 'ponemos';   // "le ponemos un 2", "un birrastre"
  if(t.length < 4 || !/^[a-z]+$/.test(t)) return false;
  if(c.length >= 5 && t.length >= 5){ if(c.slice(0,5) === t.slice(0,5)) return true; }
  else if(c === t) return true;
  return c.slice(0,2) === t.slice(0,2) && Math.abs(c.length - t.length) <= 3 && parecido(c, t) >= 0.8;
}
function alinear(texto){
  if(cacheRango.has(texto)) return cacheRango.get(texto);
  const claves = clavesDe(texto); let res = null;
  if(claves.length && palabras.length){
    const pos = new Map();
    for(let i=0; i<palabras.length; i++) for(let k=0; k<claves.length; k++)
      if(igual(claves[k][0], i)){ if(!pos.has(i)) pos.set(i, new Set()); pos.get(i).add(k); }
    const idx = [...pos.keys()].sort((x, y) => x - y), ancho = Math.max(12, 3 * claves.length);
    let mejor = null;
    for(let s=0; s<idx.length; s++){
      const a = idx[s], vistos = new Set();
      for(let q=s; q<idx.length; q++){
        const j = idx[q]; if(j - a > ancho) break;
        pos.get(j).forEach(k => vistos.add(k));
        let sc = 0; vistos.forEach(k => sc += claves[k][1]);
        if(!mejor || sc > mejor.sc || (sc === mejor.sc && j - a < mejor.b - mejor.a)) mejor = {sc, a, b: j};
      }
    }
    const total = claves.reduce((x, c) => x + c[1], 0);
    if(mejor && mejor.sc >= Math.min(2, total)){
      const marc = new Set(idx.filter(j => j >= mejor.a && j <= mejor.b));
      res = [mejor.a, mejor.b, marc];
    }
  }
  if(cacheRango.size > 400) cacheRango.clear();
  cacheRango.set(texto, res); return res;
}
function rangoDe(ln){ const t = ln.textContent.trim(); return t ? alinear(t) : null; }
function reiniciarSync(){
  cacheRango = new Map(); lineaCursor = null; rangoCursor = null; lineaSonando = null; codTok = null;
  $('#lineaInfo').innerHTML = '';
}
let rafSel = 0;
document.addEventListener('selectionchange', () => { if(!actual) return; cancelAnimationFrame(rafSel); rafSel = requestAnimationFrame(seguirCursor); });
function seguirCursor(){
  const s = getSelection(); if(!s.rangeCount) return;
  const n = s.anchorNode, el = n && (n.nodeType===1 ? n : n.parentElement);
  if(!el) return;
  const ln = el.closest('#vpHojas') ? lineaOrigenWord(+el.closest('p[data-k]')?.dataset.k) : el.closest('.ln');
  if(!ln || (!editor.contains(ln))) return;
  const r = rangoDe(ln);
  if(ln === lineaCursor && r === rangoCursor) return;
  lineaCursor = ln; pintarEco(r);
}
function pintarEco(r){
  dict.querySelectorAll('.eco').forEach(x => x.classList.remove('eco'));
  rangoCursor = r; const info = $('#lineaInfo');
  if(!r){ info.textContent = lineaCursor && lineaCursor.textContent.trim() ? '· la línea del cursor no está en el dictado' : ''; dibujarOnda(); return; }
  for(let i=r[0]; i<=r[1]; i++) dict.children[i]?.classList.add('eco');
  info.innerHTML = `· línea del cursor: ${mmss(palabras[r[0]].ini)} <button class="chico" title="Escuchar esta parte (también Alt+clic en la línea)">▶</button>`;
  info.querySelector('button').onclick = () => escuchar(palabras[r[0]].ini);
  if(audio.paused || !$('#seguir').checked){
    const sp = dict.children[r[0]];
    if(sp){ const a = sp.getBoundingClientRect(), c = dict.getBoundingClientRect();
      if(a.top < c.top + 10 || a.bottom > c.bottom - 10) sp.scrollIntoView({block:'center', behavior:'smooth'}); }
  }
  dibujarOnda();
}
function marcarLineaSonando(i){     // mientras suena el audio se marca la línea del informe que le corresponde
  if(i < 0) return;
  let mejor = null, ancho = 1e9;
  for(const ln of editor.querySelectorAll('.ln')){
    const r = rangoDe(ln); if(r && i >= r[0] && i <= r[1] && r[1] - r[0] < Math.min(ancho, 40)){ mejor = ln; ancho = r[1] - r[0]; } }
  // entre dos líneas queda marcada la última que sonó
  if(mejor && mejor !== lineaSonando){ lineaSonando?.classList.remove('sonando'); lineaSonando = mejor; mejor.classList.add('sonando'); }
  if(typeof marcarSonandoWord === 'function') marcarSonandoWord(lineaSonando);
}

