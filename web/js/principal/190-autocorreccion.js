// Autocorrección de Word (solo en la app del trabajo).
/* ================================================ autocorrección de Word (solo en la aplicación del trabajo)
   La aplicación lee el Normal.dotm de ESA PC y pasa sus entradas con ponerAutocorreccion(); la lista no va al
   Servidor. Se aplica solo a lo que se escribe a mano en el informe: al escribir el activador EXACTO (mayúsculas
   y minúsculas igual que en Word) y después espacio, Enter o un signo, se reemplaza por el texto de la entrada.
   Las negritas, colores y alineación de la entrada se agregan al formato del caso (como si se hubieran puesto
   en la vista previa F9), así que salen en el Word y en "Copiar para Word". Ctrl+Z enseguida vuelve a lo escrito. */
const AUTOC = {mapa: new Map(), deshacer: null};
const AUTOC_FIN = /^[ \u00A0.,;:!?)\]]$/;
window.ponerAutocorreccion = function(d){
  const m = new Map();
  for(const e of (d && d.entradas) || [])
    if(e && typeof e.g === 'string' && e.g && Array.isArray(e.p) && e.p.length) m.set(e.g, e.p);
  AUTOC.mapa = m;
};
if(EN_APP) try { chrome.webview.postMessage({accion:'autocorreccion'}); } catch(e){}
/* nodo de texto y posición para la letra n de un elemento */
function puntoTexto(el, n){
  const w = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
  let ult = null;
  for(let t; (t = w.nextNode());){ if(n <= t.data.length) return [t, n]; n -= t.data.length; ult = t; }
  return ult ? [ult, ult.data.length] : [el, 0];
}
function lineaAutoc(p){
  const d = document.createElement('div'); d.className = 'ln';
  if(p.a === 'center') d.classList.add('tit');
  if(p.t) d.appendChild(document.createTextNode(p.t)); else d.appendChild(document.createElement('br'));
  return d;
}
function autocorregir(tecla){
  const s = getSelection(); if(!s.rangeCount || !s.isCollapsed) return false;
  const r0 = s.getRangeAt(0), nodo = r0.startContainer;
  const ln = (nodo.nodeType === 1 ? nodo : nodo.parentElement)?.closest('.ln');
  if(!ln || ln.parentElement !== editor) return false;
  const antes = document.createRange(); antes.setStart(ln, 0); antes.setEnd(r0.startContainer, r0.startOffset);
  const txt = antes.toString();
  const m = /(?:^|[\s\u00A0])([^\s\u00A0]+)$/.exec(txt); if(!m) return false;
  const pars = AUTOC.mapa.get(m[1]); if(!pars) return false;          // tiene que ser igual, letra por letra
  AUTOC.deshacer = {html: editor.innerHTML, lin: [...editor.children].indexOf(ln), off: txt.length, tecla};
  // borrar el activador
  const [n0, o0] = puntoTexto(ln, txt.length - m[1].length);
  const rt = document.createRange(); rt.setStart(n0, o0); rt.setEnd(r0.startContainer, r0.startOffset);
  rt.deleteContents();
  // lo que había después del cursor en ese renglón
  const rr = document.createRange(); rr.setStart(rt.startContainer, rt.startOffset); rr.setEnd(ln, ln.childNodes.length);
  const cola = rr.extractContents();
  const colaTexto = (cola.textContent || '').replace(/\u00A0/g, ' ').trim() !== '';
  cola.querySelectorAll('br').forEach(b => b.remove());
  ln.querySelectorAll('br').forEach(b => b.remove());
  const prefijo = ln.textContent.replace(/\u00A0/g, ' ').trim() === '';
  // primer párrafo en el mismo renglón; los demás, renglones nuevos
  if(pars[0].t) ln.appendChild(document.createTextNode(pars[0].t));
  if(prefijo && pars[0].a === 'center') ln.classList.add('tit');
  let ult = ln;
  for(const p of pars.slice(1)){ const d = lineaAutoc(p); ult.after(d); ult = d; }
  if(ult !== ln) ult.querySelectorAll('br').forEach(b => b.remove());
  const cur = document.createRange();
  if(tecla === '\n'){
    const d = document.createElement('div'); d.className = 'ln';
    d.appendChild(cola); if(!d.textContent) d.appendChild(document.createElement('br'));
    ult.after(d); cur.setStart(d, 0);
  } else {
    const t = document.createTextNode(tecla === ' ' && !colaTexto ? '\u00A0' : tecla);
    ult.appendChild(t); ult.appendChild(cola); cur.setStartAfter(t);
  }
  for(const l of new Set([ln, ult])) if(!l.textContent && !l.querySelector('br')) l.appendChild(document.createElement('br'));
  cur.collapse(true); s.removeAllRanges(); s.addRange(cur);
  const vis = cur.startContainer.nodeType === 1 ? cur.startContainer : cur.startContainer.parentElement;
  if(vis && vis.scrollIntoView) vis.scrollIntoView({block: 'nearest'});
  if(explicaFija) ocultarExplica();
  actualizarPend(); programarBorrador();
  agregarFormatoAutoc(pars);
  return true;
}
/* Ctrl+Z justo después: vuelve el activador tal como se escribió, con la tecla que lo disparó */
function deshacerAutoc(){
  const d = AUTOC.deshacer; AUTOC.deshacer = null;
  editor.innerHTML = d.html;
  const ln = editor.children[d.lin]; if(!ln) return;
  const [n, o] = puntoTexto(ln, d.off), r = document.createRange();
  r.setStart(n, o); r.collapse(true);
  const s = getSelection(); s.removeAllRanges(); s.addRange(r);
  editor.focus({preventScroll: true});
  if(d.tecla === '\n') document.execCommand('insertParagraph'); else document.execCommand('insertText', false, d.tecla);
  actualizarPend(); programarBorrador();
}
/* los párrafos de la entrada con formato (negrita, cursiva, subrayado, color, alineación) van al formato del caso */
function agregarFormatoAutoc(pars){
  const con = pars.filter(p => p.t && (p.a || (p.r || []).some(r => r.b || r.i || r.u || r.c))).map(p => ({
    t: p.t, a: p.a || '',
    r: (p.r && p.r.length ? p.r : [{t: p.t}]).map(r => { const x = {t: r.t}; if(r.b) x.b = 1; if(r.i) x.i = 1; if(r.u) x.u = 1; if(r.c) x.c = r.c; return x; })
  }));
  if(!con.length || !actual) return;
  api('/api/formato_caso/agregar', {nombre: actual, parrafos: con})
    .catch(e => toast('No se pudo guardar el formato de la autocorrección: ' + e.message));
}
editor.addEventListener('keydown', e => {
  if(AUTOC.deshacer && (e.ctrlKey || e.metaKey) && !e.shiftKey && !e.altKey && e.key.toLowerCase() === 'z'){
    e.preventDefault(); deshacerAutoc(); return;
  }
  if(!AUTOC.mapa.size || e.ctrlKey || e.altKey || e.metaKey || e.isComposing) return;
  const tecla = e.key === 'Enter' ? '\n' : e.key;
  if(tecla !== '\n' && !AUTOC_FIN.test(tecla)) return;
  if(autocorregir(tecla)) e.preventDefault();
});
editor.addEventListener('input', () => { AUTOC.deshacer = null; });
editor.addEventListener('mousedown', () => { AUTOC.deshacer = null; });

function htmlAvisos(c){
  const a = c.avisos; if(!a || c.estado!=='listo') return '';
  const col = [['rojo','var(--rojo-f)','para corregir'],['amarillo','var(--amar-f)','dudosas'],
               ['turq','var(--turq)','no dictadas junto al hallazgo'],['gris','var(--gris)','frases de plantilla']];
  let h = col.filter(([k]) => a[k]).map(([k, color, txt]) =>
    `<span class="c" title="${a[k]} ${txt}"><i style="background:${color}"></i>${a[k]}</span>`).join('');
  const t = [];
  if(a.faltan.length) t.push('<b>Falta en el informe:</b> ' + esc(a.faltan.slice(0, 6).join(', ')) + (a.faltan.length > 6 ? '…' : ''));
  if(a.huecos.length) t.push('<b>Sin transcribir en:</b> ' + esc(a.huecos.join(', ')));
  if(!h && !t.length) h = '<span class="c" style="color:var(--ok)">✓ sin avisos</span>';
  return `<span class="av">${h}${t.length ? '<span class="txt">' + t.join(' · ') + '</span>' : ''}</span>`;
}

