// Un caso abierto no se abre en otra PC; tiempo de revisión.
/* ------------------------------------------------ bloqueo: un caso abierto no se abre en otra PC */
function soltarCaso(n){ if(!n) return; try { navigator.sendBeacon('/api/caso/soltar', JSON.stringify({nombre:n, rev: tomarRev()})); } catch(e){} }
setInterval(async () => { if(!actual) return;
  const rv = tomarRev();
  try { const b = await api('/api/caso/bloquear', {nombre: actual, rev: rv, renovar: true});
    if(!b.ok){ if(b.liberado) casoLiberado(); else toast('Atención: ' + b.por + ' abrió este caso. Tus cambios ya no se guardan.', [], 9000); } }
  catch(e){ revPend += rv; } }, 15000);
/* desde el panel de administración le sacaron el caso a esta PC (por ejemplo, para abrirlo en otra) */
function casoLiberado(){
  if(!actual) return;
  if(borradorPendiente()){
    audio.pause(); clearTimeout(tBorrador);
    estadoBorrador('Caso liberado desde otra PC. Conservá esta pantalla para recuperar tus cambios.', true);
    return; // no destruir texto local que aún no fue confirmado
  }
  audio.pause(); clearTimeout(tBorrador);
  actual = null; activa = null; ocultarExplica(); onda = null;
  audio.removeAttribute('src'); audio.load();
  mostrar('vacio');
  document.querySelectorAll('#casos li').forEach(li => li.classList.remove('sel'));
  toast('Desde el panel de administración se liberó este caso para que se pueda abrir en otra PC. Lo que escribiste quedó guardado como borrador hasta el último guardado automático.', [], 15000);
  cargarLista();
}

/* ------------------------------------------------ tiempo de revisión (para las estadísticas del panel de administración)
   Cuenta los segundos con un caso abierto en que se está trabajando: hubo teclado, mouse o rueda en el último minuto,
   o el audio está sonando. No cuenta con la ventana minimizada, escondida o en modo compacto. Se manda al servidor
   con cada renovación del bloqueo (15 s), al cerrar el caso y al guardar. */
let revPend = 0, revUltimaAccion = Date.now();
['keydown', 'mousedown', 'mousemove', 'wheel', 'touchstart'].forEach(ev =>
  document.addEventListener(ev, () => { revUltimaAccion = Date.now(); }, {passive: true, capture: true}));
setInterval(() => {
  if(!actual || document.hidden || document.body.classList.contains('compacto')) return;
  if(!audio.paused || Date.now() - revUltimaAccion < 60000) revPend++;
}, 1000);
function tomarRev(){ const s = revPend; revPend = 0; return s; }
addEventListener('pagehide', () => soltarCaso(actual));

