// Plantillas y estudio sin plantilla.
/* ------------------------------------------------ plantillas */
let secs = [], plSel = -1;
function volcarPl(){ if(plSel>=0 && secs[plSel]){ secs[plSel].nombre = $('#plNombre').value; secs[plSel].cuerpo = $('#plCuerpo').value; } }
const ORIGEN_PL = {propia: ['mía', 'Tu versión: la IA la usa en tus informes. Los demás usan la general.'],
                   nueva: ['solo mía', 'Plantilla que agregaste solo para vos.']};
function armarListaPl(){
  const ul = $('#listaPl'); ul.innerHTML = '';
  secs.forEach((x,i) => { const li = document.createElement('li'); li.textContent = x.nombre || '(sin nombre)';
    if(ORIGEN_PL[x.origen]){ const t = document.createElement('span'); t.className = 'etq-mia'; t.textContent = ORIGEN_PL[x.origen][0]; li.appendChild(t); }
    if(i===plSel) li.classList.add('sel');
    li.onclick = () => { volcarPl(); plSel = i; $('#plNombre').value = x.nombre; $('#plCuerpo').value = x.cuerpo; armarListaPl(); }; ul.appendChild(li); });
  const x = secs[plSel], o = x && MI.usuario && ORIGEN_PL[x.origen];
  $('#plOrigen').hidden = !o;
  if(o){ $('#plOrigenTxt').textContent = o[1]; $('#bPlGeneral').hidden = x.origen !== 'propia'; }
}
$('#bPlGeneral').onclick = async () => {
  const x = secs[plSel]; if(!x) return;
  if(!await confirmar(`¿Volver a la plantilla general de «${x.nombre}»?`, '<p>Se deja de usar tu versión (queda una copia en tu carpeta). Los cambios sin guardar de las demás plantillas se pierden.</p>', 'Volver a la general', 'prim')) return;
  try { await api('/api/plantillas/general', {nombre: x.nombre}); toast('Listo: usás la plantilla general.'); abrirPlantillas(); } catch(e){ toast(e.message); }
};
async function abrirPlantillas(nueva){
  if(actual) guardarBorrador().catch(()=>{});
  secs = (await api('/api/plantillas')).secciones; plSel = secs.length ? 0 : -1;
  if(nueva){ secs.push(nueva); plSel = secs.length-1; }
  mostrar('plant');
  $('#plNombre').value = plSel>=0 ? secs[plSel].nombre : ''; $('#plCuerpo').value = plSel>=0 ? secs[plSel].cuerpo : '';
  armarListaPl();
  if(nueva) toast('Revisá la plantilla nueva: dejá en PROTOCOLO NORMAL solo lo que es normal o fijo, y tocá "Guardar cambios".', [], 9000);
}
$('#bVerPlant').onclick = () => abrirPlantillas();
$('#plWord').onchange = async e => {
  const f = e.target.files[0]; e.target.value = ''; if(!f) return;
  try{
    const j = await pedir('/api/plantilla_word?archivo='+encodeURIComponent(f.name), {method:'POST', body:f});
    volcarPl(); secs.push(j); plSel = secs.length-1; $('#plNombre').value = j.nombre; $('#plCuerpo').value = j.cuerpo; armarListaPl();
    toast('Plantilla armada desde el Word: revisala. Si es la forma de un médico, agregá al nombre "(estilo Apellido)". Después "Guardar cambios".', [], 10000);
  }catch(err){ toast(err.message, [], 8000); }
};
$('#bImportar').onclick = async () => {
  try{ const r = await api('/api/importar', {});
    toast(`Importados ${r.ok.length} informes de referencia.` + (r.mal.length ? ` No se pudieron leer: ${r.mal.join(', ')}` : '') +
          ' La IA los usa para copiar el estilo de esos estudios.', [], 8000);
  }catch(e){ toast(e.message); }
};
$('#plNombre').oninput = () => { volcarPl(); const li = $('#listaPl').children[plSel]; if(li) li.textContent = $('#plNombre').value || '(sin nombre)'; };
$('#bNuevoEst').onclick = () => { volcarPl(); secs.push({nombre: 'ESTUDIO NUEVO', cuerpo: 'TITULO: \nTEXTO FIJO:\n\nPROTOCOLO NORMAL:\n-\nFRASES HABITUALES:\n-\nNOTAS (cómo se dicta, orden de las medidas, etc.):\n- '}); plSel = secs.length-1;
  $('#plNombre').value = secs[plSel].nombre; $('#plCuerpo').value = secs[plSel].cuerpo; armarListaPl(); $('#plNombre').select(); };
$('#bBorrarPl').onclick = async () => { if(plSel<0 || !await confirmar(`¿Eliminar la plantilla «${secs[plSel].nombre}»?`,
    '<p>Se guarda una copia de la versión anterior al tocar <b>Guardar cambios</b>.</p>', 'Eliminar')) return;
  secs.splice(plSel,1); plSel = Math.min(plSel, secs.length-1);
  $('#plNombre').value = plSel>=0 ? secs[plSel].nombre : ''; $('#plCuerpo').value = plSel>=0 ? secs[plSel].cuerpo : ''; armarListaPl(); };
$('#bGuardarPl').onclick = async () => { volcarPl();
  const destino = await elegirDestino('los cambios de las plantillas'); if(!destino) return;
  try{ const r = await api('/api/plantillas', {secciones: secs.map(x => ({nombre: x.nombre, cuerpo: x.cuerpo})), destino});
    if(r.sin_cambios){ toast('No había cambios para guardar.'); return; }
    toast((destino === 'mio' ? 'Guardadas solo para vos.' : 'Plantillas guardadas para todos.') + ' Se usan desde el próximo informe.'
          + (r.no_borradas && r.no_borradas.length ? ` «${r.no_borradas.join('», «')}» es general: para eliminarla elegí «Para todos».` : ''), [], 8000);
    const sel = secs[plSel] && secs[plSel].nombre; await abrirPlantillas();
    const i = secs.findIndex(x => x.nombre === sel); if(i >= 0){ plSel = i; $('#plNombre').value = secs[i].nombre; $('#plCuerpo').value = secs[i].cuerpo; armarListaPl(); }
  }catch(e){ toast(e.message); } };

/* ------------------------------------------------ estudio sin plantilla */
function armarNuevoEstudio(titulos){
  const box = $('#nuevoEst');
  if(!titulos.length){ box.style.display='none'; box.innerHTML=''; return; }
  box.style.display='block';
  box.innerHTML = '<b>Estudio sin plantilla:</b> ' + titulos.map(t => '«'+esc(t)+'»').join(', ') +
    '. La IA lo armó sin modelo: revisalo con más cuidado. Cuando esté corregido, creá su plantilla para los próximos. ';
  for(const t of titulos){ const b = document.createElement('button'); b.className='chico'; b.textContent = 'Crear plantilla de «'+t+'»';
    b.onclick = () => abrirPlantillas(plantillaDesdeInforme(t)); box.appendChild(b); }
}
function plantillaDesdeInforme(titulo){
  const ls = textoFinal().split('\n'); let i = ls.findIndex(l => l.trim()===titulo.trim()), cuerpo = [];
  if(i>=0){ for(let j=i+1;j<ls.length;j++){ const l = ls[j].trim();
      if(/^lo saluda/i.test(l) || /^categorizaci/i.test(l)) break;
      if(l && !l.startsWith('-') && cuerpo.length) break;
      if(l.startsWith('-')) cuerpo.push(l.replace(/\d+(?:[.,]\d+)?/g, '<N>')); } }   // las medidas del paciente no van en la plantilla
  const nombre = titulo.replace(/\(.*?\)/g,'').trim().toUpperCase();
  return {nombre, cuerpo: `TITULO: ${titulo}\nPROTOCOLO NORMAL (revisá: dejá solo lo que se escribe cuando es normal):\n${cuerpo.join('\n') || '-'}\nFRASES HABITUALES:\n-\nNOTAS (cómo se dicta, orden de las medidas, etc.):\n- `};
}

