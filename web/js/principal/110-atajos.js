// Teclado configurable.
/* ------------------------------------------------ teclado configurable */
const ATAJOS = {
  play: {tecla:'F5', texto:'Reproducir / pausa', boton:'bPlay'},
  atras: {tecla:'F6', texto:'Atrás', boton:'bAtras'},
  adelante: {tecla:'F7', texto:'Adelante', boton:'bAdel'},
  aceptar: {tecla:'F10', texto:'Está bien', boton:'bAcep'},
  vista: {tecla:'F9', texto:'Vista previa Word', boton:'bVista'},
  lenta: {tecla:'F3', texto:'Reducir velocidad en 0,25×'},
  rapida: {tecla:'F4', texto:'Aumentar velocidad en 0,25×'},
  siguiente: {tecla:'F2', texto:'Siguiente marca', boton:'bSig'}
};
const TECLAS_FUNCION = Array.from({length:12}, (_,i) => 'F' + (i+1));
let atajos = {};
function cargarAtajos(){
  atajos = Object.fromEntries(Object.entries(ATAJOS).map(([id,a]) => [id,a.tecla]));
  try {
    const guardados = JSON.parse(leerLS('pref_teclado') || '{}');
    const candidato = Object.fromEntries(Object.keys(ATAJOS).map(id => [id,guardados[id] || ATAJOS[id].tecla]));
    if(Object.values(candidato).every(t => TECLAS_FUNCION.includes(t)) && new Set(Object.values(candidato)).size === Object.keys(ATAJOS).length) atajos = candidato;
  } catch(e){}
}
function actualizarAtajos(){
  cargarAtajos();
  document.querySelectorAll('[data-atajo]').forEach(el => el.textContent = atajos[el.dataset.atajo]);
  for(const [id,a] of Object.entries(ATAJOS)){
    const b = a.boton && document.getElementById(a.boton); if(!b) continue;
    const texto = id === 'atras' ? `Atrás ${PREF.salto()} segundos` : id === 'adelante' ? `Adelante ${PREF.salto()} segundos` : a.texto;
    b.title = `${texto} (${atajos[id]})`; b.setAttribute('aria-keyshortcuts', atajos[id]);
    const k = b.querySelector('kbd'); if(k) k.textContent = atajos[id];
  }
  document.querySelectorAll('#cfgAtajos select').forEach(el => el.value = atajos[el.dataset.accion]);
  if(!$('#vp').classList.contains('ampliado')) $('#vpCerrar').textContent = 'Ampliar · ' + atajos.vista;
}
function cambiarVelocidad(paso){
  const sel = $('#vel'), valores = [...sel.options].map(o => +o.value);
  sel.value = String(Math.max(Math.min(...valores), Math.min(Math.max(...valores), +sel.value + paso)));
  sel.dispatchEvent(new Event('change'));
}
for(const [id,a] of Object.entries(ATAJOS)){
  const fila = document.createElement('div'); fila.className = 'cfg-fila';
  const label = document.createElement('label'); label.className = 'cfg-txt'; label.htmlFor = 'atajo-' + id; label.textContent = a.texto;
  const sel = document.createElement('select'); sel.id = label.htmlFor; sel.dataset.accion = id;
  for(const t of TECLAS_FUNCION) sel.add(new Option(t,t));
  sel.onchange = () => {
    const otro = Object.keys(atajos).find(k => k !== id && atajos[k] === sel.value);
    if(otro){ toast(`${sel.value} ya está asignada a «${ATAJOS[otro].texto}».`); sel.value = atajos[id]; return; }
    atajos[id] = sel.value; grabarLS('pref_teclado', JSON.stringify(atajos)); actualizarAtajos(); mostrarGuardado();
  };
  fila.append(label,sel); $('#cfgAtajos').appendChild(fila);
}
$('#cfgAtajosRestablecer').onclick = () => { grabarLS('pref_teclado',''); actualizarAtajos(); mostrarGuardado(); };
// F5 tampoco debe recargar mientras un diálogo intercepta el teclado.
window.addEventListener('keydown', e => { if(e.key === 'F5') e.preventDefault(); }, true);
document.addEventListener('keydown', e => {
  const accion = !e.ctrlKey && !e.altKey && !e.metaKey && !e.shiftKey && Object.keys(atajos).find(id => atajos[id] === e.key);
  // Impedir las acciones del navegador incluso con un diálogo abierto o sin informe.
  if(accion || e.key === 'F5') e.preventDefault();
  if(!$('#config').hidden || $('#confirma').classList.contains('abierto') || $('#caso').hidden) return;
  if(accion){
    e.preventDefault();
    if(e.repeat && ['play','aceptar','vista'].includes(accion)) return;
    if(accion === 'play') bPlay.click();
    else if(accion === 'atras') $('#bAtras').click();
    else if(accion === 'adelante') $('#bAdel').click();
    else if(accion === 'aceptar') aceptar();
    else if(accion === 'vista') abrirVistaPrevia();
    else if(accion === 'lenta') cambiarVelocidad(-0.25);
    else if(accion === 'rapida') cambiarVelocidad(0.25);
    else if(accion === 'siguiente') siguiente(1);
    return;
  }
  if(vpAbierta()){
    if(e.key==='Escape' && !$('#vpMenu').hidden){ e.preventDefault(); return; }
    if(e.key==='Escape' && $('#vpPaleta').classList.contains('abierta')){ e.preventDefault(); cerrarPaleta(); return; }
    if(e.key==='Escape'){ e.preventDefault(); if($('#vp').classList.contains('ampliado')) cerrarVistaPrevia(); else ocultarExplica(); return; }
    if(e.target.closest('#vp')) tecladoFormato(e);
    return;
  }
  if(e.key==='Escape' && explicaDe){ ocultarExplica(); return; }
  if(e.ctrlKey && e.key.toLowerCase()==='s'){ e.preventDefault(); guardarBorrador().then(()=>toast('Borrador guardado.')).catch(e=>toast(e.message)); }
});
$('#bSig').onclick = () => siguiente(1);
$('#bAcep').onclick = aceptar;

