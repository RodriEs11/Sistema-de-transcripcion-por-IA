// Médico reconocido por la voz.
/* ------------------------------------------------ médico reconocido por la voz
   El servidor calcula la huella de voz de cada audio y la compara con las muestras de cada médico (voces.py).
   seguro = se asignó solo · dudoso = se sugiere (la IA usó la plantilla general) · sin reconocer.
   Al guardar el Word con un médico, la voz del audio queda como muestra suya. */
const ICO_VOZ = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3"/></svg>';
const pctV = p => p == null ? '' : Math.round(p * 100) + ' %';
let VOZ_CASO = null;
function ponerVoz(v, med){
  VOZ_CASO = v || null;
  const b = $('#vozCaso');
  if(!v){ b.hidden = true; return; }
  let cls = '', txt = '', tit = '';
  if(med && v.por === 'voz'){
    cls = 'seguro'; txt = 'por la voz · ' + pctV(v.puntaje);
    tit = `Médico reconocido por la voz (se parece ${pctV(v.puntaje)} a sus muestras). Si no es, elegí el correcto en la lista: al guardar se corrige.`;
  } else if(med){
    cls = 'ok'; txt = v.muestra === med ? 'voz registrada' : 'elegido a mano';
    tit = v.muestra === med ? `La voz de este audio ya es una muestra de ${med}.`
      : `Al guardar, la voz de este audio queda como muestra de ${med}` + (v.medico && v.medico !== med && v.puntaje != null ? ` (la voz se parecía más a ${v.medico}, ${pctV(v.puntaje)}).` : '.');
  } else if(v.estado === 'dudoso' && v.medico){
    cls = 'dudoso'; txt = '¿' + v.medico + '? ' + pctV(v.puntaje);
    tit = `La voz se parece a ${v.medico} (${pctV(v.puntaje)})` + (v.segundo ? ` y a ${v.segundo} (${pctV(v.puntaje2)})` : '')
      + (v.motivo ? `; ${v.motivo}` : '') + `. La IA usó la plantilla general. Clic: es ${v.medico}.`;
  } else if(v.estado === 'corto'){
    cls = 'sin'; txt = 'voz muy corta'; tit = 'El audio tiene muy poca voz para reconocer al médico. Elegilo en la lista.';
  } else {
    cls = 'sin'; txt = 'voz sin reconocer';
    tit = (v.motivo ? v.motivo[0].toUpperCase() + v.motivo.slice(1) + '. ' : '') + 'Elegí el médico en la lista: al guardar, su voz queda registrada y los audios siguientes se reconocen solos.';
  }
  b.className = 'voz-chip ' + cls; b.innerHTML = ICO_VOZ + '<span class="vz-txt">' + esc(txt) + '</span>';
  b.title = tit; b.setAttribute('aria-label', 'Reconocimiento por la voz: ' + tit); b.hidden = false;
}
$('#vozCaso').onclick = () => {
  const v = VOZ_CASO; if(!v) return;
  if(!$('#medCaso').value && v.estado === 'dudoso' && v.medico && medicos.some(m => m.nombre === v.medico)){
    $('#medCaso').value = v.medico; cambiarMedicoCaso(v.medico);
    actualizarMedicoCaso();
  } else toast($('#vozCaso').title, [], 9000);
};
async function cambiarMedicoCaso(v){
  const n = actual; if(!n) return;
  let r; try { r = await api('/api/caso_medico', {nombre: n, medico: v}); } catch(e){ toast(e.message); return; }
  if(actual === n) ponerVoz(r.voz, v);
  if(v && r.regenerar) toast(`Médico: ${v}. La IA armó este informe sin su estilo: podés regenerarlo con sus plantillas y ejemplos (se pierden los cambios). Al guardar, su voz queda registrada.`,
    [['Regenerar con este médico', () => $('#bRegen').click()]], 12000);
  else toast(v ? `Médico: ${v}. Al guardar, la voz de este audio queda como muestra de ${v}.` : 'Médico quitado.', [], 6000);
  cargarLista();
}
/* escuchar un audio desde Médicos o Agrupar voces (aparte del reproductor del caso) */
var AUDIO_M = null, BOTON_M = null;
function pararMuestra(){ if(AUDIO_M && !AUDIO_M.paused) AUDIO_M.pause(); if(BOTON_M){ BOTON_M.textContent = '▶'; BOTON_M = null; } }
function escucharMuestra(n, b){
  if(BOTON_M === b){ pararMuestra(); return; }
  pararMuestra(); audio.pause();
  if(!AUDIO_M){ AUDIO_M = new Audio(); AUDIO_M.onended = pararMuestra; }
  AUDIO_M.src = '/audio/' + encodeURIComponent(n); AUDIO_M.volume = volumenActual();   // el volumen del reproductor
  AUDIO_M.play().catch(() => { pararMuestra(); toast('No se pudo reproducir el audio.'); });
  BOTON_M = b; b.textContent = '❚❚';
}
const FUENTE_VOZ = {'guardado': 'al guardar', 'etiquetado': 'etiquetado a mano', 'revisado antes': 'informe anterior'};
async function armarVozMedico(nombre){
  const el = $('#medVoz');
  if(!nombre){ el.innerHTML = ''; return; }
  let r; try { r = await api('/api/voces/muestras?medico=' + encodeURIComponent(nombre)); } catch(e){ el.innerHTML = ''; return; }
  if(medSel !== nombre) return;
  const ms = r.muestras;
  el.innerHTML = `<div><b>Voz</b> · ${ms.length ? ms.length + (ms.length === 1 ? ' muestra' : ' muestras') : 'sin muestras'} <span class="mu">· `
    + (ms.length >= 3 ? 'se reconoce solo por la voz' : `con 3 se reconoce solo (faltan ${3 - ms.length})`) + '</span></div>'
    + (ms.length ? '<ul>' + ms.map(m => `<li><span class="n">${esc(m.paciente || m.titulo || m.caso)}</span><span class="mu">${esc([cuandoCorto(m.fecha), m.seg ? Math.round(m.seg) + ' s de voz' : '', FUENTE_VOZ[m.fuente] || ''].filter(Boolean).join(' · '))}</span>`
        + (m.audio ? `<button class="chico play-m" data-n="${esc(m.caso)}" title="Escuchar">▶</button>` : '')
        + `<button class="chico quitar-m" data-n="${esc(m.caso)}" title="No es de este médico: deja de usarse para reconocerlo">Quitar</button></li>`).join('') + '</ul>'
      : '<p class="mu" style="margin:6px 0 0">Cuando guardes un informe de este médico (o etiquetes audios en «Agrupar voces»), su voz queda registrada acá.</p>');
  el.querySelectorAll('.play-m').forEach(b => b.onclick = () => escucharMuestra(b.dataset.n, b));
  el.querySelectorAll('.quitar-m').forEach(b => b.onclick = async () => {
    if(!await confirmar('¿Quitar esta muestra de voz?', `<p>Deja de usarse para reconocer a ${esc(nombre)}. El informe no se toca.</p>`, 'Quitar')) return;
    try { await api('/api/voces/quitar', {caso: b.dataset.n}); } catch(e){ toast(e.message); return; }
    pararMuestra(); await cargarMedicos(); armarListaMed(); armarVozMedico(nombre); });
}
async function contarSinEtiquetar(){
  const b = $('#bAgrupar');
  try { const r = await api('/api/voces'); b.textContent = 'Agrupar voces' + (r.sin_etiquetar ? ' · ' + r.sin_etiquetar : '');
    b.dataset.modelo = r.modelo; b.dataset.error = r.error || ''; } catch(e){}
}
async function armarGrupos(){
  const el = $('#grupos');
  el.innerHTML = '<p class="mu">Buscando voces parecidas…</p>';
  let g, est;
  try { [g, est] = await Promise.all([api('/api/voces/agrupar'), api('/api/voces')]); }
  catch(e){ el.innerHTML = `<div class="vac-card">No se pudo leer: ${esc(e.message)}</div>`; return; }
  if(est.modelo !== 'listo'){
    el.innerHTML = `<div class="vac-card"><b>El reconocimiento de voz todavía no está listo.</b><p>${est.modelo === 'bajando' ? 'Se está bajando el modelo (unos 26 MB, una sola vez).' : 'Falta el modelo de voz' + (est.error ? ': ' + esc(est.error) : '') + '. Se vuelve a intentar al reiniciar el servidor.'}</p></div>`;
    return;
  }
  if(!g.grupos.length){
    el.innerHTML = '<div class="vac-card"><b>No hay audios con la voz sin etiquetar.</b><p>Los audios nuevos aparecen acá hasta que se guardan con su médico o se etiquetan.</p></div>';
    return;
  }
  el.innerHTML = '';
  g.grupos.forEach((gr, i) => {
    const d = document.createElement('section'); d.className = 'grupo-voz';
    const s = gr.sugerencia || {}, conSug = s.medico && s.estado !== 'desconocido';
    const sug = conSug ? `parece ${s.medico} (${pctV(s.puntaje)})` : 'no se parece a ningún médico con muestras';
    d.innerHTML = `<header><b>${gr.casos.length > 1 ? 'Grupo ' + (i + 1) : 'Audio suelto'}</b> · ${gr.casos.length} ${gr.casos.length === 1 ? 'audio' : 'audios'} · <span class="mu">${esc(sug)}</span></header><ul>`
      + gr.casos.map(c => `<li><label><input type="checkbox" checked data-n="${esc(c.nombre)}"><span class="n">${esc(c.paciente || c.titulo || c.nombre)}</span>`
        + `<span class="mu">${esc([c.medico ? 'médico: ' + c.medico : '', c.dur ? mmss(c.dur) : '', c.fecha ? cuandoCorto(c.fecha) : '', c.origen && c.origen !== 'Servidor' ? c.origen : ''].filter(Boolean).join(' · '))}</span></label>`
        + (c.audio ? `<button class="chico play-m" data-n="${esc(c.nombre)}" title="Escuchar">▶</button>` : '') + '</li>').join('')
      + '</ul><div class="fila"><select class="selG" aria-label="Médico de estos audios"></select><button class="prim bEtiq">Etiquetar</button></div>';
    const sel = d.querySelector('.selG');
    llenarMedicos(sel, conSug ? s.medico : '', 'Elegí el médico…');
    sel.onchange = async e => { if(e.target.value === NUEVO_MED){ const n = await nuevoMedico(); llenarMedicos(e.target, n || '', 'Elegí el médico…'); } };
    d.querySelector('.bEtiq').onclick = async () => {
      const med = sel.value, ns = [...d.querySelectorAll('input:checked')].map(x => x.dataset.n);
      if(!med || med === NUEVO_MED){ toast('Elegí el médico de estos audios.'); sel.focus(); return; }
      if(!ns.length){ toast('Tildá al menos un audio.'); return; }
      let r; try { r = await api('/api/voces/etiquetar', {nombres: ns, medico: med}); } catch(e){ toast(e.message); return; }
      const k = r.etiquetados.length;
      toast(`${k} ${k === 1 ? 'audio etiquetado' : 'audios etiquetados'} como de ${med}: ahora tiene ${r.muestras} ${r.muestras === 1 ? 'muestra' : 'muestras'} de voz.`
        + (r.salteados.length ? ` ${r.salteados.length} salteado(s): ${r.salteados.map(x => x.motivo).join(', ')}.` : ''), [], 8000);
      pararMuestra(); await cargarMedicos(); armarGrupos(); cargarLista();
    };
    el.appendChild(d);
  });
  el.querySelectorAll('.play-m').forEach(b => b.onclick = () => escucharMuestra(b.dataset.n, b));
}
$('#bAgrupar').onclick = () => { mostrar('voces'); armarGrupos(); };
$('#bActVoces').onclick = () => { pararMuestra(); armarGrupos(); };
$('#bVolverMed').onclick = () => $('#bVerMed').click();

