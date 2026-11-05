// Forma de onda con marcas y huecos; arrastrar para escuchar.
/* ================================================ forma de onda con marcas y huecos */
const cv = $('#onda'), ondaCaja = $('#ondaCaja');
async function cargarOnda(n){
  onda = null; dibujarOnda();
  try { const d = await api('/api/onda?nombre=' + encodeURIComponent(n)); if(actual === n){ onda = d; dibujarOnda(); } } catch(e){}
}
function durTotal(){ return (isFinite(audio.duration) && audio.duration) || (onda && onda.dur) || (palabras.length ? palabras[palabras.length-1].fin : 0); }
function marcadoresOnda(){
  const out = [];
  for(const el of marcasPend()){ const t = tiempoDe(el); if(t == null) continue; const k = tipoDe(el); if(k) out.push({t, el, k, color: TIPOS[k][1]}); }
  for(const o of omis) if(!o.hueco && o.seg != null && !omisOk.includes(o.dato)) out.push({t: o.seg, omision: o, color: 'var(--rojo-f)', abajo: true});
  return out;
}
function huecosPend(){ return omis.filter(o => o.hueco && !omisOk.includes(o.dato)).map(o => ({o, a: o.ini ?? (o.seg - 0.5), b: o.fin ?? (o.seg + 1.5)})); }
const fondoOnda = {normal: document.createElement('canvas'), pasada: document.createElement('canvas'), clave: '', sucio: true};
new MutationObserver(()=>{ fondoOnda.sucio=true; }).observe(editor,{subtree:true,childList:true,characterData:true,attributes:true});
function pintarFondoOnda(g,w,h,D,xa){
  const X = t => t / D * w, top = 11, bottom = h - 9, mid = (top + bottom) / 2, amp = (bottom - top) / 2;
  const cAc = cssVar('--ac'), cOnda = cssVar('--onda');
  g.fillStyle = cssVar('--amarillo');                          // partes que Whisper no transcribió
  for(const q of huecosPend()) g.fillRect(X(q.a), 0, Math.max(3, X(q.b) - X(q.a)), h);
  if(rangoCursor){                                             // la línea donde está el cursor
    g.fillStyle = cssVar('--eco'); const a = X(palabras[rangoCursor[0]].ini), b = X(palabras[rangoCursor[1]].fin);
    g.fillRect(a, 0, Math.max(3, b - a), h); }
  if(onda && onda.picos.length){
    const P = onda.picos, n = P.length, f = n / ((onda.dur || D) / D) / w;
    for(let x=0; x<w; x+=3){
      const i0 = Math.floor(x * f), i1 = Math.max(i0 + 1, Math.floor((x + 3) * f)); if(i0 >= n) break;
      let m = 0; for(let i=i0; i<i1 && i<n; i++) if(P[i] > m) m = P[i];
      const hh = Math.max(0.75, m / 100 * amp);
      g.fillStyle = x < xa ? cAc : cOnda; g.fillRect(x, mid - hh, 2, hh * 2); }
  } else {                                                     // sin forma de onda: las palabras como bloques
    for(const p of palabras){ g.fillStyle = X(p.ini) < xa ? cAc : cOnda; g.fillRect(X(p.ini), mid - amp*0.3, Math.max(1, X(p.fin) - X(p.ini) - 1), amp*0.6); } }
  for(const m of marcadoresOnda()){                            // marcas: arriba; datos que faltan en el informe: abajo
    const x = X(m.t), grande = m.el && m.el === activa ? 1.6 : 1;
    g.fillStyle = colorDe(m.color); g.globalAlpha = 0.5;
    if(m.abajo) g.fillRect(x - 0.5, mid, 1, h - 7 - mid); else g.fillRect(x - 0.5, 7, 1, mid - 7);
    g.globalAlpha = 1; g.beginPath();
    if(m.abajo){ g.moveTo(x - 4.5*grande, h); g.lineTo(x + 4.5*grande, h); g.lineTo(x, h - 8*grande); }
    else { g.moveTo(x - 4.5*grande, 0); g.lineTo(x + 4.5*grande, 0); g.lineTo(x, 8*grande); }
    g.fill(); }
}
function dibujarOnda(recalcular=true){
  const w=cv.clientWidth,h=cv.clientHeight; if(!w || !h) return;
  const dpr=devicePixelRatio||1, W=Math.round(w*dpr), H=Math.round(h*dpr);
  if(cv.width!==W || cv.height!==H){cv.width=W;cv.height=H;}
  const g=cv.getContext('2d');g.setTransform(1,0,0,1,0,0);g.clearRect(0,0,W,H);
  const D=durTotal();if(!actual || !D){fondoOnda.clave='';return;}
  const clave=JSON.stringify([actual,W,H,D]);
  if(recalcular || fondoOnda.sucio || fondoOnda.clave!==clave){
    for(const [lienzo,xa] of [[fondoOnda.normal,-1],[fondoOnda.pasada,w+1]]){
      lienzo.width=W;lienzo.height=H;const c=lienzo.getContext('2d');c.setTransform(dpr,0,0,dpr,0,0);
      pintarFondoOnda(c,w,h,D,xa);
    }
    fondoOnda.clave=clave;fondoOnda.sucio=false;
  }
  g.drawImage(fondoOnda.normal,0,0);
  const x=Math.max(0,Math.min(W,(audio.currentTime||0)/D*W));
  if(x>0)g.drawImage(fondoOnda.pasada,0,0,x,H,0,0,x,H);
  g.fillStyle=cssVar('--tx');g.fillRect(x-dpr*.75,0,dpr*1.5,H);
}

function ondaEn(ev){
  const r = cv.getBoundingClientRect(), x = ev.clientX - r.left, D = durTotal();
  let cerca = null, dmin = 7;
  for(const m of marcadoresOnda()){ const d = Math.abs(m.t / D * r.width - x); if(d < dmin){ dmin = d; cerca = m; } }
  return {x, t: Math.max(0, Math.min(D, x / r.width * D)), m: cerca};
}
ondaCaja.addEventListener('mousemove', ev => {
  if(!actual || !durTotal()) return;
  const p = ondaEn(ev), tip = $('#ondaTip'); let txt = mmss(p.t);
  if(p.m) txt += p.m.omision ? ' · falta en el informe: ' + p.m.omision.dato
                             : ' · ' + TIPOS[p.m.k][0] + ': «' + p.m.el.textContent.trim().slice(0, 40) + '»';
  else if(huecosPend().some(q => p.t >= q.a && p.t <= q.b)) txt += ' · posible parte no transcrita';
  tip.textContent = txt; tip.style.display = 'block';
  tip.style.left = Math.min(Math.max(p.x, tip.offsetWidth/2 + 4), cv.clientWidth - tip.offsetWidth/2 - 4) + 'px';
  ondaCaja.style.cursor = p.m ? 'pointer' : 'col-resize';
});
ondaCaja.addEventListener('mouseleave', () => $('#ondaTip').style.display = 'none');
ondaCaja.addEventListener('click', ev => {
  if(scrub.evitarClic){ scrub.evitarClic = false; return; }     // fue un arrastre, no un clic
  if(!actual || !durTotal()) return;
  const p = ondaEn(ev);
  if(p.m && p.m.el){ seleccionar(p.m.el); return; }
  if(p.m && p.m.omision){ escuchar(p.m.t); return; }
  audio.currentTime = p.t; audio.play();
});
/* ------------------------------------------------ arrastrar sobre la onda = escuchar mientras se mueve (como una cinta) */
const scrub = {ctx:null, buf:null, rev:null, de:null, cargando:null, abajo:false, activo:false, x0:0,
               t:0, tSon:0, prox:0, timer:0, raf:0, evitarClic:false, controlador:null, generacion:0, fuentes:new Set()};
const TICK = 0.03;                                               // cada 30 ms suena el tramo recorrido
function ctxScrub(){
  if(!scrub.ctx){ try { scrub.ctx = new AudioContext({sampleRate: 24000}); } catch(e){ scrub.ctx = new AudioContext(); } }
  return scrub.ctx;
}
function liberarScrub(){
  scrub.generacion++;scrub.controlador?.abort();scrub.controlador=null;
  scrub.buf=scrub.rev=scrub.cargando=scrub.de=null;
  scrub.abajo=scrub.activo=false;clearInterval(scrub.timer);cancelAnimationFrame(scrub.raf);scrub.raf=0;
  for(const fuente of scrub.fuentes){try{fuente.stop();}catch(e){}}scrub.fuentes.clear();
  ondaCaja.classList.remove('arrastrando');
}
audio.addEventListener('emptied', liberarScrub);
function bufferScrub(){                                          // el audio del caso decodificado (mono) y al revés
  const n = actual; if(!n) return Promise.resolve(null);
  if(scrub.de === n && (scrub.buf || scrub.cargando)) return scrub.buf ? Promise.resolve(scrub.buf) : scrub.cargando;
  liberarScrub();
  scrub.de = n; const generacion = scrub.generacion, ctx = ctxScrub();
  const controlador = new AbortController(); scrub.controlador = controlador;
  scrub.cargando = (async () => {
    const r = await fetch('/audio/' + encodeURIComponent(n), {signal:controlador.signal}); if(!r.ok) throw new Error('audio ' + r.status);
    const datos = await r.arrayBuffer();
    if(scrub.generacion !== generacion) return null;
    const b = await ctx.decodeAudioData(datos);
    if(scrub.generacion !== generacion) return null;
    const L = b.length, mono = ctx.createBuffer(1, L, b.sampleRate);
    const m = mono.getChannelData(0), k = b.numberOfChannels;
    for(let c=0; c<k; c++){ const d = b.getChannelData(c); for(let i=0; i<L; i++) m[i] += d[i] / k; }
    scrub.buf = mono; scrub.cargando = null; return mono;
  })().catch(() => { if(scrub.generacion === generacion){ scrub.de = null; scrub.cargando = null; } return null; });
  return scrub.cargando;
}
function granoScrub(desde, hasta){                               // suena desde→hasta en TICK segundos (al revés si va para atrás)
  const b = scrub.buf, ctx = scrub.ctx; if(!b) return;
  const atras = hasta < desde, rate = Math.abs(hasta - desde) / TICK, D = b.duration;
  const ahora = ctx.currentTime;
  if(scrub.prox < ahora + 0.005 || scrub.prox > ahora + 0.12) scrub.prox = ahora + 0.01;   // sin acumular demora
  const t0 = scrub.prox, ov = 0.012, dur = TICK + ov;
  const src = ctx.createBufferSource(), g = ctx.createGain();
  if(atras && !scrub.rev){
    scrub.rev=ctx.createBuffer(1,b.length,b.sampleRate);const m=b.getChannelData(0),v=scrub.rev.getChannelData(0);
    for(let i=0;i<m.length;i++)v[i]=m[m.length-1-i];
  }
  scrub.fuentes.add(src);src.onended=()=>{scrub.fuentes.delete(src);src.disconnect();g.disconnect();};
  src.buffer = atras ? scrub.rev : b; src.playbackRate.value = rate;
  const v = volumenActual();                                     // el mismo volumen que el reproductor (0 = silencio)
  g.gain.setValueAtTime(0, t0); g.gain.linearRampToValueAtTime(v, t0 + ov);
  g.gain.setValueAtTime(v, t0 + TICK); g.gain.linearRampToValueAtTime(0, t0 + dur);
  src.connect(g); g.connect(ctx.destination);
  const pos = atras ? D - desde : desde;
  src.start(t0, Math.max(0, Math.min(D - 0.005, pos))); src.stop(t0 + dur + 0.01);
  scrub.prox = t0 + TICK;
}
function tickScrub(){
  if(!scrub.activo || !scrub.buf) return;
  let desde = scrub.tSon; const hasta = scrub.t, dist = Math.abs(hasta - desde);
  if(dist < 0.002){ scrub.tSon = hasta; return; }                // quieto: silencio
  if(dist < 0.3 * TICK) return;                                  // muy lento: junta movimiento antes de sonar
  if(dist > 4 * TICK) desde = hasta - Math.sign(hasta - desde) * 4 * TICK;   // salto grande: suena solo el final, a 4×
  granoScrub(desde, hasta); scrub.tSon = hasta;
}
function moverCabezal(){                                         // el cabezal, el dictado y la onda siguen al mouse
  scrub.raf = 0; if(Math.abs(audio.currentTime - scrub.t) > 0.01) audio.currentTime = scrub.t;
}
// La descarga/decodificación comienza al interactuar, no al pasar el mouse.
ondaCaja.addEventListener('pointerdown', ev => {
  if(ev.button !== 0 || !actual || !durTotal()) return;
  ctxScrub().resume(); bufferScrub();
  scrub.abajo = true; scrub.activo = false; scrub.x0 = ev.clientX;
  ondaCaja.setPointerCapture(ev.pointerId);
});
ondaCaja.addEventListener('pointermove', ev => {
  if(!scrub.abajo) return;
  const p = ondaEn(ev);
  if(!scrub.activo){
    if(Math.abs(ev.clientX - scrub.x0) < 4) return;              // todavía puede ser un clic
    scrub.activo = true; audio.pause(); ocultarExplica && ocultarExplica();
    scrub.tSon = audio.currentTime = ondaEn({clientX: scrub.x0}).t; scrub.prox = 0;
    ondaCaja.classList.add('arrastrando');
    scrub.timer = setInterval(tickScrub, TICK * 1000);
  }
  scrub.t = p.t;
  if(!scrub.buf) $('#ondaTip').textContent = mmss(p.t) + ' · preparando el audio…';
  if(!scrub.raf) scrub.raf = requestAnimationFrame(moverCabezal);
});
function soltarScrub(ev, cancelado){
  if(!scrub.abajo) return; scrub.abajo = false;
  if(!scrub.activo) return;                                      // fue un clic: lo atiende 'click'
  scrub.activo = false; scrub.evitarClic = !cancelado; clearInterval(scrub.timer);
  cancelAnimationFrame(scrub.raf); scrub.raf = 0; ondaCaja.classList.remove('arrastrando');
  audio.currentTime = scrub.t;
  if(!cancelado){ ultimaPausa = 0; audio.play(); }               // al soltar sigue sonando desde ahí, sin retroceder
  setTimeout(() => scrub.evitarClic = false, 300);
}
ondaCaja.addEventListener('pointerup', ev => soltarScrub(ev, false));
ondaCaja.addEventListener('pointercancel', ev => soltarScrub(ev, true));
new ResizeObserver(() => dibujarOnda()).observe(ondaCaja);
audio.addEventListener('play', () => { cancelAnimationFrame(rafOnda);
  const ciclo = () => { dibujarOnda(false); if(!audio.paused && !document.hidden) rafOnda = requestAnimationFrame(ciclo); }; rafOnda = requestAnimationFrame(ciclo); });
audio.addEventListener('pause', () => { cancelAnimationFrame(rafOnda); dibujarOnda(); });
document.addEventListener('visibilitychange',()=>{
  cancelAnimationFrame(rafOnda);
  if(!document.hidden && !audio.paused){const ciclo=()=>{dibujarOnda(false);if(!audio.paused && !document.hidden)rafOnda=requestAnimationFrame(ciclo);};rafOnda=requestAnimationFrame(ciclo);}
});
audio.addEventListener('loadedmetadata', dibujarOnda);
audio.addEventListener('emptied', () => { $('#prog').value = 0; $('#tiempo').textContent = '0:00 / 0:00'; });

