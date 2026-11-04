// Estado del servidor y de la IA; cartel del panel de administración.
/* ------------------------------------------------ estado del servidor y de la IA */
let SRV = {ok: null, desde: Date.now(), ultimoOk: 0, ia: 'ok', modelo: ''}, abriendo = null;
const EN_PROC = ['en cola','transcribiendo','en pausa','generando'];
function minutos(s){ if(s == null) return ''; if(s < 45) return 'menos de 1 min'; const m = Math.round(s/60); return m < 60 ? `~${m} min` : `~${Math.floor(m/60)} h ${m%60} min`; }
function haceCuanto(ms){ const s = Math.round(ms/1000); return s < 60 ? `${s} s` : s < 3600 ? `${Math.round(s/60)} min` : `${Math.floor(s/3600)} h`; }
const esperaIA = c => c.estado==='en cola' && (c.msg||'').startsWith('Esperando a la IA') && SRV.ia !== 'ok';
function textoEspera(c){        // "Transcribiendo… · listo en ~2 min" / "En cola · 1 audio antes · listo en ~3 min"
  if(esperaIA(c)) return 'Transcrito · espera a que la IA esté lista';
  if(c.estado==='en pausa') return (c.msg || 'En pausa') + (MI.remoto ? ' · la pausaron en la PC del servidor' : ' · sigue cuando la reanudes');
  const e = c.espera, partes = [c.msg ? c.msg.replace(/…$/, '') : ETIQ[c.estado]];
  if(e && e.adelante && c.estado==='en cola') partes.push(e.adelante + (e.adelante===1 ? ' audio antes' : ' audios antes'));
  if(e && SRV.ia === 'ok') partes.push(SRV.pausa ? 'espera: hay una transcripción en pausa' : 'listo en ' + minutos(e.eta));
  return partes.join(' · ');
}
function ponerEstadoSrv(){
  const box = $('#estadoSrv'), p = $('#pOllama'), t = $('#tOllama');
  let h = '', clase = '';
  if(SRV.ok === false && SRV.reinicio){
    p.className = 'punto av'; t.textContent = 'reiniciando'; clase = 'av';
    h = '<b>El servidor se está reiniciando</b>Lo pidió el administrador. En unos segundos vuelve y esta pantalla se reconecta sola; no hace falta hacer nada.'
      + `<small>Reintentando cada 2 s · hace ${haceCuanto(Date.now() - SRV.reinicio)}</small>`;
  } else if(SRV.ok === false){
    p.className = 'punto mal'; t.textContent = 'sin conexión';
    h = '<b>Sin conexión con el servidor</b>' + (MI.remoto
        ? 'La PC del servidor puede estar apagada, sin internet o con su ventana cerrada.' + (EN_APP && APP ? ' Podés seguir grabando y cargando audios: quedan guardados en esta PC y se envían solos cuando vuelva.'
            : EN_APP ? ' Los audios que grabes quedan guardados en esta PC y se envían solos cuando vuelva.'
            : ' Podés cargar audios igual: esperan en esta página y se envían solos cuando vuelva.')
        : deSistema('¿Se cerró la ventana del servidor? Abrí <code>iniciar_servidor.bat</code> (o <code>interfaz.bat</code>) y esta página se reconecta sola.'))
      + `<small>Reintentando cada 2 s · ${SRV.ultimoOk ? 'última conexión hace ' + haceCuanto(Date.now() - SRV.ultimoOk) : 'todavía no se pudo conectar'}</small>`;
  } else if(SRV.ia === 'caida'){
    p.className = 'punto av'; t.textContent = 'IA no lista'; clase = 'av';
    h = '<b>La IA no está lista: Ollama está cerrado</b>' + (MI.remoto
        ? 'Hay que abrir Ollama en la PC del servidor. Mientras tanto los audios llegan, se transcriben y esperan en la cola: se terminan solos cuando se abra.'
        : deSistema('Abrí Ollama (el ícono de la llama) y esperá unos segundos. Mientras tanto los audios se transcriben y esperan en la cola: se terminan solos.'));
  } else if(SRV.ia === 'sin_modelo'){
    p.className = 'punto av'; t.textContent = 'IA sin modelo'; clase = 'av';
    h = `<b>A Ollama le falta el modelo ${esc(SRV.modelo || '')}</b>` + (MI.remoto ? 'Hay que instalarlo en la PC del servidor.' : 'Instalalo abriendo una consola y escribiendo')
      + (MI.remoto ? '' : ` <code>ollama pull ${esc(SRV.modelo || '')}</code>.`) + ' Los audios esperan en la cola mientras tanto.';
  } else { p.className = 'punto'; t.textContent = 'IA lista'; }
  $('#rielPunto').className = p.className; $('#rielIa').title = t.textContent === 'IA' ? '' : t.textContent;   // riel de la lista oculta
  box.className = 'estado-srv' + (clase ? ' ' + clase : '');
  if(box.innerHTML !== h) box.innerHTML = h;
  box.hidden = !h;
}

let consultaLista = null;
function cargarLista(){
  if(consultaLista) return consultaLista;
  consultaLista = cargarListaActual().finally(()=>{consultaLista=null;});
  return consultaLista;
}
async function cargarListaActual(){
  let j; try { j = await api('/api/casos'); }
  catch(e){ if(SRV.ok !== false){ SRV.ok = false; SRV.desde = Date.now();
      // se cortó justo cuando el administrador reiniciaba el servidor: no es una falla
      const r = MSJ && MSJ.reinicio; if(r && (r.estado !== 'programado' || r.cuando - ahoraSrvPC() < 10)) SRV.reinicio = Date.now(); }
    if(SRV.reinicio && Date.now() - SRV.reinicio > 180000) SRV.reinicio = 0;
    $('#msjAdmin').hidden = true; ponerEstadoSrv(); armarVacio(null); return; }
  if(SRV.reinicio) toast('El servidor ya se reinició: todo sigue normal.', [], 6000);
  SRV = {...SRV, ok: true, ultimoOk: Date.now(), ia: j.ia_estado || (j.ollama ? 'ok' : 'caida'), modelo: j.modelo || '', reinicio: 0, pausa: !!j.pausa};
  ponerMensaje(j.mensaje || null);
  ponerEstadoSrv();
  if(enEspera.length) enviarEnEspera();
  casosCache = j.casos;
  const mios = j.casos.filter(c => c.origen === MI.pc);
  $('#tabMia').textContent = 'Esta PC · ' + mios.length; $('#tabTodas').textContent = 'Todas · ' + j.casos.length;
  const lista = filtro === 'mia' ? mios : j.casos;
  armarVacio(lista, j.casos);
  actualizarRiel(lista);
  const rev = lista.filter(c => c.estado==='revisado' && c.puede_borrar && !c.bloqueado_por);
  $('#limpiar').hidden = !rev.length;
  if(rev.length){ const bl = $('#bLimpiar');
    bl.innerHTML = TACHO + (MI.remoto ? 'Borrar revisados de esta PC · ' : 'Borrar revisados · ') + rev.length;
    bl.title = 'Borra los informes ya guardados' + (MI.remoto ? ' que llegaron desde esta PC' : '') + ' (audio, informe y Word). Lo que aprendió la IA se conserva.';
    bl.onclick = () => borrarCasos(rev); }
  const ul = $('#casos'); ul.innerHTML = '';
  if(!lista.length){
    ul.innerHTML = '<li class="vacia">' + (filtro==='mia'
      ? '<b>Todavía no llegaron audios de esta PC.</b>' + (MI.remoto ? 'Los que grabes aparecen acá solos.' : 'Arrastrá audios arriba para empezar.')
        + (j.casos.length ? ` Hay ${j.casos.length} en <a href="#" id="verTodas">Todas</a>.` : '')
      : '<b>Todavía no hay audios.</b>' + (MI.remoto ? 'Los que se graben aparecen acá solos.' : 'Arrastrá audios arriba para empezar.')) + '</li>';
    const v = $('#verTodas'); if(v) v.onclick = e => { e.preventDefault(); ponerFiltro('todas'); };
  }
  for(const c of lista){
    const li = document.createElement('li'); li.dataset.n = c.nombre;
    if(c.nombre === actual) li.classList.add('sel');
    const trab = EN_PROC.includes(c.estado);
    const cls = c.estado==='en pausa' ? 'pausa' : trab ? 'trabajando' : c.estado;
    let det = trab ? textoEspera(c) : (c.msg || '');
    if(c.estado==='error'){ const m = c.msg || 'error desconocido'; det = 'No se pudo procesar: ' + (m.length > 110 ? m.slice(0, 107) + '…' : m); }
    if(c.estado==='listo' && c.marcas!=null){
      const a = c.avisos, n = a ? a.rojo + a.amarillo + a.turq + a.gris + a.faltan.length + a.huecos.length : c.marcas;
      det = n ? n + (n===1?' marca':' marcas') + ' para revisar' : 'Sin marcas pendientes'; }
    if(c.estado==='nuevo') det = 'Sin procesar';
    const vz = c.voz, vzMed = c.medico ? (vz && vz.por==='voz' ? '🎙 ' : '') + c.medico
      : vz && c.estado==='listo' ? (vz.estado==='dudoso' && vz.medico ? '¿' + vz.medico + '?' : 'médico sin reconocer') : '';
    if(vzMed) det = (det ? det + ' · ' : '') + vzMed;
    if(filtro !== 'mia' && c.origen !== MI.pc) det = c.origen + (det ? ' · ' + det : '');
    if(c.bloqueado_por){ det = 'Lo está revisando ' + c.bloqueado_por; li.classList.add('bloq'); }
    if(c.titulo && c.titulo !== c.nombre){ const d = new Date(c.fecha*1000);
      det = String(d.getHours()).padStart(2,'0') + ':' + String(d.getMinutes()).padStart(2,'0') + (det ? ' · ' + det : ''); }
    const etiq = c.nombre === abriendo ? 'abriendo' : esperaIA(c) ? 'esperando IA' : (ETIQ[c.estado]||c.estado);
    if(c.nombre === abriendo) li.classList.add('abriendo');
    const audio = c.titulo || c.nombre;
    li.innerHTML = `<span class="n" title="${esc(c.paciente ? c.paciente + ' · audio ' + audio : 'Audio ' + audio + (c.estado==='nuevo' || trab ? '' : ' · no se encontró el nombre del paciente en el dictado'))}">${c.paciente ? esc(c.paciente) : '<span class="sinnom">' + esc(audio) + '</span>'}</span><span class="der">${c.puede_borrar && !c.bloqueado_por && c.nombre!==abriendo ? `<button type="button" class="borrar" title="Borrar este informe" aria-label="Borrar este informe">${TACHO}</button>` : ''}<span class="badge ${cls}">${trab && !esperaIA(c) && c.estado!=='en pausa' || c.nombre===abriendo ?'<span class="spin"></span>':''}${etiq}</span></span>${lineaEstudio(c)}<span class="e">${esc(det)}</span>` + htmlAvisos(c);
    if(c.estado==='nuevo' || c.estado==='error'){
      const b=document.createElement('button'); b.className='chico'; b.textContent= c.estado==='error'?'Reintentar':'Procesar';
      b.style.gridColumn='1/-1'; b.style.justifySelf='start';
      b.onclick = async ev => { ev.stopPropagation(); await api('/api/procesar',{nombre:c.nombre}); cargarLista(); };
      li.appendChild(b);
    }
    const bp = botonPausa(c);
    if(bp){ bp.style.gridColumn='1/-1'; bp.style.justifySelf='start'; li.appendChild(bp); }
    const bb = li.querySelector('.borrar');
    if(bb) bb.onclick = ev => { ev.stopPropagation(); borrarCasos([c]); };
    li.onclick = () => {
      if(c.bloqueado_por){ toast('Este caso lo está revisando ' + c.bloqueado_por + '.'); return; }
      if(!['listo','revisado'].includes(c.estado)) return;
      if(esCompacto()) agrandar();          // en modo compacto, un clic agranda la ventana y abre el caso
      abrirCaso(c.nombre); };
    ul.appendChild(li);
  }
}
/* ------------------------------------------------ cartel del panel de administración */
let MSJ = null, desfaseSrv = 0;
const ahoraSrvPC = () => Date.now() / 1000 + desfaseSrv;
const ICO_MSJ = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9.5"/><path d="M12 7.5v5.5M12 16.5v.5"/></svg>';
function msjCerrado(){ try { return localStorage.getItem('msjCerrado') || ''; } catch(e){ return ''; } }
function textoCuenta(cuando){
  const s = Math.round(cuando - ahoraSrvPC());
  return s > 0 ? `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}` : null;
}
function ponerMensaje(m){
  MSJ = m; const box = $('#msjAdmin');
  if(m) desfaseSrv = m.ahora - Date.now() / 1000;
  if(!m || m.id === msjCerrado()){ box.hidden = true; box.dataset.h = ''; return; }
  const r = m.reinicio;
  let cuando = '';
  if(r) cuando = r.estado === 'reiniciando' ? 'Reiniciando ahora…'
               : r.estado === 'esperando' ? 'En cuanto termine el audio que se está procesando.'
               : textoCuenta(r.cuando) ? `En <b data-cuenta="${r.cuando}">${textoCuenta(r.cuando)}</b>` : 'En un instante…';
  const h = `<span class="msj-ico">${ICO_MSJ}</span><div class="msj-txt"><b>${r ? 'El sistema se va a reiniciar' : 'Mensaje del administrador'}</b>`
    + (cuando ? `<span class="msj-cuando">${cuando}</span>` : '') + `<span>${esc(m.texto)}</span></div><button type="button" class="chico" id="bMsjOk">Entendido</button>`;
  box.className = 'msj-admin' + (m.tipo === 'aviso' || r ? ' aviso' : '');
  if(box.dataset.h !== h){
    box.dataset.h = h; box.innerHTML = h;
    $('#bMsjOk').onclick = () => { try { localStorage.setItem('msjCerrado', m.id); } catch(e){} box.hidden = true; };
  }
  box.hidden = false;
}
setInterval(() => document.querySelectorAll('#msjAdmin [data-cuenta]').forEach(el => {
  const t = textoCuenta(+el.dataset.cuenta); if(t) el.textContent = t; else el.parentNode.textContent = 'En un instante…';
}), 1000);

