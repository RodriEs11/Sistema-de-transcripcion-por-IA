// Pantalla principal cuando no hay un caso abierto; arranque de la lista.
/* ------------------------------------------------ pantalla principal cuando no hay un caso abierto */
const ICO = {
  audio: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3"/></svg>',
  doc:   '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5M9 13h6M9 17h4"/></svg>',
  reloj: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>',
  ok:    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>',
  alerta:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3l9.5 17h-19z"/><path d="M12 10v4M12 17.5v.5"/></svg>',
  /* sin conexión: la señal wifi entera (tres arcos concéntricos y el punto, sin cortes) y una insignia con una
     cruz abajo a la derecha. La cruz va del color del fondo del ícono (clase "recorte"). */
  corte: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M2.01 7.51a12 12 0 0 1 16.98 0M4.84 10.34a8 8 0 0 1 11.32 0M7.67 13.17a4 4 0 0 1 5.66 0"/><circle cx="10.5" cy="16.4" r="1.4" fill="currentColor" stroke="none"/><circle cx="18.6" cy="18.6" r="4.6" fill="currentColor" stroke="none"/><path class="recorte" d="M16.9 16.9l3.4 3.4M20.3 16.9l-3.4 3.4" stroke-width="1.8"/></svg>'};
const hhmm = t => { const d = new Date(t*1000); return String(d.getHours()).padStart(2,'0') + ':' + String(d.getMinutes()).padStart(2,'0'); };
const nombreDe = c => '«' + esc(c.paciente || c.titulo || c.nombre) + '»';
function etapas(c){           // Transcribir -> Armar el informe -> Para revisar, con la etapa actual resaltada
  const paso = c.estado==='generando' || (c.estado==='en cola' && (c.msg||'').startsWith('Esperando a la IA')) ? 1
             : c.estado==='transcribiendo' || c.estado==='en pausa' ? 0 : -1;
  const est = i => i < paso ? 'hecho' : i === paso ? (esperaIA(c) || c.estado==='en pausa' ? 'espera' : 'ahora') : '';
  const txt = [c.estado==='en pausa' ? 'Transcripción en pausa' : 'Transcribir el audio', 'Armar el informe', 'Para revisar'];
  return '<div class="etapas">' + txt.map((t, i) => `<span class="${est(i)}">${est(i)==='ahora' ? '<span class="spin"></span>' : est(i)==='hecho' ? '✓ ' : ''}${t}</span>`).join('<i></i>') + '</div>';
}
let vacioHtml = '';
function armarVacio(lista, todos){
  const box = $('#vacio');
  if(box.hidden) return;
  let h;
  const card = (ico, clase, cuerpo) => `<div class="vac-card"><div class="vac-ico ${clase}">${ICO[ico]}</div>${cuerpo}</div>`;
  if(abriendo){
    const c = casosCache.find(x => x.nombre === abriendo) || {nombre: abriendo};
    h = `<div class="vac-card"><span class="spin"></span> Abriendo ${nombreDe(c)}…</div>`;
  } else if(lista === null){
    h = card('corte', 'err', '<h2>Sin conexión con el servidor</h2><p>' + (MI.remoto
        ? 'La PC del servidor puede estar apagada, sin internet o con su ventana cerrada. Cuando vuelva, esta pantalla se actualiza sola.'
        : deSistema('La ventana del servidor parece cerrada. Abrí <b>iniciar_servidor.bat</b> (o <b>interfaz.bat</b>) y esta página se reconecta sola.'))
      + '</p><p class="vac-nota"><span class="spin"></span> Reintentando cada 2 segundos…</p>');
  } else {
    const listos = lista.filter(c => c.estado==='listo' && !c.bloqueado_por).sort((a, b) => b.fecha - a.fecha);   // el más nuevo primero
    const enProc = lista.filter(c => EN_PROC.includes(c.estado)).sort((a, b) => ((a.espera||{}).eta ?? 1e9) - ((b.espera||{}).eta ?? 1e9));
    const errores = lista.filter(c => c.estado==='error'), nuevos = lista.filter(c => c.estado==='nuevo');
    const prox = enProc[0], proxTxt = prox ? (prox.estado==='en pausa' ? 'cuando se reanude la transcripción (está en pausa)' : esperaIA(prox) ? 'cuando la IA esté lista'
      : SRV.pausa ? 'cuando se reanude la transcripción en pausa' : (prox.espera ? 'en ' + minutos(prox.espera.eta) : 'en unos minutos')) : '';
    const extra = [];
    if(enProc.length) extra.push(`${enProc.length} ${enProc.length===1 ? 'audio en proceso' : 'audios en proceso'}: el próximo estará listo ${proxTxt}.`);
    if(errores.length) extra.push(`${errores.length} con error (botón <b>Reintentar</b> en la lista).`);
    if(nuevos.length) extra.push(`${nuevos.length} ${nuevos.length===1 ? 'audio sin procesar' : 'audios sin procesar'} (botón <b>Procesar</b> en la lista).`);
    const otros = todos ? todos.length - lista.length : 0;
    if(!lista.length){
      const pasos = MI.remoto
        ? ['Grabá el audio como siempre: la aplicación lo envía sola al servidor.', 'El servidor lo transcribe y la IA arma el informe (unos minutos).', 'Cuando en la lista diga <b>para revisar</b>, hacé clic y revisalo mientras lo escuchás.']
        : ['Arrastrá uno o varios audios a la lista de la izquierda (o tocá <b>Elegir audios</b>).', 'Se transcriben y la IA arma el informe sola (unos minutos por audio).', 'Cuando diga <b>para revisar</b>, hacé clic y revisalo mientras lo escuchás.'];
      h = card('audio', '', `<h2>${filtro==='mia' && MI.remoto ? 'Todavía no llegaron audios de esta PC' : 'Todavía no hay audios'}</h2>`
        + '<ol class="vac-pasos">' + pasos.map(p => `<li><span>${p}</span></li>`).join('') + '</ol>'
        + '<div class="vac-bot">' + (MI.remoto ? '' : '<button class="prim" data-acc="elegir">Elegir audios…</button>')
        + (otros > 0 ? `<button data-acc="todas">Ver los de todas las PC (${otros})</button>` : '') + '</div>');
    } else if(listos.length){
      const c = listos[0], a = c.avisos, n = a ? a.rojo + a.amarillo + a.turq + a.gris + a.faltan.length + a.huecos.length : (c.marcas || 0);
      h = card('doc', '', `<h2>${listos.length===1 ? 'Hay 1 informe para revisar' : `Hay ${listos.length} informes para revisar`}</h2>`
        + `<p>${listos.length > 1 ? 'El más reciente' : 'Es'}: <span class="vac-titulo">${nombreDe(c)}</span> · ${hhmm(c.fecha)}${c.medico ? ' · ' + esc(c.medico) : ''} · ${n ? n + (n===1 ? ' marca' : ' marcas') + ' para revisar' : 'sin marcas'}.</p>`
        + `<div class="vac-bot"><button class="prim" data-acc="abrir" data-n="${esc(c.nombre)}">Abrir ${nombreDe(c)}</button></div>`
        + (extra.length ? `<p class="vac-nota">${extra.join(' ')}</p>` : ''));
    } else if(enProc.length){
      const bp = botonPausa(prox);
      h = card('reloj', '', `<h2>${enProc.length===1 ? 'Procesando 1 audio' : `Procesando ${enProc.length} audios`}</h2>`
        + `<p><span class="vac-titulo">${nombreDe(prox)}</span> estará listo ${proxTxt}.</p>` + etapas(prox)
        + (bp ? `<div class="vac-bot"><button class="bpausa" data-acc="${prox.puede_reanudar ? 'reanudar' : 'pausar'}" data-n="${esc(prox.nombre)}" title="${esc(bp.title)}">${bp.innerHTML}</button></div>` : '')
        + `<p class="vac-nota">No hace falta esperar en esta pantalla: cuando termine aparece en la lista como <b>para revisar</b>.`
        + (errores.length ? ` ${errores.length} con error (botón <b>Reintentar</b> en la lista).` : '') + '</p>');
    } else if(errores.length){
      const c = errores[0];
      h = card('alerta', 'err', `<h2>${errores.length===1 ? 'Un audio no se pudo procesar' : `${errores.length} audios no se pudieron procesar`}</h2>`
        + `<p>${nombreDe(c)}: ${esc(c.msg || 'error desconocido')}</p>`
        + `<div class="vac-bot"><button class="prim" data-acc="reintentar">${errores.length===1 ? 'Reintentar' : 'Reintentar todos'}</button></div>`
        + '<p class="vac-nota">El detalle del error queda en la ventana del servidor y en la carpeta registros.</p>');
    } else if(nuevos.length){
      h = card('audio', '', `<h2>${nuevos.length===1 ? 'Hay 1 audio sin procesar' : `Hay ${nuevos.length} audios sin procesar`}</h2>`
        + '<p>Estos audios están en la carpeta de audios nuevos pero todavía no se mandaron a procesar.</p>'
        + `<div class="vac-bot"><button class="prim" data-acc="procesar">${nuevos.length===1 ? 'Procesar' : 'Procesar todos'}</button></div>`);
    } else {
      const bloq = lista.filter(c => c.bloqueado_por);
      h = card('ok', 'ok', '<h2>Todo revisado</h2><p>No quedan informes pendientes' + (filtro==='mia' && otros > 0 ? ' de esta PC' : '') + '. '
        + (MI.remoto ? 'Los audios nuevos que grabes aparecen en la lista solos.' : 'Arrastrá audios nuevos a la lista cuando quieras.') + '</p>'
        + (bloq.length ? `<p class="vac-nota">${bloq.length} ${bloq.length===1 ? 'caso lo está' : 'casos los están'} revisando en otra PC.</p>` : ''));
    }
    h = armarInicio(h, lista, todos || lista, listos, enProc, errores);
  }
  box.classList.toggle('inicio', h.startsWith('<div class="ini">'));
  if(h === vacioHtml) return;
  vacioHtml = h; box.innerHTML = h;
  box.querySelectorAll('[data-acc]').forEach(b => b.onclick = async () => {
    const acc = b.dataset.acc;
    if(acc==='elegir') $('#archivos').click();
    else if(acc==='todas') ponerFiltro('todas');
    else if(acc==='abrir') abrirCaso(b.dataset.n);
    else if(acc==='word') abrirWord(b.dataset.n, b.dataset.t);
    else if(acc==='plant') $('#bVerPlant').click();
    else if(acc==='med') $('#bVerMed').click();
    else if(acc==='config') $('#bConfig').click();
    else if(acc==='admin') $('#bAdmin').click();
    else if(acc==='pausar' || acc==='reanudar') pausarCaso(b.dataset.n, acc==='pausar', b);
    else {
      b.disabled = true;
      const est = acc==='reintentar' ? 'error' : 'nuevo';
      const ns = casosCache.filter(c => c.estado===est && (filtro!=='mia' || c.origen===MI.pc)).map(c => c.nombre);
      for(const n of ns){ try { await api('/api/procesar', {nombre: n}); } catch(e){ toast(e.message); } }
      cargarLista();
    }
  });
}
/* Pantalla de inicio: encabezado con la fecha y la IA, cifras del día, la tarjeta de «qué hacer ahora» (la de arriba),
   lo que queda para revisar, lo último que se revisó (con su Word) y accesos rápidos. Usa la misma lista que la
   columna de la izquierda (pestaña «Esta PC» o «Todas»). */
const ICO_INI = {
  subir: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 16V4M7 9l5-5 5 5M5 20h14"/></svg>',
  plant: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="4" y="3" width="16" height="18" rx="2"/><path d="M8 8h8M8 12h8M8 16h5"/></svg>',
  med:   '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/></svg>',
  config:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 6h9M17 6h3M4 12h3M11 12h9M4 18h11M19 18h1"/><circle cx="15" cy="6" r="2"/><circle cx="9" cy="12" r="2"/><circle cx="17" cy="18" r="2"/></svg>',
  admin: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 3 4 6v6c0 4.5 3.2 8.2 8 9 4.8-.8 8-4.5 8-9V6z"/><path d="m9 12 2 2 4-4"/></svg>',
  word:  '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/></svg>'};
function esHoy(t){ if(!t) return false; const d = new Date(t*1000), h = new Date(); return d.toDateString() === h.toDateString(); }
function cuandoCorto(t){ if(!t) return ''; if(esHoy(t)) return 'hoy ' + hhmm(t);
  const d = new Date(t*1000); return String(d.getDate()).padStart(2,'0') + '/' + String(d.getMonth()+1).padStart(2,'0') + ' ' + hhmm(t); }
function marcasDe(c){ const a = c.avisos; return a ? a.rojo + a.amarillo + a.turq + a.gris + a.faltan.length + a.huecos.length : (c.marcas || 0); }
function armarInicio(foco, lista, todos, listos, enProc, errores){
  const conHora = lista.some(c => c.revisado_en !== undefined);          // servidor 2026.10.32 en adelante
  const rev = lista.filter(c => c.estado==='revisado').sort((a, b) => (b.revisado_en || b.fecha) - (a.revisado_en || a.fecha));
  const revHoy = conHora ? rev.filter(c => esHoy(c.revisado_en)).length : rev.length;
  const fecha = new Date().toLocaleDateString('es-AR', {weekday:'long', day:'numeric', month:'long'});
  const ia = SRV.ia === 'ok' ? ['', 'IA lista'] : SRV.ia === 'sin_modelo' ? ['av', 'IA sin modelo'] : ['av', 'IA no lista'];
  const cifra = (n, txt, clase, acc) => acc && n
    ? `<button class="ini-cifra ${clase}" data-acc="${acc}" data-n="${acc==='abrir' ? esc(listos[0].nombre) : ''}" title="Abrir el más reciente"><b>${n}</b><span>${txt}</span></button>`
    : `<div class="ini-cifra ${n ? clase : ''}"><b>${n}</b><span>${txt}</span></div>`;
  let h = '<div class="ini"><header class="ini-cab"><div><h1>Inicio</h1><p>'
    + esc(fecha.charAt(0).toUpperCase() + fecha.slice(1)) + ' · ' + (MI.remoto ? 'PC ' + esc(MI.pc) : 'PC del servidor')
    + (todos.length !== lista.length ? ' · mostrando solo los de esta PC' : '') + '</p></div>'
    + `<span class="ini-ia"><span class="punto ${ia[0]}"></span>${ia[1]}</span></header>`
    + '<div class="ini-cifras">' + cifra(listos.length, 'para revisar', 'ac', 'abrir') + cifra(enProc.length, 'en proceso', 'ac')
    + cifra(revHoy, conHora ? 'revisados hoy' : 'revisados', '') + cifra(errores.length, 'con error', 'err') + '</div>'
    + foco;
  const fila = (c, revisado) => {
    const det = [c.estudios, revisado ? (c.revisado_en ? 'guardado ' + cuandoCorto(c.revisado_en) : '') : hhmm(c.fecha), c.medico,
      todos.length !== lista.length || c.origen === MI.pc ? '' : c.origen,
      c.bloqueado_por ? 'lo está revisando ' + c.bloqueado_por : revisado ? '' : (n => n ? n + (n===1 ? ' marca' : ' marcas') : 'sin marcas')(marcasDe(c))]
      .filter(Boolean).join(' · ');
    const nom = c.paciente || c.titulo || c.nombre;
    return `<li><button class="ini-abrir" data-acc="abrir" data-n="${esc(c.nombre)}"${c.bloqueado_por ? ' disabled' : ''} title="${revisado ? 'Volver a abrir' : 'Abrir y revisar'}">`
      + `<span class="n">${esc(nom)}</span><span class="e">${esc(det)}</span></button>`
      + (revisado ? `<button class="chico" data-acc="word" data-n="${esc(c.nombre)}" data-t="${esc(nom)}" title="${MI.remoto ? 'Descargar el Word en esta PC' : 'Abrir el Word'}">${MI.remoto ? 'Descargar Word' : 'Abrir Word'}</button>` : '')
      + '</li>';
  };
  const secs = [];
  if(listos.length > 1) secs.push(`<section class="ini-sec"><h3>Para revisar <small>del más nuevo al más antiguo</small></h3><ul class="ini-filas">`
    + listos.slice(0, 6).map(c => fila(c, false)).join('') + '</ul>'
    + (listos.length > 6 ? `<p class="ini-mas">y ${listos.length - 6} más en la lista de la izquierda.</p>` : '') + '</section>');
  if(rev.length) secs.push(`<section class="ini-sec"><h3>Últimos revisados</h3><ul class="ini-filas">`
    + rev.slice(0, 5).map(c => fila(c, true)).join('') + '</ul></section>');
  if(secs.length) h += secs.length === 2 ? `<div class="ini-dos">${secs.join('')}</div>` : secs[0];
  const acc = (a, ico, txt) => `<button data-acc="${a}">${ICO_INI[ico]}${txt}</button>`;
  h += '<section class="ini-sec"><h3>Accesos rápidos</h3><div class="ini-accesos">'
    + acc('elegir', 'subir', 'Cargar audio…') + acc('plant', 'plant', 'Plantillas') + acc('med', 'med', 'Médicos')
    + acc('config', 'config', 'Configuración') + ($('#bAdmin').hidden ? '' : acc('admin', 'admin', 'Administración'))
    + '</div></section></div>';
  return h;
}
function abrirWord(n, t){
  if(MI.remoto){
    const a = document.createElement('a'); a.href = '/api/word?nombre=' + encodeURIComponent(n);
    a.download = (t || n) + '.docx'; document.body.appendChild(a); a.click(); a.remove();
    toast('Word descargado en esta PC.');
  } else api('/api/abrir', {nombre: n}).catch(e => toast(e.message));
}
/* botón Inicio (lista y riel): cierra el informe abierto (queda como borrador y libre para otra PC) y muestra el inicio */
async function irAInicio(){
  if(vpAbierta()) cerrarVistaPrevia();
  if(actual) await cerrarCaso();
  else mostrar('vacio');
}
$('#bInicio').onclick = irAInicio;
$('#rielInicio').onclick = irAInicio;
$('#bAdmin').onclick = async () => { try { if(actual){ await guardarFormato(true); await guardarBorrador(); if(borradorPendiente()) throw new Error('Hay cambios nuevos sin guardar. Reintentá antes de salir.'); } location.href = '/admin'; } catch(e){ toast(e.message); } };
$('#tabMia').onclick = () => ponerFiltro('mia'); $('#tabTodas').onclick = () => ponerFiltro('todas');
setInterval(cargarLista, 2000); cargarLista(); cargarMiPc();

