/* Editor A4. El modelo guarda párrafos lógicos; las hojas contienen fragmentos de esos
   párrafos. Repaginar nunca agrega saltos de párrafo al texto ni al Word. */
const FMT = {deshacer: [], rehacer: [], pendiente: false, guardando: null, color: '#C00000', seleccion: null, escritura: {}};
const copiaWord = x => JSON.parse(JSON.stringify(x));
const fuentesWord = ['Tahoma', 'Arial', 'Calibri', 'Cambria', 'Georgia', 'Times New Roman', 'Verdana'];
const runsWord = p => p ? (p.r || [{t: p.t, ...(p.b ? {b: 1} : {})}]) : [];
const esNormal = p => !p || ((p.a || '') === (p.a0 || '') && (!p.r || p.r.every(r =>
  !!r.b === !!p.b && !r.i && !r.u && !r.x && !r.c && !r.h && !r.f && !r.s)));
const parrafosVp = () => [...document.querySelectorAll('#vpHojas .vp-ed > p')];
let lineasOrigenWord = [], marcasOrigenWord = [], cargaWord = 0;
const lineaOrigenWord = k => lineasOrigenWord[k] || null;
const origenMarcaWord = el => el && el.dataset.marcaWord != null ? marcasOrigenWord[+el.dataset.marcaWord] || null : null;

async function cargarEditorRevision(nombre){
  const carga = ++cargaWord;
  ocultarEditorWord();
  let d;
  try { d = await api('/api/vista_previa', {texto: textoFinal(), nombre}); }
  catch(e){ if(actual === nombre) toast('No se pudo cargar el editor de Word: ' + e.message); return false; }
  if(actual !== nombre || carga !== cargaWord) return false;
  VP = d; VP.caso = nombre;
  if(!VP.parrafos.length) VP.parrafos = [{t:'',b:false,a:'',a0:''}];
  FMT.deshacer = []; FMT.rehacer = []; FMT.pendiente = false; FMT.seleccion = null; FMT.escritura = {};
  const vp = $('#vp'), panel = $('.hojawrap'); panel.appendChild(vp); panel.classList.add('word-activo');
  vp.classList.add('integrado', 'abierta'); vp.classList.remove('ampliado');
  vp.setAttribute('role', 'region'); vp.removeAttribute('aria-modal');
  $('#vpCerrar').textContent = 'Ampliar · ' + atajos.vista; $('#vpZoom').value = leerLS('zoomVp') || 'ajustar';
  avisoVistaPrevia(); paginar(VP); estadoBotonesFmt(); mostrarEstadoFmt();
  return true;
}
function ocultarEditorWord(){
  clearTimeout(FMT.t);
  $('#vp').classList.remove('abierta', 'ampliado'); $('.hojawrap').classList.remove('word-activo');
  cerrarMenuWord(); cerrarPaleta();
}
function indexarMarcasWord(d){
  const nodos = [...editor.children], usados = new Set(); marcasOrigenWord = [];
  lineasOrigenWord = d.parrafos.map(p => {
    const t = p?.t.trim() || '';
    const i = nodos.findIndex((n, i) => !usados.has(i) && n.textContent.replace(/\u00a0/g, ' ').trim() === t);
    if(i < 0) return null; usados.add(i); return nodos[i];
  });
}
function anotarFragmentoWord(el, k, desde){
  const origen = lineaOrigenWord(k); if(!origen) return;
  if(origen.classList.contains('sonando')) el.classList.add('sonando');
  const base = origen.textContent.length - origen.textContent.trimStart().length;
  const marcas = [];
  for(const m of origen.querySelectorAll('mark')){
    const r = document.createRange(); r.selectNodeContents(origen); r.setEndBefore(m);
    marcas.push({m, a:r.toString().length - base, b:r.toString().length - base + m.textContent.length});
  }
  if(origen.dataset.linea) marcas.push({m:origen, a:0, b:origen.textContent.trim().length});
  // Las marcas son decoración de revisión; el modelo de formato no las incluye.
  for(const {m,a,b} of marcas){
    let id = marcasOrigenWord.indexOf(m); if(id < 0){ id = marcasOrigenWord.length; marcasOrigenWord.push(m); }
    let pos = desde;
    const textos = []; const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
    for(let n; (n=walker.nextNode());) textos.push(n);
    for(const n of textos){
      const largo = n.data.length, ini = Math.max(0,a-pos), fin = Math.min(largo,b-pos); pos += largo;
      if(fin <= ini) continue;
      const rango = document.createRange(); rango.setStart(n,ini); rango.setEnd(n,fin);
      const marca = document.createElement(m.tagName==='MARK' ? 'mark' : 'span');
      marca.className = m.tagName==='MARK' ? m.className : 'l-' + m.dataset.linea;
      marca.dataset.marcaWord = id; marca.dataset.motivo = m.dataset.motivo || m.title || '';
      if(m.dataset.t) marca.dataset.t = m.dataset.t;
      marca.appendChild(rango.extractContents()); rango.insertNode(marca);
    }
  }
}
function refrescarMarcasWord(){
  if(!VP || VP.caso !== actual || !vpAbierta()) return;
  const sel = selVp() || FMT.seleccion, scroll = $('#vpHojas').scrollTop;
  paginar(VP); $('#vpHojas').scrollTop = scroll; restaurarSel(sel); ocultarExplica();
}
function seleccionarMarcaWord(el, sonar){
  if(!VP || VP.caso !== actual || !vpAbierta()) return false;
  let id = marcasOrigenWord.indexOf(el); if(id < 0){ refrescarMarcasWord(); id = marcasOrigenWord.indexOf(el); }
  const visible = $('#vpHojas').querySelector(`[data-marca-word="${id}"]`); if(!visible) return false;
  $('#vpHojas').querySelectorAll('.activa').forEach(m=>m.classList.remove('activa'));
  for(const m of $('#vpHojas').querySelectorAll(`[data-marca-word="${id}"]`)) m.classList.add('activa');
  visible.scrollIntoView({block:'center',behavior:'smooth'});
  const primero = posicion(visible,0), partes = [...$('#vpHojas').querySelectorAll(`[data-marca-word="${id}"]`)];
  const ultimo = partes[partes.length-1], fin = posicion(ultimo,ultimo.childNodes.length);
  if(primero && fin) restaurarSel({a:primero,b:fin});
  if(sonar) escuchar(tiempoDe(el));
  setTimeout(()=>{ if(activa===el && visible.isConnected) mostrarExplica(visible,true); },260);
  return true;
}
function marcarSonandoWord(origen){
  $('#vpHojas').querySelectorAll('p.sonando').forEach(p=>p.classList.remove('sonando'));
  const k = lineasOrigenWord.indexOf(origen); if(k<0) return;
  for(const p of parrafosVp()) if(+p.dataset.k===k) p.classList.add('sonando');
}

function recortarRuns(p, inicio, fin){
  const out = []; let pos = 0;
  for(const r of runsWord(p)){
    const a = Math.max(0, inicio - pos), b = Math.min(r.t.length, fin - pos);
    if(b > a) out.push({...r, t: r.t.slice(a, b)});
    pos += r.t.length;
  }
  return out;
}
function unirRuns(rs){
  const out = [];
  for(const r of rs){
    if(!r.t) continue;
    const anterior = out[out.length - 1];
    if(anterior && JSON.stringify({...anterior, t: ''}) === JSON.stringify({...r, t: ''})) anterior.t += r.t;
    else out.push({...r});
  }
  return out;
}
function parrafoVp(p){
  const el = document.createElement('p');
  if(p && p.a) el.style.textAlign = p.a;
  for(const r of runsWord(p)){
    const sp = document.createElement('span'); sp.textContent = r.t;
    Object.assign(sp.style, {fontWeight: r.b ? '700' : '400', fontStyle: r.i ? 'italic' : 'normal',
      textDecoration: [r.u && 'underline', r.x && 'line-through'].filter(Boolean).join(' ') || 'none',
      color: r.c || '#000000', backgroundColor: r.h || '', fontFamily: r.f || '', fontSize: r.s ? r.s + 'pt' : ''});
    el.appendChild(sp);
  }
  if(!el.textContent) el.appendChild(document.createElement('br'));
  return el;
}
function paginar(d){
  const cont = $('#vpHojas'), pg = {...d.pagina, ancho_cm: 21, alto_cm: 29.7};
  d.pagina = pg;
  indexarMarcasWord(d);
  cont.replaceChildren();
  const lienzo = document.createElement('div'); lienzo.className = 'vp-lienzo'; cont.appendChild(lienzo);
  const escala = document.createElement('div'); escala.className = 'vp-escala'; lienzo.appendChild(escala);
  let cuerpo, ed, usadas = 0; const numeros = [];
  function nueva(){
    const hoja = document.createElement('div'); hoja.className = 'vp-pag';
    hoja.setAttribute('aria-label', 'Página ' + (numeros.length + 1));
    Object.assign(hoja.style, {width: '21cm', height: '29.7cm',
      padding: `${pg.margen_superior_cm}cm ${pg.margen_derecho_cm}cm ${pg.margen_inferior_cm}cm ${pg.margen_izquierdo_cm}cm`,
      fontFamily: `${d.fuente}, sans-serif`, fontSize: d.tamano + 'pt'});
    cuerpo = document.createElement('div'); cuerpo.className = 'vp-cuerpo';
    cuerpo.style.height = (29.7 - pg.margen_superior_cm - pg.margen_inferior_cm) + 'cm';
    ed = document.createElement('div'); ed.className = 'vp-ed'; ed.contentEditable = 'true';
    ed.setAttribute('role', 'textbox'); ed.setAttribute('aria-label', 'Texto de la página ' + (numeros.length + 1));
    ed.setAttribute('aria-multiline', 'true'); ed.spellcheck = false;
    cuerpo.appendChild(ed); hoja.appendChild(cuerpo); escala.appendChild(hoja);
    const numero = document.createElement('div'); numero.className = 'vp-num'; escala.appendChild(numero); numeros.push(numero);
    usadas = 0;
  }
  nueva();
  if(d.encabezado > 0){
    const enc = document.createElement('div'); enc.className = 'vp-enc';
    for(let i = 0; i < d.encabezado; i++) enc.appendChild(parrafoVp(null));
    cuerpo.insertBefore(enc, ed);
  }
  const cabe = () => cuerpo.scrollHeight <= cuerpo.clientHeight + 0.5;
  function fragmento(p, k, desde, hasta){
    const el = parrafoVp(p ? {...p, t: p.t.slice(desde, hasta), r: recortarRuns(p, desde, hasta)} : null);
    el.dataset.k = k; el.dataset.desde = desde; el.dataset.hasta = hasta;
    anotarFragmentoWord(el, k, desde);
    ed.appendChild(el); return el;
  }
  d.parrafos.forEach((p, k) => {
    let desde = 0, longitud = p ? p.t.length : 0;
    do {
      let el = fragmento(p, k, desde, longitud);
      if(cabe()){ usadas++; break; }
      el.remove();
      let bajo = desde, alto = longitud;
      while(bajo < alto){
        const medio = Math.ceil((bajo + alto) / 2);
        el = fragmento(p, k, desde, medio); const ok = cabe(); el.remove();
        if(ok) bajo = medio; else alto = medio - 1;
      }
      if(bajo === desde){
        if(usadas){ nueva(); continue; }
        // El encabezado puede ocupar casi toda la primera hoja.
        if(cuerpo.querySelector('.vp-enc')){ nueva(); continue; }
        throw new Error('El tamaño de letra no cabe dentro de los márgenes de la hoja.');
      }
      let corte = bajo;
      if(corte < longitud){
        const espacio = p.t.lastIndexOf(' ', corte - 1);
        if(espacio > desde && corte - espacio < 80) corte = espacio + 1;
        // No dividir un par UTF-16 (por ejemplo, un emoji).
        if(/[\uD800-\uDBFF]/.test(p.t[corte - 1])) corte--;
      }
      fragmento(p, k, desde, corte); usadas++; desde = corte;
      if(desde < longitud) nueva();
    } while(desde < longitud);
  });
  numeros.forEach((n, i) => n.textContent = `Página ${i + 1} de ${numeros.length}`);
  $('#vpInfo').textContent = `A4 · ${numeros.length} ${numeros.length === 1 ? 'página' : 'páginas'}`;
  zoomVistaPrevia();
}
function zoomVistaPrevia(){
  const escala = $('#vpHojas .vp-escala'); if(!escala || !VP) return;
  const v = $('#vpZoom').value;
  const z = v === 'ajustar' ? Math.min(1.25, Math.max(0.3, ($('#vpHojas').clientWidth - 40) / cmPx(21))) : +v;
  // Transformar el lienzo mantiene las métricas del documento: CSS zoom puede cambiar
  // el redondeo de los renglones y esconder la última línea de una hoja.
  escala.style.transform = `translateX(-50%) scale(${z})`;
  escala.parentElement.style.height = Math.ceil(escala.offsetHeight * z) + 'px';
  escala.parentElement.style.width = Math.max($('#vpHojas').clientWidth - 32, cmPx(21) * z) + 'px';
}
function posicion(nodo, off){
  const elemento = nodo.nodeType === 1 ? nodo : nodo.parentElement;
  let p = elemento.closest('.vp-ed > p');
  if(!p && elemento.classList.contains('vp-ed')){
    p = elemento.children[Math.min(off, elemento.children.length - 1)];
    if(!p) return null;
    return {k: +p.dataset.k, o: off >= elemento.children.length ? +p.dataset.hasta : +p.dataset.desde};
  }
  if(!p) return null;
  const r = document.createRange(); r.setStart(p, 0); r.setEnd(nodo, off);
  return {k: +p.dataset.k, o: +p.dataset.desde + r.toString().length};
}
function selVp(){
  const s = getSelection(); if(!s.rangeCount) return null;
  const r = s.getRangeAt(0), a = posicion(r.startContainer, r.startOffset), b = posicion(r.endContainer, r.endOffset);
  return a && b ? {a, b} : null;
}
function puntoEn(pos){
  const candidatos = parrafosVp().filter(p => +p.dataset.k === pos.k && +p.dataset.desde <= pos.o && +p.dataset.hasta >= pos.o);
  const el = candidatos[candidatos.length - 1]; if(!el) return null;
  let resta = pos.o - (+el.dataset.desde); const w = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
  for(let n; (n = w.nextNode());){ if(resta <= n.data.length) return [n, resta]; resta -= n.data.length; }
  return [el, 0];
}
function restaurarSel(sel){
  if(!sel) return;
  const a = puntoEn(sel.a), b = puntoEn(sel.b); if(!a || !b) return;
  const padre = a[0].nodeType === 1 ? a[0] : a[0].parentElement;
  padre.closest('.vp-ed').focus({preventScroll: true});
  getSelection().setBaseAndExtent(a[0], a[1], b[0], b[1]); FMT.seleccion = sel;
}
function formatoEn(pos){
  const p = VP && VP.parrafos[pos.k]; let i = 0;
  for(const r of runsWord(p)){ i += r.t.length; if(i >= Math.max(1, pos.o)) return {...r, t: ''}; }
  return {t: '', ...(p && p.b ? {b: 1} : {})};
}
const sinSeleccion = s => !s || (s.a.k === s.b.k && s.a.o === s.b.o);
const hastaPar = s => s.b.k > s.a.k && s.b.o === 0 ? s.b.k - 1 : s.b.k;
function sincronizarInforme(){
  const nodos = [...editor.children], usados = new Set(), frag = document.createDocumentFragment();
  for(const p of VP.parrafos){
    const t = p ? p.t : '';
    const i = nodos.findIndex((n, i) => !usados.has(i) && n.textContent.replace(/\u00a0/g, ' ') === t);
    let el;
    if(i >= 0){ usados.add(i); el = nodos[i]; }
    else { el = document.createElement('div'); el.className = 'ln'; el.textContent = t;
      if(pareceTitulo(t)) el.classList.add('tit'); if(!t) el.appendChild(document.createElement('br')); }
    frag.appendChild(el);
  }
  editor.replaceChildren(frag); actualizarPend(); reiniciarSync(); programarBorrador(); avisoVistaPrevia();
}
function ponerModelo(modelo, sel){
  const anteriores = VP.parrafos, sc = $('#vpHojas').scrollTop;
  const textoAntes = anteriores.map(p => p ? p.t : '').join('\n');
  VP.parrafos = modelo;
  if(textoAntes !== modelo.map(p => p ? p.t : '').join('\n')) sincronizarInforme();
  paginar(VP); $('#vpHojas').scrollTop = sc;
  restaurarSel(sel); estadoBotonesFmt();
  FMT.pendiente = true; mostrarEstadoFmt('Guardando…'); clearTimeout(FMT.t); FMT.t = setTimeout(guardarFormato, 700);
}
function cambiarFormato(fn){
  if(!VP) return;
  const sel = selVp() || FMT.seleccion, antes = JSON.stringify(VP.parrafos), modelo = copiaWord(VP.parrafos);
  const seleccion = fn(sel, modelo);
  if(seleccion === false) return;
  if(JSON.stringify(modelo) === antes){ estadoBotonesFmt(); return; }
  FMT.deshacer.push({modelo: JSON.parse(antes), sel, html: htmlLimpio()}); if(FMT.deshacer.length > 100) FMT.deshacer.shift(); FMT.rehacer = [];
  ponerModelo(modelo, seleccion && seleccion.a ? seleccion : sel);
}
function deshacerFmt(atras){
  const de = atras ? FMT.deshacer : FMT.rehacer, a = atras ? FMT.rehacer : FMT.deshacer;
  if(!de.length) return;
  a.push({modelo: copiaWord(VP.parrafos), sel: selVp() || FMT.seleccion, html: htmlLimpio()});
  const previo = de.pop(); FMT.escritura = {}; ponerModelo(previo.modelo, previo.sel);
  if(previo.html != null){ editor.innerHTML = previo.html; actualizarPend(); reiniciarSync(); programarBorrador(); avisoVistaPrevia(); refrescarMarcasWord(); }
}
async function guardarFormato(exigir=false){
  clearTimeout(FMT.t);
  // Capturar el documento antes de esperar otra escritura: la persona puede cerrar
  // el editor y abrir un caso distinto mientras el servidor responde.
  const documento = VP;
  const html = htmlLimpio(), omisiones = [...omisOk];
  if(FMT.guardando) await FMT.guardando;
  if(!FMT.pendiente || !VP || !VP.caso) return;
  if(VP !== documento || VP.caso !== actual) return;
  FMT.pendiente = false;
  const caso = VP.caso, normal = VP.parrafos.every(esNormal);
  const formato = normal ? null : {v: 2, parrafos: VP.parrafos.filter(Boolean).map(p => {
    const inicio = p.t.length - p.t.trimStart().length, fin = p.t.trimEnd().length;
    return {t: p.t.trim(), a: p.a || '', r: recortarRuns(p, inicio, Math.max(inicio, fin))};
  })};
  FMT.guardando = (async () => {
    try {
      // El borrador se escribe primero para que el formato corresponda al texto guardado.
      await api('/api/borrador', {nombre: caso, html, omisiones_ok: omisiones});
      await api('/api/formato_caso', {nombre: caso, formato});
      mostrarEstadoFmt('Cambios guardados · se conservan en el Word');
    } catch(e){ FMT.pendiente = true; mostrarEstadoFmt('No se pudo guardar: ' + e.message); }
    finally { FMT.guardando = null; }
  })();
  await FMT.guardando;
  if(exigir && FMT.pendiente) throw new Error('No se pudieron guardar todos los cambios de formato. Volvé a intentar antes de generar el Word.');
}
function mostrarEstadoFmt(txt){ $('#vpFmtEstado').textContent = txt || 'Editá el texto o seleccioná una parte para darle formato'; }
function estilo(cmd, valor){
  const claves = {bold: 'b', italic: 'i', underline: 'u', strikeThrough: 'x', foreColor: 'c', fontName: 'f', fontSize: 's', highlight: 'h'};
  return (sel, modelo) => {
    if(!sel) return false;
    const clave = claves[cmd]; if(!clave) return false;
    let v = valor;
    if(['b','i','u','x'].includes(clave)){
      const rs = [];
      for(let k = sel.a.k; k <= hastaPar(sel); k++) rs.push(...recortarRuns(modelo[k], k === sel.a.k ? sel.a.o : 0, k === sel.b.k ? sel.b.o : (modelo[k]?.t.length || 0)));
      v = sinSeleccion(sel) ? !({...formatoEn(sel.a), ...FMT.escritura})[clave] : !rs.every(r => r[clave]);
    }
    if(sinSeleccion(sel)){ FMT.escritura[clave] = v; restaurarSel(sel); estadoBotonesFmt(); return false; }
    for(let k = sel.a.k; k <= hastaPar(sel); k++){
      const p = modelo[k]; if(!p) continue;
      const a = k === sel.a.k ? sel.a.o : 0, b = k === sel.b.k ? sel.b.o : p.t.length;
      p.r = unirRuns([...recortarRuns(p, 0, a), ...recortarRuns(p, a, b).map(r => ({...r, [clave]: v})), ...recortarRuns(p, b, p.t.length)]);
    }
  };
}
function alinearParrafos(al){ return (sel, modelo) => {
  if(!sel) return false;
  for(let k = sel.a.k; k <= hastaPar(sel); k++){
    if(!modelo[k]) modelo[k] = {t: '', b: false, a0: '', a: al}; else modelo[k].a = al;
  }
}; }
function quitarFormato(sel, modelo){
  const todo = sinSeleccion(sel), desde = todo ? 0 : sel.a.k, hasta = todo ? modelo.length - 1 : hastaPar(sel);
  for(let k = desde; k <= hasta; k++){
    const p = modelo[k]; if(!p) continue;
    const a = todo || k !== sel.a.k ? 0 : sel.a.o, b = todo || k !== sel.b.k ? p.t.length : sel.b.o;
    p.r = unirRuns([...recortarRuns(p, 0, a), {t: p.t.slice(a, b), ...(p.b ? {b: 1} : {})}, ...recortarRuns(p, b, p.t.length)]);
    if(todo || (a === 0 && b === p.t.length)) p.a = p.a0 || '';
  }
  FMT.escritura = {};
}
function estadoBotonesFmt(){
  const sel = selVp() || FMT.seleccion, f = sel && VP ? {...formatoEn(sel.a), ...FMT.escritura} : {};
  for(const b of document.querySelectorAll('#vpFmt [data-cmd], #vpMenu [data-cmd]')){
    const clave = {bold:'b', italic:'i', underline:'u', strikeThrough:'x'}[b.dataset.cmd];
    b.classList.toggle('on', !!f[clave]); b.setAttribute('aria-pressed', !!f[clave]);
  }
  const al = sel && VP?.parrafos[sel.a.k]?.a || 'left';
  for(const b of document.querySelectorAll('#vpFmt [data-al], #vpMenu [data-al]')) b.classList.toggle('on', b.dataset.al === al);
  $('#vpDeshacer').disabled = !FMT.deshacer.length; $('#vpRehacer').disabled = !FMT.rehacer.length;
  if(document.activeElement !== $('#vpFuente')) $('#vpFuente').value = f.f || VP?.fuente || 'Tahoma';
  if(document.activeElement !== $('#vpTamano')) $('#vpTamano').value = f.s || VP?.tamano || 12;
  $('#vpColorMuestra').style.background = f.c || FMT.color;
}

/* La edición de texto actúa sobre el modelo, incluso si la selección abarca hojas distintas. */
function reemplazarWord(texto, tipo, plantilla=null){
  cambiarFormato((seleccion, modelo) => {
    if(!seleccion) return false;
    const s = copiaWord(seleccion);
    if(sinSeleccion(s) && /^delete/.test(tipo)){
      const p = modelo[s.a.k], t = p?.t || '';
      if(/Backward$/.test(tipo)){
        if(s.a.o){ s.a.o = tipo.includes('Word') ? t.slice(0, s.a.o).replace(/\s*\S+\s*$/, '').length : s.a.o - [...t.slice(0, s.a.o)].pop().length; }
        else if(s.a.k){ s.a.k--; s.a.o = modelo[s.a.k]?.t.length || 0; } else return false;
      } else {
        if(s.b.o < t.length) s.b.o += tipo.includes('Word') ? (t.slice(s.b.o).match(/^\s*\S+\s*/) || [''])[0].length : [...t.slice(s.b.o)][0].length;
        else if(s.b.k < modelo.length - 1){ s.b.k++; s.b.o = 0; } else return false;
      }
    }
    const primero = modelo[s.a.k] || {t: '', b: false, a: '', a0: ''}, ultimo = modelo[s.b.k] || {t: ''};
    const antes = recortarRuns(primero, 0, s.a.o), despues = recortarRuns(ultimo, s.b.o, ultimo.t.length);
    const f = {...formatoEn(s.a), ...FMT.escritura}; delete f.t;
    const lineas = texto.replace(/\r\n?/g, '\n').split('\n');
    const nuevos = lineas.map((t, i) => {
      const insertados = plantilla?.[i]?.r || [{t, ...f}];
      const rs = unirRuns([...(i === 0 ? antes : []), ...insertados, ...(i === lineas.length - 1 ? despues : [])]);
      return {...primero, ...(plantilla?.[i]?.a ? {a:plantilla[i].a} : {}), t: rs.map(r => r.t).join(''), r: rs};
    });
    modelo.splice(s.a.k, s.b.k - s.a.k + 1, ...nuevos);
    const pos = {k: s.a.k + nuevos.length - 1, o: (nuevos.length === 1 ? s.a.o : 0) + lineas[lineas.length - 1].length};
    return {a: pos, b: pos};
  });
}
function tecladoFormato(e){
  if(e.target.closest('#vpFmt, #vpMenu')) return;
  if(e.key === 'Escape' && !$('#vpMenu').hidden){ e.preventDefault(); return; }
  if(!(e.ctrlKey || e.metaKey) || e.altKey) return;
  const k = e.key.toLowerCase(), acc = {b:'bold', n:'bold', i:'italic', k:'italic', s:'underline', u:'underline'}[k],
        al = {q:'left', t:'center', d:'right', j:'justify', l:'left', e:'center', r:'right'}[k];
  if(acc){ e.preventDefault(); cambiarFormato(estilo(acc)); }
  else if(al){ e.preventDefault(); cambiarFormato(alinearParrafos(al)); }
  else if(k === 'z' || k === 'y'){ e.preventDefault(); deshacerFmt(k === 'z' && !e.shiftKey); }
  else if(k === 'a'){ e.preventDefault(); const k = VP.parrafos.length - 1; restaurarSel({a:{k:0,o:0}, b:{k,o:VP.parrafos[k]?.t.length || 0}}); }
}
$('#vpHojas').addEventListener('beforeinput', e => {
  if(!e.target.closest('.vp-ed')) return;
  if(e.isComposing) return;
  e.preventDefault();
  const tecla = e.inputType === 'insertParagraph' || e.inputType === 'insertLineBreak' ? '\n' : e.data;
  if(tecla && (tecla === '\n' || AUTOC_FIN.test(tecla)) && autocorregirWord(tecla)) return;
  if(e.inputType === 'historyUndo' || e.inputType === 'historyRedo'){ deshacerFmt(e.inputType === 'historyUndo'); return; }
  if(e.inputType.startsWith('delete')) reemplazarWord('', e.inputType);
  else if(e.inputType === 'insertParagraph' || e.inputType === 'insertLineBreak') reemplazarWord('\n', e.inputType);
  else if(e.inputType.startsWith('insert') && e.data != null) reemplazarWord(e.data, e.inputType);
});
let composicionWord = null;
$('#vpHojas').addEventListener('compositionstart', () => { composicionWord = selVp(); });
$('#vpHojas').addEventListener('compositionend', e => {
  const sel = composicionWord; composicionWord = null;
  paginar(VP); restaurarSel(sel); if(e.data) reemplazarWord(e.data, 'insertText');
});
$('#vpHojas').addEventListener('paste', e => { e.preventDefault(); reemplazarWord(e.clipboardData.getData('text/plain'), 'insertFromPaste'); });
$('#vpHojas').addEventListener('cut', e => {
  const s = selVp(); if(sinSeleccion(s)) return;
  e.preventDefault(); e.clipboardData.setData('text/plain', textoSeleccionWord(s)); reemplazarWord('', 'deleteByCut');
});
$('#vpHojas').addEventListener('drop', e => e.preventDefault());
$('#vpHojas').addEventListener('pointerup', () => { FMT.escritura = {}; });
function textoSeleccionWord(s){
  return VP.parrafos.slice(s.a.k, s.b.k + 1).map((p, i) => (p?.t || '').slice(i === 0 ? s.a.o : 0, i === s.b.k - s.a.k ? s.b.o : undefined)).join('\n');
}
function autocorregirWord(tecla){
  const sel = selVp(); if(!sel || !sinSeleccion(sel) || !AUTOC.mapa.size) return false;
  const prefijo = (VP.parrafos[sel.a.k]?.t || '').slice(0,sel.a.o), m = /(?:^|[\s\u00a0])([^\s\u00a0]+)$/.exec(prefijo);
  const entrada = m && AUTOC.mapa.get(m[1]); if(!entrada) return false;
  const pars = copiaWord(entrada).map(p=>({...p,r:p.r?.length ? p.r : [{t:p.t||''}]}));
  if(tecla==='\n') pars.push({t:'',r:[]});
  else { const ultimo = pars[pars.length-1]; ultimo.t += tecla; ultimo.r.push({t:tecla}); }
  restaurarSel({a:{k:sel.a.k,o:sel.a.o-m[1].length},b:sel.b});
  reemplazarWord(pars.map(p=>p.t).join('\n'),'insertText',pars); return true;
}

$('#vpHojas').addEventListener('click', e => {
  const p = e.target.closest('p[data-k]'); if(!p) return;
  const origen = lineaOrigenWord(+p.dataset.k);
  if(e.altKey && origen){ const r=rangoDe(origen); escuchar(r ? palabras[r[0]].ini : tiempoDe(origen)); return; }
  const marca = e.target.closest('[data-marca-word]'), m = origenMarcaWord(marca);
  if(m){
    if(activa) activa.classList.remove('activa'); activa=m; m.classList.add('activa');
    $('#vpHojas').querySelectorAll('.activa').forEach(x=>x.classList.remove('activa')); marca.classList.add('activa');
    escuchar(tiempoDe(m));
  }
});
$('#vpHojas').addEventListener('mouseover', e => {
  const m=e.target.closest('[data-marca-word]'); if(!m || explicaFija || !PREF.explicar()) return;
  clearTimeout(tExplica); tExplica=setTimeout(()=>mostrarExplica(m,false),250);
});
$('#vpHojas').addEventListener('mouseout', e => {
  const m=e.target.closest('[data-marca-word]'); if(!m || (e.relatedTarget && m.contains(e.relatedTarget))) return;
  clearTimeout(tExplica); if(!explicaFija && explicaDe===m) ocultarExplica();
});

/* La barra y el menú conservan la selección aunque sus controles reciban el foco. */
$('#vpFmt').addEventListener('mousedown', e => {
  FMT.seleccion = selVp() || FMT.seleccion;
  if(e.target.closest('button')) e.preventDefault();
});
for(const b of document.querySelectorAll('#vpFmt [data-cmd], #vpMenu [data-cmd]')) b.onclick = () => { restaurarSel(FMT.seleccion); cambiarFormato(estilo(b.dataset.cmd)); };
for(const b of document.querySelectorAll('#vpFmt [data-al], #vpMenu [data-al]')) b.onclick = () => { restaurarSel(FMT.seleccion); cambiarFormato(alinearParrafos(b.dataset.al)); };
$('#vpDeshacer').onclick = () => deshacerFmt(true); $('#vpRehacer').onclick = () => deshacerFmt(false);
$('#vpLimpiar').onclick = () => cambiarFormato(quitarFormato);
$('#vpFuente').onchange = e => { restaurarSel(FMT.seleccion); cambiarFormato(estilo('fontName', e.target.value)); };
function tamanoWord(valor){
  const n = Number(valor);
  if(!Number.isFinite(n) || n < 6 || n > 96){ toast('Elegí un tamaño entre 6 y 96 puntos.'); estadoBotonesFmt(); return; }
  restaurarSel(FMT.seleccion); cambiarFormato(estilo('fontSize', Math.round(n * 2) / 2));
}
$('#vpTamano').onchange = e => tamanoWord(e.target.value);
$('#vpTamano').onkeydown = e => { if(e.key === 'Enter'){ e.preventDefault(); tamanoWord(e.target.value); } };
$('#vpGuardar').onclick = () => $('#bFin').click();
let selPaleta = null;
function cerrarPaleta(){ $('#vpPaleta').classList.remove('abierta'); }
$('#vpColorBtn').onclick = () => { selPaleta = selVp() || FMT.seleccion; $('#vpPaleta').classList.toggle('abierta'); };
function ponerColor(c){ cerrarPaleta(); FMT.color = c; restaurarSel(selPaleta); cambiarFormato(estilo('foreColor', c)); }
$('#vpPaleta').addEventListener('click', e => { const b = e.target.closest('[data-c]'); if(b) ponerColor(b.dataset.c === 'auto' ? '#000000' : b.dataset.c); });
$('#vpColorLibre').onchange = e => ponerColor(e.target.value);
// Colores estándar compartidos entre la barra y el menú contextual.
const COLORES_WORD = [
  ['Negro','#000000'], ['Blanco','#FFFFFF'], ['Rojo oscuro','#C00000'], ['Rojo','#FF0000'],
  ['Naranja','#FFC000'], ['Amarillo','#FFFF00'], ['Verde claro','#92D050'], ['Verde','#00B050'],
  ['Celeste','#00B0F0'], ['Azul','#0070C0'], ['Azul oscuro','#002060'], ['Violeta','#7030A0']
];
for(const id of ['vpColoresPredeterminados','vpMenuColores']){
  const paleta=document.getElementById(id);
  for(const [nombre,color] of COLORES_WORD){
    const b=document.createElement('button'); b.type='button'; b.dataset.c=color;
    b.title=nombre; b.setAttribute('aria-label',nombre); b.style.backgroundColor=color; paleta.appendChild(b);
  }
}
$('#vpMenuColores').addEventListener('click',e=>{
  const b=e.target.closest('[data-c]'); if(!b) return;
  selPaleta=FMT.seleccion; ponerColor(b.dataset.c);
});
$('#vpResaltar').onclick = () => cambiarFormato(estilo('highlight', '#FFFF00'));
function cerrarMenuWord(){ $('#vpMenu').hidden = true; }
let seleccionContextoWord = null;
$('#vpHojas').addEventListener('pointerdown', e => {
  if(e.button === 2) seleccionContextoWord = selVp();
});
$('#vpHojas').addEventListener('contextmenu', e => {
  if(!e.target.closest('.vp-ed')) return;
  e.preventDefault(); cerrarPaleta();
  FMT.seleccion = !sinSeleccion(seleccionContextoWord) ? seleccionContextoWord : selVp() || FMT.seleccion;
  seleccionContextoWord = null;
  restaurarSel(FMT.seleccion);
  const menu = $('#vpMenu'); menu.hidden = false; estadoBotonesFmt();
  $('#vpMenuTamano').value = $('#vpTamano').value; $('#vpMenuFuente').value = $('#vpFuente').value;
  menu.style.left = Math.max(8, Math.min(e.clientX, innerWidth - menu.offsetWidth - 8)) + 'px';
  menu.style.top = Math.max(8, Math.min(e.clientY, innerHeight - menu.offsetHeight - 8)) + 'px';
});
$('#vpMenu').addEventListener('mousedown', e => { if(e.target.closest('button')) e.preventDefault(); });
$('#vpMenuTamano').onchange = e => { tamanoWord(e.target.value); };
$('#vpMenuFuente').onchange = e => { restaurarSel(FMT.seleccion); cambiarFormato(estilo('fontName', e.target.value)); };
$('#vpMenuColor').oninput = e => { restaurarSel(FMT.seleccion); cambiarFormato(estilo('foreColor', e.target.value)); };
$('#vpMenuLimpiar').onclick = () => { restaurarSel(FMT.seleccion); cambiarFormato(quitarFormato); };
$('#vpMenuCopiar').onclick = async () => {
  const sel = copiaWord(FMT.seleccion), modelo = VP;
  if(sinSeleccion(sel)){ toast('Seleccioná el texto que querés copiar.'); return; }
  try { await navigator.clipboard.writeText(textoSeleccionWord(sel)); }
  catch(e){ toast('No se pudo copiar: ' + e.message); }
  if(VP === modelo && !$('#vpMenu').hidden) restaurarSel(sel);
};
$('#vpMenuPegar').onclick = async () => {
  const sel = copiaWord(FMT.seleccion), modelo = VP;
  try {
    const texto = await navigator.clipboard.readText();
    if(VP !== modelo || $('#vpMenu').hidden) return;
    restaurarSel(sel); if(texto) reemplazarWord(texto, 'insertFromPaste');
  } catch(e){ toast('No se pudo acceder al portapapeles. Podés pegar con Ctrl+V.'); restaurarSel(sel); }
};
document.addEventListener('mousedown', e => {
  if(!e.target.closest('#vpMenu')) cerrarMenuWord();
  if(!e.target.closest('.vp-color')) cerrarPaleta();
});
document.addEventListener('selectionchange', () => {
  if(!vpAbierta()) return; const s = selVp(); if(s) FMT.seleccion = s; estadoBotonesFmt();
});

$('#vpHojas').addEventListener('scroll', () => {
  if(explicaDe) ubicarExplica();

}, {passive: true});
$('#bVista').onclick = abrirVistaPrevia;
$('#vpCerrar').onclick = () => $('#vp').classList.contains('ampliado') ? cerrarVistaPrevia() : abrirVistaPrevia();
$('#vpCopiar').onclick = copiarParaWord;
$('#vpZoom').onchange = e => { grabarLS('zoomVp', e.target.value); zoomVistaPrevia(); };
addEventListener('resize', () => { if(vpAbierta()) zoomVistaPrevia(); });
let anchoEditorWord = 0;
new ResizeObserver(entries=>{
  const ancho=entries[0].contentRect.width;
  if(ancho !== anchoEditorWord){ anchoEditorWord=ancho; if(vpAbierta()) requestAnimationFrame(zoomVistaPrevia); }
}).observe($('#vpHojas'));
