// Reproductor de audio.
/* ------------------------------------------------ audio */
const bPlay = $('#bPlay');
bPlay.onclick = () => audio.paused ? audio.play() : audio.pause();
$('#bAtras').onclick = () => audio.currentTime = Math.max(0, audio.currentTime - PREF.salto());
$('#bAdel').onclick = () => audio.currentTime = Math.min(audio.duration||0, audio.currentTime + PREF.salto());
$('#vel').onchange = e => { audio.playbackRate = +e.target.value; grabarLS('velUltima', e.target.value); };
$('#prog').oninput = e => { if(audio.duration) audio.currentTime = e.target.value/1000*audio.duration; };
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

