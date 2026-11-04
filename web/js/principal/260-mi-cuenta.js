// Mi cuenta: contraseña, formato del Word y reglas propias.
/* ------------------------------------------------ Mi cuenta (contraseña, formato del Word, reglas propias) */
const SINO = v => v === true ? 'si' : v === false ? 'no' : '';
const DE_SINO = v => v === 'si' ? true : v === 'no' ? false : null;
async function cargarCuenta(){
  if(!MI.usuario) return;
  let e; try { e = await api('/api/usuario/estilo'); } catch(err){ return; }
  const g = e.general || {}, f = e.formato || {};
  const opciones = (sel, valores, actual, gen, fmt) => {
    sel.innerHTML = `<option value="">General (${esc(fmt(gen))})</option>` + valores.map(v => `<option value="${esc(String(v))}">${esc(fmt(v))}</option>`).join('');
    sel.value = actual == null ? '' : String(actual);
  };
  opciones($('#mfFuente'), e.fuentes, f.fuente, g.fuente, v => v);
  opciones($('#mfTamano'), [9, 10, 11, 12, 13, 14, 16], f.tamano_fuente, g.tamano_fuente, v => v + ' pt');
  opciones($('#mfRenglones'), [0, 1, 2, 3, 4, 5, 6, 7, 8, 10, 12], f.lineas_vacias_para_encabezado, g.lineas_vacias_para_encabezado, v => String(v));
  $('#mfCentrar').value = SINO(f.centrar_titulos); $('#mfNegrita').value = SINO(f.negrita_titulos); $('#mfLinea').value = SINO(f.linea_vacia_entre_titulo_y_texto);
  MIS_REGLAS = reglasDeTexto(e.reglas || ''); pintarReglas();
  const p = e.plantillas_propias.length, m = e.medicos_propios.length;
  $('#cuentaEstilo').textContent = (p ? `Plantillas propias: ${e.plantillas_propias.join(', ')}. ` : 'Usás las plantillas generales. ')
    + (m ? `Notas propias de: ${e.medicos_propios.join(', ')}.` : 'Usás las notas generales de los médicos.')
    + ' Lo que corregís se aprende para tus próximos informes.';
}
const abrirConfigOriginal = abrirConfig;
abrirConfig = function(tab, pedirEstado = true){ abrirConfigOriginal(tab, pedirEstado); if(MI.usuario) cargarCuenta(); };
$('#bMiCuenta').onclick = () => abrirConfig('cuenta');
$('#fMiClave').onsubmit = async ev => {
  ev.preventDefault();
  const a = $('#mcActual').value, n = $('#mcNueva').value, n2 = $('#mcNueva2').value, msj = $('#mcMsj');
  msj.className = 'cfg-msj mal';
  if(n.length < 6){ msj.textContent = 'La nueva tiene que tener al menos 6 caracteres.'; $('#mcNueva').focus(); return; }
  if(n !== n2){ msj.textContent = 'Las dos no coinciden.'; $('#mcNueva2').focus(); return; }
  try { await api('/api/usuario/contrasena', {actual: a, nueva: n}); }
  catch(e){ msj.textContent = e.message; return; }
  msj.className = 'cfg-msj'; msj.textContent = '✓ Contraseña cambiada.';
  ['#mcActual', '#mcNueva', '#mcNueva2'].forEach(x => $(x).value = '');
  if(MI.usuario) MI.usuario.cambiar = false;
  pintarConfig();
};
$('#fMiFormato').onsubmit = async ev => {
  ev.preventDefault();
  const num = v => v === '' ? null : +v;
  const formato = {fuente: $('#mfFuente').value || null, tamano_fuente: num($('#mfTamano').value),
    lineas_vacias_para_encabezado: num($('#mfRenglones').value), centrar_titulos: DE_SINO($('#mfCentrar').value),
    negrita_titulos: DE_SINO($('#mfNegrita').value), linea_vacia_entre_titulo_y_texto: DE_SINO($('#mfLinea').value)};
  const msj = $('#mfMsj');
  try { await api('/api/usuario/formato', {formato}); msj.className = 'cfg-msj'; msj.textContent = '✓ Guardado: se usa en los próximos Word que guardes.'; }
  catch(e){ msj.className = 'cfg-msj mal'; msj.textContent = e.message; }
};
/* reglas propias: se guardan como renglones «- regla» en su reglas_dictado.md */
let MIS_REGLAS = [];
const reglasDeTexto = t => t.split(/\r?\n/).map(l => l.replace(/^\s*[-•*]\s*/, '').trim()).filter(l => l && !l.startsWith('#'));
function pintarReglas(){
  const ul = $('#mrLista');
  ul.innerHTML = MIS_REGLAS.length ? '' : '<li class="vacio"><span>Todavía no agregaste reglas propias.</span></li>';
  MIS_REGLAS.forEach((r, i) => {
    const li = document.createElement('li'), t = document.createElement('span');
    t.textContent = r; li.appendChild(t);
    const ed = document.createElement('button'); ed.type = 'button'; ed.className = 'chico'; ed.textContent = 'Editar';
    ed.onclick = () => abrirReglas(i);
    const qu = document.createElement('button'); qu.type = 'button'; qu.className = 'chico'; qu.textContent = 'Quitar';
    qu.onclick = async () => {
      if(!await confirmar('¿Quitar esta regla?', '<p>' + esc(r) + '</p>', 'Quitar')) return;
      const antes = MIS_REGLAS.slice(); MIS_REGLAS.splice(i, 1);
      if(!await guardarReglas('Regla quitada.')){ MIS_REGLAS = antes; } pintarReglas();
    };
    li.append(ed, qu); ul.appendChild(li);
  });
}
async function guardarReglas(ok){
  const msj = $('#mrMsj');
  try { await api('/api/usuario/reglas', {reglas: MIS_REGLAS.map(r => '- ' + r).join('\n')});
        msj.className = 'cfg-msj'; msj.textContent = '✓ ' + ok + ' La IA las usa desde tu próximo informe.'; return true; }
  catch(e){ msj.className = 'cfg-msj mal'; msj.textContent = 'No se guardó: ' + e.message; return false; }
}
let reglaEditada = null, reglasPrevio = null;
function filaRegla(valor){
  const f = document.createElement('div'); f.className = 'rd-fila';
  const inp = document.createElement('input'); inp.type = 'text'; inp.maxLength = 400; inp.value = valor || '';
  inp.placeholder = 'Ej.: Escribir «Bi-Rads 2.» sin dos puntos'; inp.setAttribute('aria-label', 'Regla'); inp.spellcheck = true; inp.lang = 'es';
  inp.addEventListener('keydown', e => { if(e.key === 'Enter'){ e.preventDefault(); if(reglaEditada === null){ const n = filaRegla(''); f.after(n); n.firstChild.focus(); } else $('#rdSi').click(); } });
  const x = document.createElement('button'); x.type = 'button'; x.className = 'chico'; x.textContent = '✕'; x.title = 'Quitar este renglón'; x.setAttribute('aria-label', 'Quitar este renglón');
  x.onclick = () => { if($('#rdFilas').children.length > 1) f.remove(); else inp.value = ''; ($('#rdFilas').querySelector('input') || inp).focus(); };
  f.append(inp, x); return f;
}
function abrirReglas(i){       // i: índice de la regla a editar; sin i, añadir varias
  reglaEditada = i == null ? null : i; reglasPrevio = document.activeElement;
  $('#rdTit').textContent = reglaEditada === null ? 'Añadir reglas' : 'Editar regla';
  $('#rdOtra').hidden = reglaEditada !== null;
  const filas = $('#rdFilas'); filas.innerHTML = '';
  filas.appendChild(filaRegla(reglaEditada === null ? '' : MIS_REGLAS[reglaEditada]));
  $('#reglasDlg').hidden = false; filas.querySelector('input').focus();
}
function cerrarReglas(){ $('#reglasDlg').hidden = true; try { reglasPrevio && reglasPrevio.focus(); } catch(e){} }
$('#bAnadirRegla').onclick = () => abrirReglas();
$('#rdOtra').onclick = () => { const n = filaRegla(''); $('#rdFilas').appendChild(n); n.firstChild.focus(); };
$('#rdNo').onclick = cerrarReglas;
$('#reglasDlg').addEventListener('mousedown', e => { if(e.target === $('#reglasDlg')) cerrarReglas(); });
$('#reglasDlg').addEventListener('keydown', e => {
  e.stopPropagation();
  if(e.key === 'Escape'){ e.preventDefault(); cerrarReglas(); }
});
$('#rdSi').onclick = async () => {
  const nuevas = [...$('#rdFilas').querySelectorAll('input')].map(x => x.value.replace(/\s+/g, ' ').trim()).filter(Boolean);
  const antes = MIS_REGLAS.slice();
  if(reglaEditada === null){
    if(!nuevas.length){ $('#rdFilas').querySelector('input').focus(); return; }
    MIS_REGLAS.push(...nuevas.filter(r => !MIS_REGLAS.includes(r)));
  } else if(nuevas.length) MIS_REGLAS[reglaEditada] = nuevas[0];
  else MIS_REGLAS.splice(reglaEditada, 1);
  $('#rdSi').disabled = true;
  const ok = await guardarReglas(reglaEditada === null ? (nuevas.length === 1 ? 'Regla agregada.' : nuevas.length + ' reglas agregadas.') : 'Regla guardada.');
  $('#rdSi').disabled = false;
  if(!ok){ MIS_REGLAS = antes; return; }
  pintarReglas(); cerrarReglas();
};

aplicarTema();
