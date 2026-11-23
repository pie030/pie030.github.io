/* Shared free-view tools: fullscreen and optional animation playback. */
(() => {
  'use strict';
  const buttons=[...document.querySelectorAll('[data-viewer-fullscreen]')];
  const target=button=>button.closest('[data-model-preview], .viewer-frame');
  function fullscreenLabels(){
    for(const button of buttons){
      const stage=target(button);
      button.hidden=!Boolean(document.fullscreenEnabled && stage?.requestFullscreen);
      const active=document.fullscreenElement===stage;
      button.textContent=active?'Exit full screen':'Full screen';
      button.setAttribute('aria-pressed',String(active));
    }
  }
  for(const button of buttons)button.addEventListener('click',async()=>{
    const stage=target(button);if(!stage)return;
    try{if(document.fullscreenElement===stage)await document.exitFullscreen();else await stage.requestFullscreen();}
    catch{const status=stage.parentElement.querySelector('[data-model-feedback], #viewer-status');if(status)status.textContent='Full screen is unavailable. You can still rotate and zoom.';}
  });
  document.addEventListener('fullscreenchange',fullscreenLabels);
  document.addEventListener('click',event=>{
    const close=event.target.closest('[data-model-close]');
    if(close && document.fullscreenElement===close.closest('[data-model-preview]'))document.exitFullscreen().catch(()=>{});
  });
  fullscreenLabels();
  for(const stage of document.querySelectorAll('[data-model-preview]')){
    const controls=stage.querySelector('[data-model-animation-controls]'),clips=stage.querySelector('[data-model-clip]'),play=stage.querySelector('[data-model-play]');
    const status=stage.parentElement.querySelector('[data-model-feedback]');
    const requested=(stage.dataset.modelClips||'').split(',').filter(Boolean),labels={Caminhada:'Walk',Impacto:'Ground strike'};
    let viewer=null,playing=false;
    function playbackLabel(){if(play){play.textContent=playing?'Pause':'Play';play.setAttribute('aria-pressed',String(playing));play.setAttribute('aria-label',playing?'Pause animation':'Play animation');}}
    function pause(){if(viewer && typeof viewer.pause==='function')viewer.pause();playing=false;playbackLabel();}
    function connect(){
      const next=stage.querySelector('model-viewer'),ready=stage.classList.contains('is-ready');
      if(next===viewer && ready)return;
      pause();viewer=ready?next:null;if(controls)controls.hidden=true;if(!viewer)return;
      viewer.setAttribute('touch-action','none');viewer.setAttribute('min-camera-orbit','auto 0deg auto');viewer.setAttribute('max-camera-orbit','auto 180deg auto');
      if(status)status.textContent='Drag to rotate; Shift-drag to pan; scroll or pinch to zoom.';
      if(!controls||!clips||!play)return;
      const names=requested.filter(name=>(viewer.availableAnimations||[]).includes(name));
      clips.replaceChildren();
      for(const name of names){const option=document.createElement('option');option.value=name;option.textContent=labels[name]||name;clips.append(option);}
      if(!names.length)return;
      viewer.setAttribute('animation-crossfade-duration','0');viewer.animationName=names[0];viewer.currentTime=0;pause();controls.hidden=false;
    }
    clips?.addEventListener('change',()=>{if(viewer){pause();viewer.animationName=clips.value;viewer.currentTime=0;}});
    play?.addEventListener('click',()=>{if(!viewer)return;if(playing)pause();else{viewer.play();playing=true;playbackLabel();}});
    document.addEventListener('visibilitychange',()=>{if(document.hidden)pause();});
    if('IntersectionObserver' in window)new IntersectionObserver(entries=>{if(!entries[0].isIntersecting)pause();}).observe(stage);
    new MutationObserver(connect).observe(stage,{childList:true,attributes:true,attributeFilter:['class']});connect();
  }
  // A direct 3D link expresses the visitor's choice to open the model.
  if(location.hash==='#interactive-viewer'){
    document.querySelector('#interactive-viewer [data-model-launch]')?.click();
  }else if(location.hash==='#model-view'){
    document.querySelector('#open-model')?.click();
  }
})();