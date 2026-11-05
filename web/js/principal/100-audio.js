// Reproductor de audio.
/* ------------------------------------------------ audio */
const bPlay = $('#bPlay');
bPlay.onclick = () => audio.paused ? audio.play() : audio.pause();
$('#bAtras').onclick = () => audio.currentTime = Math.max(0, audio.currentTime - PREF.salto());
$('#bAdel').onclick = () => audio.currentTime = Math.min(audio.duration||0, audio.currentTime + PREF.salto());
$('#vel').onchange = e => { audio.playbackRate = +e.target.value; grabarLS('velUltima', e.target.value); };
$('#prog').oninput = e => { if(audio.duration) audio.currentTime = e.target.value/1000*audio.duration; };
/* volumen: se guarda en esta PC ('volumen', no sincroniza con el transcriptor: depende de sus parlantes o auriculares).
   0 % es silenciado; el parlante silencia y vuelve al último nivel ('volumenAntes'). Vale también para el arrastre
   sobre la onda y las muestras de voz de Médicos, que suenan aparte (volumenActual). */
const bVol = $('#bVol'), vol = $('#vol');
let volumenAntes = 100;
const acotarVolumen = (p, otro) => { p = Math.round(+p); return Number.isFinite(p) ? Math.max(0, Math.min(100, p)) : otro; };
function volumenActual(){ return audio.volume; }
function ponerVolumen(p, guardar = true){
  p = acotarVolumen(p, 100);
  vol.value = String(p); audio.volume = p / 100;
  if(AUDIO_M) AUDIO_M.volume = p / 100;
  if(guardar) grabarLS('volumen', String(p));
  pintarVolumen();
}
function recordarVolumen(){                       // el nivel al que vuelve el parlante después de silenciar
  const p = +vol.value; if(p > 0){ volumenAntes = p; grabarLS('volumenAntes', String(p)); }
}
function pintarVolumen(){
  const p = +vol.value, mudo = p === 0;
  $('#volumen').dataset.nivel = mudo ? 'silencio' : p < 50 ? 'bajo' : 'alto';
  vol.title = mudo ? 'Volumen: silenciado (0 %)' : `Volumen: ${p} %`;
  vol.setAttribute('aria-valuetext', mudo ? 'silenciado, 0 %' : p + ' %');
  bVol.title = mudo ? `Activar el sonido (volver a ${volumenAntes} %)` : `Silenciar (volumen ${p} %)`;
  bVol.setAttribute('aria-label', mudo ? 'Activar el sonido' : 'Silenciar');
  bVol.setAttribute('aria-pressed', String(mudo));
}
function iniciarVolumen(){                        // la llama 240-preferencias-pantalla.js, cuando leerLS ya existe
  volumenAntes = acotarVolumen(leerLS('volumenAntes') || 100, 100) || 100;
  const v = leerLS('volumen');
  ponerVolumen(v === '' ? 100 : acotarVolumen(v, 100), false);
}
vol.oninput = () => ponerVolumen(vol.value);
vol.onchange = recordarVolumen;
bVol.onclick = () => { if(+vol.value > 0){ recordarVolumen(); ponerVolumen(0); } else ponerVolumen(volumenAntes || 100); };
$('#volumen').addEventListener('wheel', e => {
  if(!e.deltaY) return;
  e.preventDefault(); ponerVolumen(+vol.value + (e.deltaY < 0 ? 5 : -5)); recordarVolumen();
}, {passive: false});
audio.addEventListener('play', () => { bPlay.textContent='❚❚'; const r = PREF.retroceso(); if(r && Date.now()-ultimaPausa < 60000 && ultimaPausa) audio.currentTime = Math.max(0, audio.currentTime-r); });
audio.addEventListener('pause', () => { bPlay.textContent='▶'; ultimaPausa = Date.now(); });
let palActual = -1;
audio.addEventListener('timeupdate', () => {
  const t = audio.currentTime;
  $('#tiempo').textContent = mmss(t)+' / '+mmss(audio.duration);
  if(audio.duration) $('#prog').value = t/audio.duration*1000;
  let lo=0, hi=palabras.length-1, i=-1;
  while(lo<=hi){ const m=(lo+hi)>>1; if(palabras[m].ini<=t){ i=m; lo=m+1; } else hi=m-1; }
  if(i!==palActual){
    dict.querySelector('.actual')?.classList.remove('actual'); palActual=i;
    const sp = i>=0 ? dict.children[i] : null;
    if(sp){ sp.classList.add('actual');
      if($('#seguir').checked){ const r=sp.getBoundingClientRect(), c=dict.getBoundingClientRect(); if(r.top<c.top+20||r.bottom>c.bottom-20) sp.scrollIntoView({block:'center',behavior:'smooth'}); } }
    if(!audio.paused) marcarLineaSonando(i);
  }
  if(audio.paused) dibujarOnda();
});
dict.addEventListener('click', e => { const sp = e.target.closest('span[data-i]'); if(sp){ audio.currentTime = palabras[+sp.dataset.i].ini; audio.play(); }});

