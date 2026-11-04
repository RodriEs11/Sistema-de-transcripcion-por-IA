// Texto final y borrador; borrar informes.
/* ------------------------------------------------ texto final / borrador */
function textoFinal(){
  const lineas = [];
  editor.childNodes.forEach(n => {
    if(n.nodeType===3){ lineas.push(...n.textContent.split('\n')); }
    else if(n.nodeType===1){ (n.innerText ?? n.textContent).replace(/\n$/,'').split('\n').forEach(x => lineas.push(x)); }
  });
  return lineas.map(l => l.replace(/ /g,' ').replace(/\s+$/,'')).join('\n').replace(/^\n+|\n+$/g,'');
}
const BORRADOR = {cola: Promise.resolve(), pendientes: 0, confirmado: new Map(), revision: new Map(), fallidos: new Set()};
function capturarBorrador(){ return {nombre: actual, html: htmlLimpio(), omisiones_ok: [...omisOk]}; }
function firmaBorrador(d){ return JSON.stringify([d.html, d.omisiones_ok]); }
function estadoBorrador(texto, error=false){
  $('#guardadoBorrador').hidden = !texto;
  $('#estadoBorrador').textContent = texto;
  $('#reintentarBorrador').hidden = !error;
}
function borradorPendiente(){
  return !!actual && (BORRADOR.pendientes > 0 || BORRADOR.fallidos.has(actual) || BORRADOR.confirmado.get(actual) !== firmaBorrador(capturarBorrador())
    || (typeof FMT !== 'undefined' && !!(FMT.pendiente || FMT.guardando)));
}
function programarBorrador(){
  clearTimeout(tBorrador); estadoBorrador('Cambios sin guardar');
  tBorrador = setTimeout(()=>guardarBorrador().catch(()=>{}), 1500);
}
function enviarBorrador(datos){
  // Una única fila de escrituras para autoguardado y formato. Capturar antes de esperar.
  const copia = {...datos, omisiones_ok: [...datos.omisiones_ok]};
  BORRADOR.pendientes++;
  if(actual === copia.nombre) estadoBorrador('Guardando…');
  const tarea = BORRADOR.cola.then(async () => {
    const revision = BORRADOR.revision.get(copia.nombre);
    const r = await api('/api/borrador', {...copia, ...(Number.isInteger(revision) ? {revision} : {})});
    if(r.ok !== true) throw new Error('El servidor no confirmó el guardado del borrador.');
    if((Number.isSafeInteger(revision) || r.revision !== undefined) &&
       (!Number.isSafeInteger(r.revision) || r.revision < 1 || (Number.isSafeInteger(revision) && r.revision < revision)))
      throw new Error('El servidor no confirmó una revisión válida del borrador.');
    BORRADOR.revision.set(copia.nombre, r.revision);
    BORRADOR.fallidos.delete(copia.nombre);
    BORRADOR.confirmado.set(copia.nombre, firmaBorrador(copia));
  }).catch(e => {
    BORRADOR.fallidos.add(copia.nombre);
    if(actual === copia.nombre){
      estadoBorrador(e.status === 409 ? e.message : 'No se pudo guardar. Conservá esta pantalla y reintentá.', true);
      clearTimeout(tBorrador);
      if(e.status !== 409) tBorrador = setTimeout(()=>{ if(actual === copia.nombre) guardarBorrador().catch(()=>{}); }, 10000);
    }
    throw e;
  }).finally(() => {
    BORRADOR.pendientes--;
    if(actual === copia.nombre && !borradorPendiente()) estadoBorrador('Borrador guardado');
    else if(actual === copia.nombre && !BORRADOR.pendientes && !BORRADOR.fallidos.has(copia.nombre)) estadoBorrador('Cambios sin guardar');
  });
  BORRADOR.cola = tarea.catch(()=>{}); // la siguiente escritura debe poder reintentar
  return tarea;
}
function guardarBorrador(){
  if(!actual) return Promise.resolve();
  clearTimeout(tBorrador);
  return enviarBorrador(capturarBorrador());
}
$('#reintentarBorrador').onclick = async () => {
  try { await guardarFormato(true); await guardarBorrador(); } catch(e){ toast(e.message); }
};
/* Cerrar el estudio: guarda el borrador, lo libera para las otras PC y vuelve a la lista */
async function cerrarCaso(silencioso){
  if(!actual) return;
  const n = actual, tit = $('#titulo').dataset.t || n;
  audio.pause();
  try { await guardarFormato(true); await guardarBorrador(); }
  catch(e){ toast('No se cerró el estudio: ' + e.message); return false; }
  if(borradorPendiente()){ toast('Hay cambios nuevos sin guardar. Volvé a cerrar el estudio cuando termines de editar.'); return false; }
  actual = null; activa = null; ocultarExplica(); onda = null;
  { const rv = tomarRev(); try { await api('/api/caso/soltar', {nombre: n, rev: rv}); } catch(e){ revPend += rv; soltarCaso(n); } }
  audio.removeAttribute('src'); audio.load();
  mostrar('vacio');
  document.querySelectorAll('#casos li').forEach(li => li.classList.remove('sel'));
  if(!silencioso) toast('Cerraste ' + tit + '. Tus cambios quedaron guardados y el estudio está libre.');
  cargarLista();
}
$('#bCerrar').onclick = cerrarCaso;

/* ------------------------------------------------ borrar informes (audio, informe y Word; lo aprendido queda) */
/* Ventanas propias (en lugar de las del navegador, que en la app se ven como "La página dice…").
   confirmar(titulo, html, boton, clase) → true/false · clase 'peligro' (rojo, por defecto) o 'prim' (azul).
   pedirTexto({titulo, html, etiqueta, valor, placeholder, boton, vacio, validar}) → el texto, o null si se cancela.
   validar(texto) devuelve '' si está bien o el mensaje a mostrar debajo del campo. */
function modal(o){
  return new Promise(res => {
    const d = $('#confirma'), si = $('#cfSi'), no = $('#cfNo'), otro = $('#cfOtro'), inp = $('#cfInput'), aviso = $('#cfAviso'), previo = document.activeElement;
    const conCampo = !!o.campo;
    otro.hidden = !o.otro; otro.textContent = o.otro || ''; otro.onclick = () => fin('otro');
    $('#cfTit').textContent = o.titulo; $('#cfTxt').innerHTML = o.html || '';
    si.textContent = o.boton || 'Aceptar'; si.className = o.clase || 'peligro';
    d.setAttribute('role', conCampo ? 'dialog' : 'alertdialog');
    $('#cfCampo').hidden = !conCampo; aviso.hidden = !conCampo; aviso.textContent = o.nota || ''; aviso.className = '';
    if(conCampo){ $('#cfEtiq').textContent = o.etiqueta || ''; inp.value = o.valor || ''; inp.placeholder = o.placeholder || ''; inp.removeAttribute('aria-invalid'); }
    const revisar = () => {
      const t = inp.value.trim(), m = !t && !o.vacio ? (o.faltaTxt || 'Escribí un nombre.') : o.validar ? o.validar(t) : '';
      return m;
    };
    const fin = v => { d.classList.remove('abierto'); document.removeEventListener('keydown', tecla, true); inp.oninput = null;
      try { previo && previo.focus && previo.focus({preventScroll:true}); } catch(e){} res(v); };
    const aceptar = () => {
      if(!conCampo) return fin(true);
      const m = revisar();
      if(m){ aviso.textContent = m; aviso.className = 'mal'; inp.setAttribute('aria-invalid', 'true'); inp.focus(); return; }
      fin(inp.value.trim());
    };
    const tecla = e => {
      e.stopPropagation();                         // que no actúen los atajos del informe (F2, F4...)
      if(e.key==='Escape'){ e.preventDefault(); fin(conCampo ? null : false); }
      else if(e.key==='Enter' && document.activeElement===inp){ e.preventDefault(); aceptar(); }
      else if(e.key==='Tab'){
        e.preventDefault();
        const orden = (conCampo ? [inp, no, otro, si] : [no, otro, si]).filter(x => !x.hidden), i = orden.indexOf(document.activeElement);
        orden[(i + (e.shiftKey ? orden.length - 1 : 1)) % orden.length].focus();
      }
    };
    if(conCampo) inp.oninput = () => {
      if(inp.getAttribute('aria-invalid')){ inp.removeAttribute('aria-invalid'); aviso.className = ''; }
      aviso.textContent = o.alEscribir ? o.alEscribir(inp.value.trim()) : (o.nota || '');
    };
    no.onclick = () => fin(conCampo ? null : false); si.onclick = aceptar;
    d.onmousedown = e => { if(e.target===d) fin(conCampo ? null : false); };
    document.addEventListener('keydown', tecla, true);
    d.classList.add('abierto');
    if(conCampo){ inp.focus(); inp.select(); }
    else (o.clase === 'prim' ? si : no).focus();   // al borrar, por seguridad, el foco queda en Cancelar
  });
}
function confirmar(titulo, html, boton, clase){ return modal({titulo, html, boton: boton || 'Borrar', clase: clase || 'peligro'}); }
/* ¿El cambio es solo para mí o para todos? → 'mio' · 'todos' · null (cancelar). Sin usuario: 'todos' sin preguntar. */
async function elegirDestino(que){
  if(!MI.usuario) return 'todos';
  const r = await modal({titulo: `¿Guardar ${que} solo para vos o para todos?`, clase: 'prim', boton: 'Solo para mí', otro: 'Para todos',
    html: `<p><b>Solo para mí:</b> la IA lo usa únicamente en tus informes; los demás siguen con lo general.</p><p><b>Para todos:</b> cambia lo general, que usan todos los que no tienen su propia versión.</p>`});
  return r === true ? 'mio' : r === 'otro' ? 'todos' : null;
}
function pedirTexto(o){ return modal({...o, campo: true, clase: 'prim'}); }
async function dejarCasoAbierto(){                 // cierra el caso abierto sin aviso (para poder borrarlo)
  const n = actual; if(!n) return;
  audio.pause(); await guardarBorrador();
  actual = null; activa = null; ocultarExplica(); onda = null;
  audio.removeAttribute('src'); audio.load();      // suelta el audio para que se pueda borrar
  mostrar('vacio'); document.querySelectorAll('#casos li').forEach(li => li.classList.remove('sel'));
  { const rv = tomarRev(); try { await api('/api/caso/soltar', {nombre: n, rev: rv}); } catch(e){ revPend += rv; soltarCaso(n); } }
}
async function borrarCasos(cs){
  cs = cs.filter(Boolean); if(!cs.length) return;
  const uno = cs.length === 1, c = cs[0], nom = x => esc(x.paciente || x.titulo || x.nombre);
  const pend = cs.filter(x => x.estado !== 'revisado');
  let html = uno
    ? `<p>Se borran el audio, el informe y el Word de <b>${nom(c)}</b>${c.estudios ? ' (' + esc(c.estudios) + ')' : ''}.</p>`
    : `<p>Se borran el audio, el informe y el Word de estos <b>${cs.length} informes</b> ya revisados:</p><ul>${cs.map(x => '<li>' + nom(x) + (x.estudios ? ' · ' + esc(x.estudios) : '') + '</li>').join('')}</ul>`;
  if(pend.length) html += uno
    ? `<p class="cf-pend"><b>${c.estado==='listo' ? 'Este informe todavía no se guardó.' : c.estado==='error' ? 'Este audio no se pudo procesar.' : 'Este audio todavía no tiene informe.'}</b> Si lo borrás, se pierde${c.estado==='listo' ? ' lo que corregiste' : ''} y no se va a poder recuperar.</p>`
    : `<p class="cf-pend"><b>${pend.length === 1 ? '1 todavía no se guardó' : pend.length + ' todavía no se guardaron'}.</b> Si los borrás, se pierden.</p>`;
  html += '<p>Lo que la IA aprendió de tus correcciones se conserva. <b>No se puede deshacer.</b></p>';
  if(!await confirmar(uno ? 'Borrar «' + (c.paciente || c.titulo || c.nombre) + '»' : `Borrar ${cs.length} informes revisados`,
                      html, uno ? 'Borrar' : `Borrar ${cs.length}`)) return;
  if(cs.some(x => x.nombre === actual)) { try { await dejarCasoAbierto(); } catch(e){ toast(e.message); return; } }
  let r;
  try { r = await api('/api/borrar', {nombres: cs.map(x => x.nombre)}); }
  catch(e){ toast(e.message, [], 8000); cargarLista(); return; }
  const ok = r.borrados.length, mal = r.fallidos || [];
  const hecho = ok === 1 ? (uno ? 'Informe borrado.' : 'Se borró 1 informe.') : `Se borraron ${ok} informes.`;
  if(mal.length) toast((ok ? hecho + ' ' : '') + (mal.length === 1 ? mal[0].error : `${mal.length} no se pudieron borrar: ${mal[0].error}`), [], 9000);
  else toast(hecho);
  cargarLista();
}
$('#bBorrarCaso').onclick = () => { const c = casosCache.find(x => x.nombre === actual); if(c) borrarCasos([c]); };

