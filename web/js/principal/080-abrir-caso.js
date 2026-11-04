// Abrir un caso.
/* ------------------------------------------------ abrir caso */
async function abrirCaso(n){
  if(abriendo) return;
  abriendo = n; marcarAbriendo(n); vacioHtml = ''; armarVacio([], []);
  try { await abrirCaso2(n); } finally { abriendo = null; marcarAbriendo(null); vacioHtml = ''; if(!actual) cargarLista(); }
}
function marcarAbriendo(n){
  document.querySelectorAll('#casos li').forEach(li => { const si = li.dataset.n === n; li.classList.toggle('abriendo', si);
    if(si){ const bd = li.querySelector('.badge'); if(bd) bd.innerHTML = '<span class="spin"></span>abriendo'; } });
}
async function abrirCaso2(n){
  if(actual){
    try { await guardarFormato(true); await guardarBorrador(); if(borradorPendiente()) throw new Error('Hay cambios nuevos sin guardar. Reintentá antes de cambiar de estudio.'); }
    catch(e){ toast(e.message); return; }
  }
  let b; try { b = await api('/api/caso/bloquear', {nombre: n}); } catch(e){ toast(e.message); return; }
  if(!b.ok){ toast('Este caso lo está revisando ' + b.por + '.'); return; }
  let c; try{ c = await api('/api/caso?nombre='+encodeURIComponent(n)); }catch(e){ if(actual!==n) soltarCaso(n); toast('No se pudo abrir el caso: ' + e.message); return; }
  if(actual && borradorPendiente()){ if(actual!==n) soltarCaso(n); toast('Hay cambios nuevos sin guardar. Conservamos el estudio actual.'); return; }
  if(actual && actual!==n) soltarCaso(actual);
  actual = n; palabras = c.palabras; activa = null;
  $('#bBorrarCaso').hidden = !((casosCache.find(x => x.nombre===n) || {}).puede_borrar);
  document.querySelectorAll('#casos li').forEach(li => li.classList.toggle('sel', li.dataset.n===n));
  mostrar('caso'); requestAnimationFrame(ajustarBarra); llenarMedicos($('#medCaso'), c.medico, 'Médico: sin especificar');
  ponerVoz(c.voz, c.medico);
  armarNuevoEstudio(c.estudios_nuevos || []);
  armarAvisoEstilo(c);
  ponerTitulo(c.paciente, c.titulo || (casosCache.find(x => x.nombre===n) || {}).titulo || n, c.revisado, {estudios: c.estudios, dur: c.dur});
  if(PREF.leer('velInicial')) $('#vel').value = PREF.leer('velInicial');      // Configuración → velocidad al abrir
  audio.src = '/audio/' + encodeURIComponent(n); audio.playbackRate = +$('#vel').value;
  ocultarExplica(); reiniciarSync();
  if(c.borrador != null){ editor.innerHTML = c.borrador; adaptarBorrador(); } else armarEditor(c.lineas);
  armarDictado(c.palabras);
  omis = c.omisiones || []; omisOk = c.omisiones_ok || []; armarAvisos();
  BORRADOR.confirmado.set(n, firmaBorrador(capturarBorrador()));
  BORRADOR.revision.set(n, c.borrador_revision);
  BORRADOR.fallidos.delete(n);
  estadoBorrador('');
  actualizarPend(); editor.scrollTop = 0;
  cargarOnda(n);
  await cargarEditorRevision(n);
}
function armarEditor(lineas){
  editor.innerHTML = '';
  for(const l of lineas){
    const d = document.createElement('div'); d.className='ln';
    if(l.titulo) d.classList.add('tit');
    if(l.seg!=null) d.dataset.seg = l.seg;
    if(l.linea){ d.classList.add('l-'+l.linea); d.dataset.linea=l.linea; d.dataset.motivo=l.motivo||''; }
    let vacia = true;
    for(const s of l.segs){
      if(!s.t) continue;
      if(s.t.trim()) vacia = false;
      if(s.tipo){
        const m = document.createElement('mark'); m.className='m-'+s.tipo; m.textContent=s.t; m.dataset.motivo=s.motivo||'';
        if(s.seg!=null) m.dataset.t = s.seg; d.appendChild(m);
      } else d.appendChild(document.createTextNode(s.t));
    }
    if(vacia && !d.childNodes.length) d.appendChild(document.createElement('br'));
    editor.appendChild(d);
  }
}
function armarDictado(ps){
  dict.innerHTML = ps.map((w,i)=>`<span data-i="${i}" class="${w.conf<0.5?'baja':''}${w.recuperada?' rec':''}" title="${w.ini.toFixed(1)}s · confianza ${w.conf.toFixed(2)}${w.recuperada?' · recuperada en la segunda pasada de Whisper':''}">${esc(w.p)}</span>`).join('');
}
function armarAvisos(){
  const box = $('#avisos'), pend = omis.filter(o => !omisOk.includes(o.dato));
  if(!pend.length){ box.style.display='none'; box.innerHTML=''; return; }
  box.style.display='block';
  box.innerHTML = '<b>Dictado pero no está en el informe:</b> revisá si falta agregarlo. ';
  for(const o of pend){
    const c = document.createElement('span'); c.className='chip';
    c.innerHTML = `${esc(o.dato)} <button title="Escuchar">▶</button><button title="Está bien, no hace falta">✕</button>`;
    c.title = o.hueco ? 'Hay voz en el audio que Whisper no transcribió. Escuchalo y agregá lo que falte.'
                      : `Se dictó «${o.dato}»${o.seg!=null ? ' (cerca de ' + mmss(o.seg) + ')' : ''} y no aparece en el informe.`;
    const [bE, bX] = c.querySelectorAll('button');
    bE.onclick = () => escuchar(o.seg);
    bX.onclick = () => { omisOk.push(o.dato); armarAvisos(); actualizarPend(); programarBorrador(); };
    if(o.hueco) c.style.background = 'var(--amarillo)';
    box.appendChild(c);
  }
}

