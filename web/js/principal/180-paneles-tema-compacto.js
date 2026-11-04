// Paneles ajustables, tema claro/oscuro y modo compacto.
/* ================================================ paneles ajustables
   Se arrastran los divisores (o se mueven con las flechas si tienen el foco). Doble clic vuelve al tamaño
   original. Cada medida queda guardada en esta PC (en la app, para el usuario de Windows). */
function divisor(el, o){
  const aplicar = v => { o.poner(v); return v; };
  const limitar = v => Math.min(o.max(), Math.max(o.min(), v));
  let actual = Number(leerLS(o.clave)) || o.inicial;
  const guardar = () => grabarLS(o.clave, String(actual));
  const reponer = () => { actual = limitar(actual); aplicar(actual); };
  reponer();
  addEventListener('resize', reponer);
  el.addEventListener('pointerdown', e => {
    if(e.button !== 0) return;
    e.preventDefault(); el.setPointerCapture(e.pointerId);
    el.classList.add('arrastrando'); document.body.classList.add('redimensionando');
    const x0 = e.clientX, v0 = actual;
    const mover = ev => { actual = limitar(o.desdeArrastre(v0, ev.clientX - x0)); aplicar(actual); };
    const soltar = () => { el.classList.remove('arrastrando'); document.body.classList.remove('redimensionando');
      el.removeEventListener('pointermove', mover); el.removeEventListener('pointerup', soltar); el.removeEventListener('pointercancel', soltar);
      guardar(); if(o.alTerminar) o.alTerminar(); };
    el.addEventListener('pointermove', mover); el.addEventListener('pointerup', soltar); el.addEventListener('pointercancel', soltar);
  });
  el.addEventListener('dblclick', () => { actual = limitar(o.inicial); aplicar(actual); guardar(); if(o.alTerminar) o.alTerminar(); });
  el.addEventListener('keydown', e => {
    const paso = e.shiftKey ? 64 : 16;
    if(e.key === 'ArrowLeft' || e.key === 'ArrowRight'){ e.preventDefault(); e.stopPropagation();
      actual = limitar(o.desdeArrastre(actual, e.key === 'ArrowLeft' ? -paso : paso)); aplicar(actual); guardar(); if(o.alTerminar) o.alTerminar(); }
    else if(e.key === 'Home'){ e.preventDefault(); el.dispatchEvent(new Event('dblclick')); }
  });
}
/* lista de audios: ancho en px */
divisor($('#divLista'), {clave: 'anchoLista', inicial: 270,
  min: () => 200, max: () => Math.max(240, Math.min(620, innerWidth * 0.45)),
  desdeArrastre: (v0, dx) => v0 + dx,
  poner: v => document.querySelector('.app').style.setProperty('--ancho-lista', Math.round(v) + 'px')});
/* informe | dictado: proporción del ancho que se lleva el informe (0,25 a 0,8) */
{
  const cols = document.querySelector('.cols');
  const ancho = () => Math.max(1, cols.clientWidth - 32 - 16);
  const visible = () => cols.clientWidth > 600;         // con el caso cerrado no hay ancho para medir
  divisor($('#divCols'), {clave: 'propInforme', inicial: 1.35 / 2.35,
    min: () => visible() ? Math.min(0.5, Math.max(0.25, 300 / ancho())) : 0.25,
    max: () => visible() ? Math.max(0.5, Math.min(0.8, 1 - 240 / ancho())) : 0.8,
    desdeArrastre: (p0, dx) => p0 + dx / ancho(),
    poner: p => { cols.style.setProperty('--fr-hoja', p.toFixed(4) + 'fr'); cols.style.setProperty('--fr-dict', (1 - p).toFixed(4) + 'fr'); },
    alTerminar: () => requestAnimationFrame(dibujarOnda)});
}
/* listas de Plantillas y Médicos: el mismo ancho para las dos */
document.querySelectorAll('.div-lista2').forEach(d => divisor(d, {clave: 'anchoLista2', inicial: 240,
  min: () => 160, max: () => Math.max(200, Math.min(560, innerWidth * 0.4)),
  desdeArrastre: (v0, dx) => v0 + dx,
  poner: v => document.querySelectorAll('.fila2').forEach(f => f.style.setProperty('--ancho-lista2', Math.round(v) + 'px'))}));

/* ================================================ tema claro / oscuro */
const EN_APP = !!(window.chrome && window.chrome.webview);     // dentro de la aplicación del trabajo
const mqOscuro = matchMedia('(prefers-color-scheme: dark)');
const cssVar = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const colorDe = c => c.replace(/var\((--[\w-]+)\)/, (_, v) => cssVar(v));
function temaEfectivo(){ return document.documentElement.dataset.theme || (mqOscuro.matches ? 'dark' : 'light'); }
function aplicarTema(){
  const t = temaEfectivo();
  document.documentElement.dataset.temaEfectivo = t;
  $('#bTema').title = t==='dark' ? 'Cambiar a modo claro' : 'Cambiar a modo oscuro';
  if(EN_APP) try { chrome.webview.postMessage({accion:'tema', oscuro: t==='dark'}); } catch(e){}
  dibujarOnda();
}
$('#bTema').onclick = () => {
  const t = temaEfectivo()==='dark' ? 'light' : 'dark';
  document.documentElement.dataset.theme = t; grabarLS('tema', t); aplicarTema();
};
mqOscuro.addEventListener('change', aplicarTema);

/* ================================================ modo compacto: solo la cola y los avisos */
function esCompacto(){ return document.body.classList.contains('compacto'); }
window.ponerCompacto = function(si){          // la aplicación del trabajo también la llama
  document.body.classList.toggle('compacto', !!si);
  if(si){ audio.pause(); ocultarExplica(); }
  if(!EN_APP) grabarLS('compacto', si ? '1' : '');
  $('#bCompacto').title = si ? 'Agrandar la ventana' : 'Modo compacto: solo la cola y los avisos';
  if(!si) requestAnimationFrame(dibujarOnda);
  aplicarLista();                              // en el modo compacto la lista siempre se ve
};
function agrandar(){
  if(EN_APP) try { chrome.webview.postMessage({accion:'agrandar'}); } catch(e){}
  ponerCompacto(false);
}
$('#bCompacto').onclick = () => esCompacto() ? agrandar() : ponerCompacto(true);
if(EN_APP) $('#bCompacto').style.display = 'none';      // en la aplicación lo maneja su barra de arriba
else if(leerLS('compacto')) ponerCompacto(true);

