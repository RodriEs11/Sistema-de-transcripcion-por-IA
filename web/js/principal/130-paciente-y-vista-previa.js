// Nombre del paciente y vista previa como Word.
/* ------------------------------------------------ nombre del paciente (solo para mostrar, no va al informe) */
function lineaEstudio(c){      // "Mamografía + Eco mamaria · 1:40" debajo del nombre
  if(!c.estudios && !c.dur) return '';
  return `<span class="est" title="${esc([c.estudios ? 'Estudios: ' + c.estudios : '', c.dur ? 'audio de ' + mmss(c.dur) : ''].filter(Boolean).join(' · '))}">`
    + (c.estudios ? esc(c.estudios) : '') + (c.estudios && c.dur ? ' · ' : '') + (c.dur ? `<span class="dur">${mmss(c.dur)}</span>` : '') + '</span>';
}
function ponerTitulo(pac, audio, revisado, info){
  const h = $('#titulo'), t = pac || audio;
  if(info) h.dataset.info = JSON.stringify(info); else info = JSON.parse(h.dataset.info || '{}');
  h.textContent = t + (revisado ? ' ✓' : ''); h.dataset.t = t; h.dataset.pac = pac || ''; h.dataset.audio = audio;
  h.title = pac ? 'Paciente (sacado del dictado)' : 'No se encontró el nombre del paciente en el dictado';
  const extra = [info.estudios, info.dur ? mmss(info.dur) : '', pac ? 'audio ' + audio : ''].filter(Boolean);
  $('#tituloAudio').textContent = extra.length ? '· ' + extra.join(' · ') : '';
  $('#tituloAudio').title = info.estudios ? 'Estudios detectados en el informe' : '';
}
$('#bPaciente').onclick = async () => {
  if(!actual) return;
  const h = $('#titulo'), n = actual;
  const v = await pedirTexto({titulo: 'Nombre del paciente', html: '<p>Solo se muestra en la lista; no va al informe.</p>',
    etiqueta: 'Nombre', valor: h.dataset.pac || '', placeholder: 'Ej.: Pérez, María', boton: 'Guardar', vacio: true,
    nota: 'Dejalo vacío para volver a sacarlo del dictado.'});
  if(v === null) return;
  try {
    const r = await api('/api/paciente', {nombre: n, paciente: v});
    if(actual === n) ponerTitulo(r.paciente, h.dataset.audio, h.textContent.endsWith('✓'));
    toast(r.paciente ? 'Paciente: ' + r.paciente : 'No se encontró el nombre en el dictado.'); cargarLista();
  } catch(e){ toast(e.message); }
};
window.addEventListener('beforeunload', e => {
  if(borradorPendiente()){ e.preventDefault(); e.returnValue = ''; }
}); // no enviar un beacon sin orden ni confirmación que pueda pisar una escritura más nueva

let FORMATO = {palabras_titulo: [], negrita_titulos: true, prefijos: [], exactas: []};
api('/api/formato').then(f => FORMATO = f).catch(()=>{});
const sinAcentos = t => t.normalize('NFD').replace(/[\u0300-\u036f]/g,'');
function enNegrita(l){
  const x = l.trim(); if(!x) return false;
  if(FORMATO.prefijos.some(p => x.startsWith(p))) return true;
  if((FORMATO.exactas || []).includes(x.replace(/:$/, ''))) return true;
  if(!FORMATO.negrita_titulos || x.startsWith('-') || /[.:]$/.test(x) || x.length>110) return false;
  const w = (sinAcentos(x.toLowerCase()).match(/[a-z]+/) || [''])[0];
  return FORMATO.palabras_titulo.includes(w);
}
/* Copia con formato. Las negritas y los renglones vacíos salen del servidor (el mismo código que arma el Word);
   si no responde, se arma acá con la regla aproximada. */
async function copiarParaWord(){
  const t = textoFinal();
  let pars = null;
  await guardarFormato();
  try { pars = (await api('/api/vista_previa', {texto: t, nombre: actual})).parrafos; } catch(e){}
  if(!pars) pars = t.split('\n').map(l => l.trim() ? {t: l, b: enNegrita(l)} : null);
  const fuente = (VP && VP.fuente) || 'Tahoma', tam = (VP && VP.tamano) || 12;
  const est = `margin:0;font-family:${fuente};font-size:${tam}pt`;
  const run = r => { let h = esc(r.t); if(r.u) h = '<u>'+h+'</u>'; if(r.i) h = '<i>'+h+'</i>'; if(r.b) h = '<b>'+h+'</b>';
    if(r.x) h = '<s>'+h+'</s>';
    return `<span style="${r.c ? 'color:'+esc(r.c)+';' : ''}${r.h ? 'background-color:'+esc(r.h)+';' : ''}${r.f ? 'font-family:'+esc(r.f)+';' : ''}${r.s ? 'font-size:'+Number(r.s)+'pt;' : ''}">${h}</span>`; };
  const html = `<div style="font-family:${fuente};font-size:${tam}pt">` + pars.map(p => !p ? `<p style="${est}">&nbsp;</p>`
    : `<p style="${est};text-align:${p.a || 'left'}">${(p.r && p.r.length ? p.r : [{t: p.t, b: p.b}]).map(run).join('')}</p>`).join('') + '</div>';
  const plano = pars.map(p => p ? p.t : '').join('\n');
  try{
    await navigator.clipboard.write([new ClipboardItem({'text/html': new Blob([html],{type:'text/html'}), 'text/plain': new Blob([plano],{type:'text/plain'})})]);
  }catch(e){
    try { await navigator.clipboard.writeText(plano); } catch(e2){ toast('No se pudo copiar: ' + e2.message); return; }
  }
  const n = marcasPend().length;
  toast(n ? `Copiado (ojo: quedan ${n} marcas sin revisar).` : 'Copiado. Pegalo en tu Word con Ctrl+V.');
}
$('#bCopiar').onclick = copiarParaWord;

/* ------------------------------------------------ vista previa como Word */
let VP = null;                         // último resultado de /api/vista_previa
const vpAbierta = () => $('#vp').classList.contains('abierta');
const cmPx = cm => cm * 96 / 2.54;
async function abrirVistaPrevia(){
  if(!actual) return;
  if(!VP || VP.caso !== actual){ if(!await cargarEditorRevision(actual)) return; }
  const ampliado = !$('#vp').classList.contains('ampliado');
  $('#vp').classList.toggle('ampliado', ampliado);
  $('#vp').setAttribute('role', ampliado ? 'dialog' : 'region');
  if(ampliado) $('#vp').setAttribute('aria-modal', 'true'); else $('#vp').removeAttribute('aria-modal');
  $('#vpCerrar').textContent = ampliado ? 'Volver junto al audio · Esc' : 'Ampliar · ' + atajos.vista;
  zoomVistaPrevia();
}
function cerrarVistaPrevia(){
  cerrarMenuWord(); cerrarPaleta(); guardarFormato();
  $('#vp').classList.remove('ampliado'); $('#vp').setAttribute('role','region'); $('#vp').removeAttribute('aria-modal');
  $('#vpCerrar').textContent = 'Ampliar · ' + atajos.vista; zoomVistaPrevia();
}
function avisoVistaPrevia(){
  const box = $('#vpAviso'), n = marcasPend().length + omis.filter(o => !omisOk.includes(o.dato)).length;
  const completar = textoFinal().includes('[COMPLETAR');
  if(!n && !completar){ box.style.display = 'none'; return; }
  box.innerHTML = '<b>' + (completar ? 'Falta completar un dato' + (n ? ` y quedan ${n} ${n===1?'marca':'marcas'} sin revisar` : '')
                                      : `Quedan ${n} ${n===1?'marca':'marcas'} sin revisar`) + '.</b> Las marcas se muestran sobre el informe mientras lo revisás.';
  const b = document.createElement('button'); b.className = 'chico'; b.textContent = completar ? 'Ir al dato' : 'Ir a la siguiente marca';
  b.onclick = () => { cerrarVistaPrevia(); const m = completar && editor.querySelector('.m-completar'); m ? seleccionar(m) : siguiente(1); };
  box.appendChild(b); box.style.display = 'flex';
}
/* Editor A4 y formato: web/editor_word.js */
$('#bFin').onclick = async () => {
  const n = marcasPend().length + omis.filter(o => !omisOk.includes(o.dato)).length, t = textoFinal();
  if(t.includes('[COMPLETAR')){ toast('Todavía hay un [COMPLETAR] en el informe.'); const m = editor.querySelector('.m-completar'); if(m) seleccionar(m,false); return; }
  if(n && !await confirmar(n === 1 ? 'Queda 1 marca sin revisar' : `Quedan ${n} marcas sin revisar`,
      '<p>¿Guardar el Word igual? La IA aprende de lo que quede como está.</p>', 'Guardar igual', 'prim')) return;
  try{
    await guardarFormato(true);
    const rv = tomarRev();
    const r = await api('/api/finalizar', {nombre: actual, texto: t, rev: rv}).catch(e => { revPend += rv; throw e; });
    const n = actual, tit = $('#titulo').dataset.t || n;
    if(MI.remoto){
      const a = document.createElement('a'); a.href = '/api/word?nombre=' + encodeURIComponent(n);
      a.download = tit + '.docx'; document.body.appendChild(a); a.click(); a.remove();
    }
    // el informe se cierra (queda libre para las otras PC) y se vuelve a la pantalla de inicio
    const sig = casosCache.filter(c => c.estado==='listo' && !c.bloqueado_por && c.nombre!==n && (filtro!=='mia' || c.origen===MI.pc))
      .sort((a, b) => a.fecha - b.fecha)[0];
    if(vpAbierta()) cerrarVistaPrevia();
    await cerrarCaso(true);
    const botones = [];
    if(!MI.remoto) botones.push(['Abrir Word', () => api('/api/abrir', {nombre: n})]);
    if(sig) botones.push(['Revisar el siguiente', () => abrirCaso(sig.nombre)]);
    toast(`${MI.remoto ? 'Word descargado en esta PC' : 'Word guardado'} (${tit}) · corregiste el ${r.pct}% de las palabras. ${r.aprendizaje === 'pendiente' ? 'El aprendizaje continúa en segundo plano.' : 'La IA ya lo usa como ejemplo.'}`, botones, 9000);
  }catch(e){ toast(e.message); }
};
/* El informe lo armó la IA con el estilo de otro transcriptor (o el general): se avisa y se ofrece regenerarlo */
function armarAvisoEstilo(c){
  const e = c.estilo, yo = MI.usuario && MI.usuario.clave;
  const otro = yo && e && !c.revisado && e.usuario !== yo;
  $('#estiloAviso').hidden = !otro;
  if(otro) $('#estiloTxt').textContent = e.usuario ? `La IA armó este informe con el estilo de ${e.nombre}.` : 'La IA armó este informe con el estilo general (no con el tuyo).';
}
$('#bRegenMio').onclick = async () => {
  if(!await confirmar('¿Regenerar el informe con tu estilo?', '<p>La IA lo vuelve a armar con tus plantillas, tus notas y lo que aprendió de tus correcciones. Se pierden los cambios que hiciste en este informe.</p>', 'Regenerar', 'prim')) return;
  await api('/api/procesar', {nombre: actual});
  audio.pause(); mostrar('vacio'); soltarCaso(actual); actual = null; cargarLista();
  toast('Se está volviendo a armar con tu estilo. Aparece en la lista cuando esté listo.');
};
$('#bRegen').onclick = async () => {
  if(!await confirmar('¿Volver a generar el informe con la IA?', '<p>Se pierden los cambios que hiciste en este informe.</p>', 'Regenerar')) return;
  await api('/api/procesar', {nombre: actual});
  audio.pause(); mostrar('vacio'); soltarCaso(actual); actual = null; cargarLista();
};

