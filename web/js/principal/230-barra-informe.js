// Barra del informe adaptable.
/* ================================================ barra del informe adaptable
   La fila de acciones nunca se parte en dos: si no entra, se achica por pasos hasta que entre.
   n1: Borrar y Regenerar pasan al menú «Más» · n2: sin las teclas (F2, F8, F9) · n3: Vista previa solo con ícono
   n4: Cerrar estudio al menú · n5: textos cortos (Siguiente, N marcas) · n6: Copiar para Word solo con ícono
   n7: «Guardar Word» · n8: como último recurso, se deja partir en dos líneas.
   Los atajos siguen en los títulos de los botones y en el botón «?». */
const NIVELES_BARRA = 8;
function enMas(){
  return [...document.querySelectorAll('#filaAcciones .secundaria')].filter(b => !b.hidden && getComputedStyle(b).display === 'none');
}
function ajustarBarra(){
  const fila = $('#filaAcciones');
  if($('#caso').hidden || !fila.clientWidth) return;
  for(let n = 0; n <= NIVELES_BARRA; n++){
    for(let k = 1; k <= NIVELES_BARRA; k++) fila.classList.toggle('n' + k, k <= n);
    $('#masCaja').hidden = !enMas().length;
    if(fila.scrollWidth <= fila.clientWidth + 1) break;
  }
  if($('#masCaja').hidden) cerrarMas();
}
new ResizeObserver(() => ajustarBarra()).observe($('#barraCaso'));
if(document.fonts && document.fonts.ready) document.fonts.ready.then(ajustarBarra);

/* menú «Más»: las acciones que no entraron en la barra */
function abrirMas(){
  const m = $('#menuMas'); m.innerHTML = '';
  for(const b of enMas()){
    const x = document.createElement('button'); x.type = 'button'; x.setAttribute('role', 'menuitem');
    const ic = b.querySelector('svg');
    x.innerHTML = (ic ? ic.outerHTML : '<svg viewBox="0 0 24 24" aria-hidden="true"></svg>') + esc(b.dataset.menu || b.textContent.trim());
    if(b.id === 'bBorrarCaso') x.className = 'peligro-txt';
    x.title = b.title;
    x.onclick = () => { cerrarMas(); b.click(); };
    m.appendChild(x);
  }
  if(!m.children.length) return;
  m.hidden = false; $('#bMas').setAttribute('aria-expanded', 'true');
  m.firstElementChild.focus();
}
function cerrarMas(){ const m = $('#menuMas'); if(m.hidden) return; m.hidden = true; $('#bMas').setAttribute('aria-expanded', 'false'); }
$('#bMas').onclick = () => $('#menuMas').hidden ? abrirMas() : cerrarMas();
$('#menuMas').addEventListener('keydown', e => {
  const items = [...$('#menuMas').children], i = items.indexOf(document.activeElement);
  if(e.key === 'ArrowDown' || e.key === 'ArrowUp'){ e.preventDefault(); e.stopPropagation();
    items[(i + (e.key === 'ArrowDown' ? 1 : items.length - 1)) % items.length].focus(); }
  else if(e.key === 'Escape' || e.key === 'Tab'){ e.preventDefault(); e.stopPropagation(); cerrarMas(); $('#bMas').focus(); }
});

/* ventanita «?»: colores y atajos */
function abrirAyuda(ancla){
  const p = $('#ayudaPop'), b = ancla || $('#bAyuda');
  p.hidden = false;
  const r = b.getBoundingClientRect(), w = p.offsetWidth, h = p.offsetHeight;
  if(r.width){
    p.style.left = Math.max(12, Math.min(r.left, innerWidth - w - 12)) + 'px';
    p.style.top = (r.bottom + 6 + h < innerHeight - 12 ? r.bottom + 6 : Math.max(12, innerHeight - h - 12)) + 'px';
  } else { p.style.left = Math.max(12, (innerWidth - w) / 2) + 'px'; p.style.top = Math.max(12, (innerHeight - h) / 2) + 'px'; }
  $('#bAyuda').setAttribute('aria-expanded', 'true');
}
function cerrarAyuda(){ const p = $('#ayudaPop'); if(p.hidden) return; p.hidden = true; $('#bAyuda').setAttribute('aria-expanded', 'false'); }
$('#bAyuda').onclick = () => $('#ayudaPop').hidden ? abrirAyuda() : cerrarAyuda();
document.addEventListener('mousedown', e => {
  if(!$('#menuMas').hidden && !e.target.closest('#masCaja')) cerrarMas();
  if(!$('#ayudaPop').hidden && !e.target.closest('#ayudaPop,#bAyuda')) cerrarAyuda();
});
addEventListener('resize', cerrarAyuda);
document.addEventListener('keydown', e => {
  if(e.key === 'Escape' && !$('#ayudaPop').hidden && $('#config').hidden){ e.preventDefault(); e.stopPropagation(); cerrarAyuda(); }
}, true);

