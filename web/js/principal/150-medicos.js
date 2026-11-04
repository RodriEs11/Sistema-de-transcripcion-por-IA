// Médicos.
/* ------------------------------------------------ medicos */
let medicos = [];
const NUEVO_MED = '__nuevo__';
const AUTO_MED = 'Automático (por la voz)';
// El select oculto conserva la integración con el caso y el reconocimiento por voz.
// El menú va en body para que el contenedor de la barra no recorte la lista.
const menuMedCaso = document.createElement('div');
menuMedCaso.id = 'menuMedCaso'; menuMedCaso.hidden = true;
menuMedCaso.innerHTML = '<input id="buscarMedCaso" type="search" placeholder="Buscar por nombre o apellido…" aria-label="Buscar médico por nombre o apellido" role="combobox" aria-autocomplete="list" aria-expanded="false" aria-controls="opcionesMedCaso" autocomplete="off"><div id="opcionesMedCaso" role="listbox" aria-label="Médicos"></div>';
document.body.appendChild(menuMedCaso);
let opcionMedCaso = -1;
function actualizarMedicoCaso(){
  const nombre = $('#medCaso').value || 'Médico: sin especificar';
  $('#nombreMedCaso').textContent = nombre;
  $('#bMedCaso').title = nombre + '. Buscar por nombre o apellido';
}
function cerrarMedicosCaso(foco=false){
  const menu = $('#menuMedCaso'); if(!menu) return;
  menu.hidden = true;
  $('#bMedCaso').setAttribute('aria-expanded', 'false');
  $('#buscarMedCaso').setAttribute('aria-expanded', 'false');
  $('#buscarMedCaso').removeAttribute('aria-activedescendant');
  if(foco) $('#bMedCaso').focus();
}
function ubicarMedicosCaso(){
  if(menuMedCaso.hidden) return;
  const r = $('#bMedCaso').getBoundingClientRect(), ancho = Math.min(320, innerWidth - 16);
  menuMedCaso.style.width = ancho + 'px';
  menuMedCaso.style.left = Math.max(8, Math.min(r.left, innerWidth - ancho - 8)) + 'px';
  menuMedCaso.style.top = (r.bottom + 4) + 'px';
  menuMedCaso.style.maxHeight = Math.max(80, Math.min(320, innerHeight * 0.5, innerHeight - r.bottom - 16)) + 'px';
}
function activarMedicoCaso(indice){
  const opciones = [...$('#opcionesMedCaso').querySelectorAll('button')];
  opcionMedCaso = opciones.length ? Math.max(0, Math.min(indice, opciones.length - 1)) : -1;
  opciones.forEach((b,i) => b.classList.toggle('activa', i === opcionMedCaso));
  const activa = opciones[opcionMedCaso];
  if(activa){ $('#buscarMedCaso').setAttribute('aria-activedescendant', activa.id); activa.scrollIntoView({block:'nearest'}); }
  else $('#buscarMedCaso').removeAttribute('aria-activedescendant');
}
function filtrarMedicosCaso(){
  const palabras = sinAcentos($('#buscarMedCaso').value).toLowerCase().trim().split(/\s+/).filter(Boolean);
  const opciones = [...$('#medCaso').options].filter(o => !palabras.length || (o.value && palabras.every(p => sinAcentos(o.text).toLowerCase().includes(p))));
  const lista = $('#opcionesMedCaso'); lista.replaceChildren();
  for(const [i,o] of opciones.entries()){
    const b = document.createElement('button'); b.type = 'button'; b.tabIndex = -1;
    b.id = 'opcionMedCaso' + i; b.setAttribute('role', 'option');
    b.setAttribute('aria-selected', String(o.value === $('#medCaso').value)); b.textContent = o.text;
    b.onclick = () => {
      $('#medCaso').value = o.value; actualizarMedicoCaso(); cerrarMedicosCaso(true);
      $('#medCaso').dispatchEvent(new Event('change', {bubbles:true}));
    };
    lista.appendChild(b);
  }
  if(!opciones.length) lista.innerHTML = '<div class="sin-medicos" role="status">No se encontraron médicos.</div>';
  activarMedicoCaso(Math.max(0, opciones.findIndex(o => o.value === $('#medCaso').value)));
}
$('#bMedCaso').onclick = () => {
  if(!menuMedCaso.hidden){ cerrarMedicosCaso(); return; }
  $('#buscarMedCaso').value = ''; menuMedCaso.hidden = false;
  $('#bMedCaso').setAttribute('aria-expanded', 'true'); $('#buscarMedCaso').setAttribute('aria-expanded', 'true');
  ubicarMedicosCaso(); filtrarMedicosCaso(); $('#buscarMedCaso').focus();
};
$('#bMedCaso').addEventListener('keydown', e => {
  if(e.key === 'ArrowDown' || e.key === 'ArrowUp'){ e.preventDefault(); e.stopPropagation(); if(menuMedCaso.hidden) $('#bMedCaso').click(); }
});
$('#buscarMedCaso').oninput = filtrarMedicosCaso;
menuMedCaso.addEventListener('keydown', e => {
  e.stopPropagation();
  if(e.key === 'Escape'){ e.preventDefault(); cerrarMedicosCaso(true); }
  else if(e.key === 'ArrowDown' || e.key === 'ArrowUp'){
    e.preventDefault(); activarMedicoCaso(opcionMedCaso + (e.key === 'ArrowDown' ? 1 : -1));
  } else if(e.key === 'Enter'){
    e.preventDefault(); const opciones = $('#opcionesMedCaso').querySelectorAll('button');
    if(opciones[opcionMedCaso]) opciones[opcionMedCaso].click();
  } else if(e.key === 'Tab'){ cerrarMedicosCaso(true); }
});
document.addEventListener('pointerdown', e => {
  if(!menuMedCaso.contains(e.target) && !e.target.closest('.med-selector')) cerrarMedicosCaso();
});
document.addEventListener('focusin', e => {
  if(!menuMedCaso.contains(e.target) && !e.target.closest('.med-selector')) cerrarMedicosCaso();
});
window.addEventListener('resize', ubicarMedicosCaso);
$('#bAgregarMedCaso').onclick = async () => {
  cerrarMedicosCaso(); const caso = actual, n = await nuevoMedico();
  if(!n || actual !== caso || !caso) return;
  llenarMedicos($('#medCaso'), n, 'Médico: sin especificar');
  $('#medCaso').dispatchEvent(new Event('change', {bubbles:true}));
};
const leerLS = k => { try { return localStorage.getItem(k) || ''; } catch(e){ return ''; } };
const grabarLS = (k,v) => { try { localStorage.setItem(k, v); } catch(e){} };
async function cargarMedicos(){
  try { medicos = (await api('/api/medicos')).medicos; } catch(e){ medicos = []; }
  llenarMedicos($('#medSubir'), MI.medico, AUTO_MED);
  if(actual) llenarMedicos($('#medCaso'), $('#medCaso').value, 'Médico: sin especificar');
}
function llenarMedicos(sel, valor, vacio){
  sel.innerHTML = `<option value="">${esc(vacio)}</option>` + medicos.map(m => `<option>${esc(m.nombre)}</option>`).join('')
    + (sel.id === 'medCaso' ? '' : `<option value="${NUEVO_MED}">+ Agregar médico…</option>`);
  sel.value = medicos.some(m => m.nombre===valor) ? valor : '';
  if(sel.id === 'medCaso'){ actualizarMedicoCaso(); if(!menuMedCaso.hidden) filtrarMedicosCaso(); }
}
async function nuevoMedico(){
  const igual = t => medicos.find(m => sinAcentos(m.nombre).toLowerCase().replace(/\s+/g, ' ') === sinAcentos(t).toLowerCase().replace(/\s+/g, ' '));
  const nota = 'Así va a aparecer en las listas para elegir el médico de cada audio.';
  const n = await pedirTexto({
    titulo: 'Agregar médico',
    html: '<p>La IA usa sus notas y sus informes anteriores para respetar su forma de dictar.</p>',
    etiqueta: 'Nombre del médico', placeholder: 'Ej.: Dra. Pérez', boton: 'Agregar', nota,
    faltaTxt: 'Escribí el nombre del médico.',
    alEscribir: t => { const m = t && igual(t); return m ? `Ya existe «${m.nombre}»: se elige ese.` : nota; },
    validar: t => t.length < 2 ? 'El nombre es demasiado corto.' : ''
  });
  if(!n) return null;
  const ya = igual(n);
  if(ya) return ya.nombre;
  try {
    const r = await api('/api/medico', {medico: n, notas: '', crear: true});
    await cargarMedicos(); toast(`Médico agregado: ${r.medico}`); return r.medico;
  } catch(e){ toast(e.sinConexion ? 'Sin conexión con el servidor: no se pudo agregar el médico. Probá de nuevo cuando vuelva.' : 'No se pudo agregar el médico: ' + e.message, [], 8000); return null; }
}
$('#medSubir').onchange = async e => {
  if(e.target.value===NUEVO_MED){ const n = await nuevoMedico(); llenarMedicos(e.target, n||'', AUTO_MED); }
  MI.medico = e.target.value;
  try { await api('/api/mi_medico', {medico: e.target.value}); } catch(err){ toast(err.message); }
};
$('#medCaso').onchange = async e => {
  const v = e.target.value; actualizarMedicoCaso();
  cambiarMedicoCaso(v);
};
let medSel = null;
function armarListaMed(){
  const ul = $('#listaMed'); ul.innerHTML = medicos.length ? '' : '<li style="cursor:default;color:var(--mu)">Todavía no hay médicos.</li>';
  for(const m of medicos){
    const li = document.createElement('li'); li.innerHTML = esc(m.nombre) + (m.propias ? '<span class="etq-mia" title="Usás tus propias notas de este médico">mías</span>' : '') + (m.voz ? `<span class="mvz" title="Muestras de voz registradas">${m.voz} ${m.voz===1 ? 'muestra' : 'muestras'}</span>` : '');
    if(m.nombre===medSel) li.classList.add('sel');
    li.onclick = () => { medSel = m.nombre; $('#medNombre').value = m.nombre; $('#medNotas').value = m.notas; armarListaMed(); armarVozMedico(m.nombre); };
    ul.appendChild(li);
  }
  const m = medicos.find(x => x.nombre === medSel);
  $('#medOrigen').hidden = !(m && MI.usuario && m.propias);
  $('#medOrigenTxt').textContent = 'Tus notas: la IA las usa en tus informes de este médico. Los demás usan las generales.';
}
$('#bMedGeneral').onclick = async () => {
  if(!medSel || !await confirmar(`¿Volver a las notas generales de ${medSel}?`, '<p>Se borran tus notas propias de este médico.</p>', 'Volver a las generales')) return;
  try { await api('/api/medico', {medico: medSel, destino: 'general'}); await cargarMedicos(); $('#bVerMed').click(); toast('Listo: usás las notas generales.'); } catch(e){ toast(e.message); }
};
$('#bVerMed').onclick = async () => { if(actual) guardarBorrador().catch(()=>{}); await cargarMedicos(); mostrar('med');
  if(!medSel && medicos[0]){ medSel = medicos[0].nombre; }
  const m = medicos.find(x=>x.nombre===medSel); $('#medNombre').value = m ? m.nombre : ''; $('#medNotas').value = m ? m.notas : ''; armarListaMed();
  armarVozMedico(m ? m.nombre : ''); contarSinEtiquetar(); };
$('#bNuevoMed').onclick = async () => { const n = await nuevoMedico(); if(n){ medSel = n; $('#bVerMed').click(); } };
$('#bGuardarMed').onclick = async () => {
  if(!medSel){ toast('Elegí o agregá un médico.'); return; }
  const destino = await elegirDestino('las notas de ' + medSel); if(!destino) return;
  try { await api('/api/medico', {medico: medSel, notas: $('#medNotas').value, destino}); }
  catch(e){ toast(e.message); return; }
  await cargarMedicos(); armarListaMed(); toast(destino === 'mio' ? 'Notas guardadas solo para vos.' : 'Notas guardadas para todos.');
};
cargarMedicos();

