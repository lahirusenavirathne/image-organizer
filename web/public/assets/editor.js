'use strict';
(() => {
  const root = document.getElementById('photo-editor');
  if (!root) return;
  const form = document.getElementById('editor-form');
  const $ = id => document.getElementById(id);
  const picture = $('editor-preview');
  const original = $('editor-before-image');
  const divider = $('editor-compare-divider');
  const imageStage = $('editor-image-stage');
  const cropBox = $('editor-crop-box');
  const holder = imageStage.parentElement;
  const message = $('editor-status');
  const loading = $('editor-loading');
  const compare = $('editor-before');
  const comparePosition = $('editor-compare-position');
  const compareControls = $('editor-compare-control');
  const saveState = $('editor-save-state');
  const previewHelp = $('editor-preview-help');
  const photoId = Number(root.dataset.photoId);
  const csrf = document.querySelector('meta[name="csrf-token"]')?.content || '';
  let revision = Number(root.dataset.revision);
  let saved;
  try { saved = JSON.parse(root.dataset.recipe || '{}'); } catch { saved = {}; }
  const baseline = {rotate:0,straighten:0,crop:'original',crop_manual:0,crop_x:0,crop_y:0,crop_w:1000,crop_h:1000,exposure:0,contrast:0,highlights:0,shadows:0,saturation:0,warmth:0,sharpness:0};
  const hslColors=['red','orange','yellow','green','cyan','blue','purple','magenta'];
  const hslFields=hslColors.flatMap(color=>['hue','sat','lum'].map(part=>`hsl_${color}_${part}`));
  const advancedFields=['whites','blacks','vibrance','tint','curve_shadows','curve_midtones','curve_highlights',...hslFields];
  for(const key of advancedFields)baseline[key]=0;
  const recipeFields = Object.keys(baseline);
  const toneFields = ['exposure','contrast','highlights','shadows','saturation','warmth','sharpness',...advancedFields];
  const inputs = recipeFields.map(name => form.elements.namedItem(name)).filter(input => input.type!=='hidden');
  const field = name => form.elements.namedItem(name);
  let timer = null, controller = null, imageUrl = null, beforeUrl = null, seq = 0;
  let beforeGeometry = '', zoom = 1, panX = 0, panY = 0, pointer = null;
  let cropMode = false, cropRect = null, cropPointer = null;
  let undoStack = [], redoStack = [], currentSnapshot = '', lastEditKey = '', lastEditAt = 0;
  const presetKey = 'glpm-photo-editor-presets-v1';
  const status = (text, error = false) => { message.textContent = text; message.classList.toggle('error', error); };
  const safeStorageRead = () => { try { return localStorage.getItem(presetKey); } catch { return null; } };
  const safeStorageWrite = value => { try { localStorage.setItem(presetKey, value); return true; } catch { return false; } };
  const normalize = values => ({ ...baseline, ...Object.fromEntries(recipeFields.filter(k => values && Object.prototype.hasOwnProperty.call(values,k)).map(k => [k,values[k]])) });
  function recipe() {
    const r = { ...baseline, rotate:Number(field('rotate').value), crop:field('crop').value };
    for(const key of ['straighten','crop_manual','crop_x','crop_y','crop_w','crop_h'])r[key]=Number(field(key).value);
    for (const key of toneFields) r[key] = Number(field(key).value);
    return r;
  }
  const serial = values => JSON.stringify(normalize(values));
  const nowDirty = () => serial(recipe()) !== serial(saved);
  function savedState(text) {
    if (!saveState) return;
    const dirty = nowDirty();
    saveState.dataset.dirty = String(dirty);
    saveState.lastChild.textContent = ' ' + (text || (dirty ? 'Unsaved changes' : 'All changes saved'));
  }
  function paintRange(el) {
    const min=Number(el.min),max=Number(el.max),value=Number(el.value);
    el.style.setProperty('--slider-pct', Math.round((value-min)*100/(max-min))+'%');
  }
  function updateToneCurve() {
    const r=recipe();
    const offsets=[0,r.curve_shadows*.5,r.curve_midtones*.5,r.curve_highlights*.5,0];
    const x=[0,64,128,192,255];
    const commands=[];
    for(let v=0;v<=255;v+=3){
      const i=v<64?0:v<128?1:v<192?2:3;
      const t=(v-x[i])/(x[i+1]-x[i]);const smooth=t*t*(3-2*t);
      const n=v/255;
      const val=v+offsets[i]*(1-smooth)+offsets[i+1]*smooth+r.blacks*.34*(1-n)**3+r.whites*.34*n**3;
      commands.push(`${commands.length?'L':'M'}${v} ${(255-Math.min(255,Math.max(0,val))).toFixed(1)}`);
    }
    $('editor-tone-curve-path').setAttribute('d',commands.join(' '));
  }
  let histogramFrame=0;
  function refreshHistogram(){
    if(histogramFrame)cancelAnimationFrame(histogramFrame);
    histogramFrame=requestAnimationFrame(()=>{
      histogramFrame=0;
      const output=$('editor-clipping');const canvas=$('editor-histogram');if(!canvas||!picture.naturalWidth)return;
      try{
        const scratch=document.createElement('canvas');scratch.width=160;scratch.height=96;
        const sx=scratch.getContext('2d',{willReadFrequently:true});
        if(!sx)throw new Error('Canvas unavailable');
        sx.drawImage(picture,0,0,scratch.width,scratch.height);
        const rgba=sx.getImageData(0,0,scratch.width,scratch.height).data;
        const bins=Array.from({length:3},()=>new Uint32Array(64));
        let shadows=0,highlights=0;const count=rgba.length/4;
        for(let i=0;i<rgba.length;i+=4){
          for(let channel=0;channel<3;channel++)bins[channel][Math.min(63,rgba[i+channel]>>2)]++;
          const lum=(rgba[i]*.299+rgba[i+1]*.587+rgba[i+2]*.114);
          if(lum<5)shadows++;if(lum>250)highlights++;
        }
        const ctx=canvas.getContext('2d');if(!ctx)return;
        const width=canvas.width,height=canvas.height;
        ctx.clearRect(0,0,width,height);ctx.fillStyle='#101b15';ctx.fillRect(0,0,width,height);
        const peak=Math.max(...bins.flatMap(channel=>[...channel]));
        const colors=['rgba(255,112,117,.78)','rgba(110,220,143,.72)','rgba(111,157,255,.8)'];
        bins.forEach((channel,k)=>{
          ctx.beginPath();ctx.lineWidth=1.6;ctx.strokeStyle=colors[k];
          channel.forEach((n,j)=>{const x=j*width/63;const y=height-3-(n/Math.max(1,peak))*(height-7);if(j===0)ctx.moveTo(x,y);else ctx.lineTo(x,y);});
          ctx.stroke();
        });
        output.textContent=`Black clip ${(100*shadows/count).toFixed(1)}% · White clip ${(100*highlights/count).toFixed(1)}%`;
      }catch{
        output.textContent='Histogram unavailable for this preview';
      }
    });
  }
  function updateLabels() {
    for (const key of toneFields) {
      const input=field(key);$( 'edit-'+key+'-value').textContent=String(input.value);paintRange(input);
    }
    updateToneCurve();
    $('editor-straighten-value').textContent=(Number(field('straighten').value)/10).toFixed(1)+'°';
    paintRange(field('straighten'));
    $('editor-quality-label').textContent=field('quality').value+'%';
    $('editor-quality').disabled=field('format').value==='png';
    $('editor-quality-hint').textContent=field('format').value==='png' ? 'PNG is lossless; the quality control is not used.' : 'Higher quality creates larger files. 80–90 is a useful web starting point.';
  }
  function updateUndoButtons() {$('editor-undo').disabled=!undoStack.length;$('editor-redo').disabled=!redoStack.length;}
  function loadForm(values, preserveHistory = false) {
    const normalized=normalize(values);
    for (const key of recipeFields) field(key).value=String(normalized[key]);
    if (!preserveHistory) {undoStack=[];redoStack=[];currentSnapshot=serial(normalized);lastEditKey='';updateUndoButtons();}
    updateLabels();savedState();if(cropMode){cropRect=null;}queuePreview();
  }
  function recordEdit(key) {
    const next=serial(recipe());if(next===currentSnapshot)return;
    const now=Date.now();
    if (!(key===lastEditKey && now-lastEditAt<450)) {
      undoStack.push(currentSnapshot);
      if(undoStack.length>100)undoStack.shift();
    }
    currentSnapshot=next;redoStack=[];lastEditKey=key;lastEditAt=now;
    updateUndoButtons();savedState();queuePreview();
  }
  function historyStep(direction) {
    const from=direction==='undo'?undoStack:redoStack, to=direction==='undo'?redoStack:undoStack;
    if(!from.length)return;
    to.push(currentSnapshot);
    currentSnapshot=from.pop();lastEditKey='';
    try {loadForm(JSON.parse(currentSnapshot),true);} catch {return;}
    updateUndoButtons();status(direction==='undo'?'Last adjustment undone.':'Adjustment restored.');
  }
  async function send(action, params, abortSignal=null) {
    const data=new FormData();data.set('action',action);data.set('id',String(photoId));data.set('recipe',JSON.stringify(params));data.set('csrf',csrf);
    if(action==='save')data.set('version',String(revision));
    if(action==='export'||action==='save_copy') {
      data.set('width',field('width').value);data.set('height',field('height').value);
      data.set('format',field('format').value);data.set('quality',field('quality').value);
      if(action==='save_copy')data.set('copy_name',field('copy_name').value.trim());
    }
    const res=await fetch('editor_action.php',{method:'POST',body:data,credentials:'same-origin',signal:abortSignal,cache:'no-store'});
    if(!res.ok){const error=await res.json().catch(()=>null);throw new Error(error?.error||`Server returned HTTP ${res.status}`);}
    return res;
  }
  function queuePreview(){clearTimeout(timer);timer=setTimeout(refresh,360);}
  function updateCompareSplit() {
    const value=Number(comparePosition.value);
    original.style.clipPath=`inset(0 ${100-value}% 0 0)`;
    divider.style.left=value+'%';
  }
  function updateCompareUI() {
    compareControls.hidden=!compare.checked;
    original.hidden=!compare.checked;
    divider.hidden=!compare.checked;
    updateCompareSplit();
  }
  async function refresh() {
    if(controller)controller.abort();controller=new AbortController();const local=++seq;
    loading.hidden=false;
    const settings=recipe();
    const geometry=['crop','rotate','straighten','crop_manual','crop_x','crop_y','crop_w','crop_h'].map(k=>settings[k]).join('|');
    try {
      const displaySettings=cropMode?{...settings,crop:'original',crop_manual:0,crop_x:0,crop_y:0,crop_w:1000,crop_h:1000}:settings;
      const editedResponse=await send('preview',displaySettings,controller.signal);
      const editedBlob=await editedResponse.blob();
      if(local!==seq)return;
      let priorBlob=null;
      if(compare.checked && (geometry!==beforeGeometry || !beforeUrl)) {
        const beforeResponse=await send('preview_before',settings,controller.signal);
        priorBlob=await beforeResponse.blob();
      }
      if(local!==seq)return;
      const newUrl=URL.createObjectURL(editedBlob),oldUrl=imageUrl;
      imageUrl=newUrl;picture.onload=()=>{if(oldUrl)URL.revokeObjectURL(oldUrl);if(cropMode){if(!cropRect)cropRect=initialCropRect();placeCrop();}refreshHistogram();};picture.src=newUrl;
      if(priorBlob) {
        const oldBefore=beforeUrl;beforeUrl=URL.createObjectURL(priorBlob);
        original.onload=()=>{if(oldBefore)URL.revokeObjectURL(oldBefore);};original.src=beforeUrl;
        beforeGeometry=geometry;
      }
      updateCompareUI();loading.hidden=true;
      if(previewHelp)previewHelp.textContent=cropMode?'Crop mode: resize the corner handles or drag inside the selection to move. Press Done cropping to apply.':compare.checked?'Drag the comparison slider to see original tones versus edited tones. Crop and rotation match.':'Showing adjusted preview · Original file preserved.';
    } catch(error) {
      if(error.name==='AbortError'||local!==seq)return;
      loading.hidden=true;status('Preview error: '+error.message,true);
    }
  }
  // Crop geometry is normalized to the full preview after rotation/straightening, not to screen pixels.
  const bound=(value,low,high)=>Math.max(low,Math.min(high,value));
  function pictureGeometry(){
    const w=imageStage.clientWidth,h=imageStage.clientHeight;
    if(!w||!h||!picture.naturalWidth||!picture.naturalHeight)return null;
    const ratio=picture.naturalWidth/picture.naturalHeight;
    const width=Math.min(w,h*ratio),height=width/ratio;
    return {left:(w-width)/2,top:(h-height)/2,width,height};
  }
  const ratioPresets={'square':1,'4:3':4/3,'3:2':1.5,'16:9':16/9,'272:300':272/300};
  function aspectLocked(){
    const option=field('crop').value,geometry=pictureGeometry();
    if(!geometry||option==='free')return null;
    if(option==='original')return geometry.width/geometry.height;
    return ratioPresets[option]||null;
  }
  function initialCropRect(){
    const selected=recipe();
    if(selected.crop_manual)return {x:selected.crop_x/1000,y:selected.crop_y/1000,w:selected.crop_w/1000,h:selected.crop_h/1000};
    const geometry=pictureGeometry(),ratio=aspectLocked();
    if(!geometry||ratio===null)return {x:0,y:0,w:1,h:1};
    const imageRatio=geometry.width/geometry.height;
    const w=imageRatio>ratio?ratio/imageRatio:1;
    const h=imageRatio>ratio?1:imageRatio/ratio;
    return {x:(1-w)/2,y:(1-h)/2,w,h};
  }
  function placeCrop(){
    if(!cropMode||!cropRect){cropBox.hidden=true;return;}
    const g=pictureGeometry();if(!g){cropBox.hidden=true;return;}
    cropBox.hidden=false;
    cropBox.style.left=(g.left+cropRect.x*g.width)+'px';
    cropBox.style.top=(g.top+cropRect.y*g.height)+'px';
    cropBox.style.width=(cropRect.w*g.width)+'px';
    cropBox.style.height=(cropRect.h*g.height)+'px';
  }
  function encodeCrop(rect){
    const x=bound(Math.round(rect.x*1000),0,999),y=bound(Math.round(rect.y*1000),0,999);
    field('crop_manual').value='1';field('crop_x').value=String(x);field('crop_y').value=String(y);
    field('crop_w').value=String(bound(Math.round(rect.w*1000),1,1000-x));
    field('crop_h').value=String(bound(Math.round(rect.h*1000),1,1000-y));
    savedState();
  }
  function resizeCrop(start,handle,dx,dy){
    if(handle==='move')return {x:bound(start.x+dx,0,1-start.w),y:bound(start.y+dy,0,1-start.h),w:start.w,h:start.h};
    const west=handle.includes('w'),north=handle.includes('n');
    const anchorX=west?start.x+start.w:start.x,anchorY=north?start.y+start.h:start.y;
    const endX=(west?start.x:start.x+start.w)+dx,endY=(north?start.y:start.y+start.h)+dy;
    const maxW=west?anchorX:1-anchorX,maxH=north?anchorY:1-anchorY;
    let w=bound(Math.abs(anchorX-endX),.03,maxW),h=bound(Math.abs(anchorY-endY),.03,maxH);
    const g=pictureGeometry(),aspect=aspectLocked();
    if(g&&aspect!==null){
      const normalizedRatio=aspect*g.height/g.width;
      const wFromH=h*normalizedRatio;
      if(Math.abs(wFromH-start.w)>Math.abs(w-start.w))w=wFromH;
      w=bound(w,Math.min(.03,maxW,maxH*normalizedRatio),Math.min(maxW,maxH*normalizedRatio));
      h=w/normalizedRatio;
    }
    return {x:west?anchorX-w:anchorX,y:north?anchorY-h:anchorY,w,h};
  }
  function toggleCropMode(force){
    const next=force===undefined?!cropMode:!!force;
    if(next===cropMode)return;
    cropMode=next;
    if(cropMode){
      changeZoom(1);compare.checked=false;updateCompareUI();cropRect=null;
    } else {cropPointer=null;cropBox.hidden=true;cropRect=null;}
    $('editor-crop-toggle').textContent=cropMode?'Done cropping':'Edit crop on image';
    $('editor-crop-toggle').setAttribute('aria-pressed',String(cropMode));
    for(const id of ['editor-zoom-out','editor-zoom-in','editor-zoom-fit','editor-before'])$(id).disabled=cropMode;
    if(cropMode){
      $('panel-crop').open=true;
      status('Crop mode: drag corners or move the selection. Use focused handles and arrow keys for precise changes.');
    }
    queuePreview();
  }
  function resetCrop(){
    field('crop_manual').value='0';
    for(const [key,value] of Object.entries({crop_x:0,crop_y:0,crop_w:1000,crop_h:1000}))field(key).value=String(value);
    cropRect=null;recordEdit('crop-reset');
    if(cropMode)queuePreview();
    status('Crop reset to the selected aspect ratio. Original photo remains unchanged.');
  }
  function commitCropChange(){encodeCrop(cropRect);recordEdit('crop-drag');}
  cropBox.querySelectorAll('[data-crop-handle]').forEach(handle=>{
    const name=handle.dataset.cropHandle;
    handle.addEventListener('pointerdown',event=>{
      if(!cropMode||!cropRect||event.button!==0)return;
      event.preventDefault();event.stopPropagation();
      cropPointer={id:event.pointerId,name,x:event.clientX,y:event.clientY,rect:{...cropRect},settings:recipe()};
      handle.setPointerCapture(event.pointerId);handle.classList.add('dragging');
    });
    handle.addEventListener('pointermove',event=>{
      if(!cropPointer||event.pointerId!==cropPointer.id||name!==cropPointer.name)return;
      const g=pictureGeometry();if(!g)return;
      cropRect=resizeCrop(cropPointer.rect,name,(event.clientX-cropPointer.x)/g.width,(event.clientY-cropPointer.y)/g.height);
      encodeCrop(cropRect);placeCrop();
    });
    handle.addEventListener('lostpointercapture',()=>{
      handle.classList.remove('dragging');
      if(cropPointer && cropPointer.name===name){cropPointer=null;commitCropChange();}
    });
    handle.addEventListener('pointercancel',()=>{
      if(cropPointer && cropPointer.name===name){
        cropRect={...cropPointer.rect};
        for(const key of ['crop_manual','crop_x','crop_y','crop_w','crop_h'])field(key).value=String(cropPointer.settings[key]);
        cropPointer=null;placeCrop();savedState();
      }
    });
    handle.addEventListener('keydown',event=>{
      if(!cropMode||!cropRect||!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(event.key))return;
      const g=pictureGeometry();if(!g)return;
      event.preventDefault();const step=event.shiftKey?20:4;
      const dx=event.key==='ArrowLeft'?-step/g.width:event.key==='ArrowRight'?step/g.width:0;
      const dy=event.key==='ArrowUp'?-step/g.height:event.key==='ArrowDown'?step/g.height:0;
      cropRect=resizeCrop(cropRect,name,dx,dy);placeCrop();commitCropChange();
    });
  });
  $('editor-crop-toggle').addEventListener('click',()=>toggleCropMode());
  $('editor-crop-reset').addEventListener('click',resetCrop);
  function changeZoom(next){
    zoom=Math.max(1,Math.min(3,next));if(zoom===1){panX=0;panY=0;}
    clampPan();renderZoom();
  }
  function clampPan(){
    const maxX=(holder.clientWidth*(zoom-1))/2, maxY=(holder.clientHeight*(zoom-1))/2;
    panX=Math.max(-maxX,Math.min(maxX,panX));panY=Math.max(-maxY,Math.min(maxY,panY));
  }
  function renderZoom(){
    imageStage.style.transform=`translate3d(${panX}px,${panY}px,0) scale(${zoom})`;
    imageStage.classList.toggle('zoomed',zoom>1);
    $('editor-zoom-level').textContent=zoom===1?'Fit':Math.round(zoom*100)+'%';
    $('editor-zoom-out').disabled=zoom===1;
    $('editor-zoom-in').disabled=zoom===3;
  }
  async function save(){
    try{const response=await send('save',recipe());const result=await response.json();
      revision=result.version;root.dataset.revision=String(revision);saved=recipe();savedState();status('Adjustments saved. Original photograph unchanged.');
    }catch(error){status('Save failed: '+error.message,true);}
  }
  function exportSettingsValid(requireCopyName=false){
    for(const key of ['width','height','format'])if(!field(key).reportValidity())return false;
    if(requireCopyName&&!field('copy_name').reportValidity())return false;
    const width=Number(field('width').value),height=Number(field('height').value);
    if(width<0||height<0||(width===0&&height===0)||width>2500||height>2500||width*height>2500000){
      status('Specify an image no larger than 2.5 megapixels and 2500 pixels per side.',true);return false;
    }
    return true;
  }
  async function exportCopy(){
    if(!exportSettingsValid())return;
    const button=$('editor-export');button.disabled=true;status('Preparing your edited download…');
    try{const response=await send('export',recipe());const blob=await response.blob();
      const url=URL.createObjectURL(blob);const link=document.createElement('a');
      link.href=url;link.download=`photo-${photoId}-edited.${field('format').value}`;
      document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),30000);
      status('Edited copy downloaded. Original preserved.');
    }catch(error){status('Export failed: '+error.message,true);}finally{button.disabled=false;}
  }
  async function saveAsCopy(){
    if(!exportSettingsValid(true))return;
    const button=$('editor-save-copy');button.disabled=true;status('Saving edited photograph to your library…');
    try{const response=await send('save_copy',recipe());const result=await response.json();
      status('New photograph added to the same folder. Original preserved.');
      const link=document.createElement('a');link.href=`editor.php?id=${encodeURIComponent(String(result.id))}`;
      link.className='studio-copy-success';link.textContent='Open new copy: '+result.name;message.append(link);
    }catch(error){status('Save as copy failed: '+error.message,true);}finally{button.disabled=false;}
  }
  function readPresets(){
    try {
      const raw=JSON.parse(safeStorageRead()||'[]');
      if(!Array.isArray(raw))return [];
      return raw.filter(x=>x&&typeof x.name==='string'&&x.name.length<=32&&x.recipe&&typeof x.recipe==='object').slice(0,10);
    }catch{return [];}
  }
  let presets=readPresets();
  function populatePresets(){
    const select=$('editor-preset-select');const prior=select.value;
    select.replaceChildren(new Option('Choose a preset',''));
    for(const item of presets)select.add(new Option(item.name,item.name));
    select.value=presets.some(p=>p.name===prior)?prior:'';
    $('editor-apply-preset').disabled=!select.value;
    $('editor-remove-preset').disabled=!select.value;
  }
  for(const el of inputs){
    el.addEventListener(el.type==='range'?'input':'change',()=>{
      if(el.name==='crop'){
        field('crop_manual').value='0';cropRect=null;
        for(const [key,value] of Object.entries({crop_x:0,crop_y:0,crop_w:1000,crop_h:1000}))field(key).value=String(value);
      }
      updateLabels();recordEdit(el.name);
    });
    if(el.type==='range')el.addEventListener('change',()=>{lastEditKey='';});
  }
  field('quality').addEventListener('input',updateLabels);
  field('format').addEventListener('change',updateLabels);
  compare.addEventListener('change',()=>{updateCompareUI();queuePreview();});
  comparePosition.addEventListener('input',updateCompareSplit);
  $('editor-undo').addEventListener('click',()=>historyStep('undo'));
  $('editor-redo').addEventListener('click',()=>historyStep('redo'));
  document.addEventListener('keydown',event=>{
    const target=event.target;
    if(!event.ctrlKey&&!event.metaKey)return;
    if(target?.matches?.('input,select,textarea,[contenteditable]'))return;
    if(event.key.toLowerCase()==='z'){event.preventDefault();historyStep(event.shiftKey?'redo':'undo');}
    else if(event.key.toLowerCase()==='y'){event.preventDefault();historyStep('redo');}
  });
  $('editor-zoom-out').addEventListener('click',()=>changeZoom(zoom===3?2:zoom===2?1.5:1));
  $('editor-zoom-in').addEventListener('click',()=>changeZoom(zoom===1?1.5:zoom===1.5?2:3));
  $('editor-zoom-fit').addEventListener('click',()=>changeZoom(1));
  imageStage.addEventListener('pointerdown',event=>{
    if(cropMode||event.button!==0||zoom===1)return;
    pointer={id:event.pointerId,x:event.clientX,y:event.clientY,panX,panY};
    imageStage.setPointerCapture(event.pointerId);
  });
  imageStage.addEventListener('pointermove',event=>{
    if(!pointer||pointer.id!==event.pointerId)return;
    panX=pointer.panX+event.clientX-pointer.x;panY=pointer.panY+event.clientY-pointer.y;
    clampPan();renderZoom();
  });
  imageStage.addEventListener('lostpointercapture',()=>{pointer=null;});
  imageStage.addEventListener('pointercancel',()=>{pointer=null;});
  window.addEventListener('resize',()=>{clampPan();renderZoom();placeCrop();});
  $('editor-save').addEventListener('click',save);
  $('editor-export').addEventListener('click',exportCopy);
  $('editor-save-copy').addEventListener('click',saveAsCopy);
  $('editor-reset').addEventListener('click',()=>{
    if(cropMode)toggleCropMode(false);
    for(const k of recipeFields)field(k).value=String(baseline[k]);
    recordEdit('reset');updateLabels();status('Sliders reset. Save adjustments to persist the reset.');
  });
  $('editor-preset-select').addEventListener('change',populatePresets);
  $('editor-store-preset').addEventListener('click',()=>{
    const name=$('editor-preset-name').value.trim();
    if(!name||name.length>32){status('Enter a preset name between 1 and 32 characters.',true);$('editor-preset-name').focus();return;}
    if(presets.some(p=>p.name.toLowerCase()===name.toLowerCase())){status('A preset with that name already exists. Delete it first to replace it.',true);return;}
    if(presets.length>=10){status('A maximum of 10 presets can be saved in this browser.',true);return;}
    const next=[...presets,{name,recipe:recipe()}];
    if(!safeStorageWrite(JSON.stringify(next))){status('Browser storage is unavailable. The preset was not saved.',true);return;}
    presets=next;populatePresets();$('editor-preset-select').value=name;populatePresets();$('editor-preset-name').value='';
    status('Preset saved in this browser: '+name);
  });
  $('editor-apply-preset').addEventListener('click',()=>{
    const selected=presets.find(p=>p.name===$('editor-preset-select').value);if(!selected)return;
    for(const k of recipeFields)if(Object.prototype.hasOwnProperty.call(selected.recipe,k))field(k).value=String(selected.recipe[k]);
    updateLabels();cropRect=null;recordEdit('preset');status('Applied preset: '+selected.name);
  });
  $('editor-remove-preset').addEventListener('click',()=>{
    const name=$('editor-preset-select').value;if(!name)return;
    const next=presets.filter(p=>p.name!==name);
    if(!safeStorageWrite(JSON.stringify(next))){status('Could not update browser preset storage.',true);return;}
    presets=next;populatePresets();status('Preset deleted: '+name);
  });
  const exportJump=$('editor-top-export');
  if(exportJump)exportJump.addEventListener('click',()=>{
    $('panel-export').scrollIntoView({behavior:'auto',block:'center'});
    field('width').focus({preventScroll:true});
  });
  // Use the same logical panel selection in the rail and the inspector tabs.
  const panelNavigation=document.querySelectorAll('.studio-tool[data-jump],.studio-workspace-tab[data-jump]');
  function markActivePanel(panelId){
    panelNavigation.forEach(el=>{
      const active=el.dataset.jump===panelId;
      el.classList.toggle('active',active);
      if(active)el.setAttribute('aria-current','true');
      else el.removeAttribute('aria-current');
    });
  }
  document.querySelectorAll('.studio-section').forEach(section=>{
    section.addEventListener('toggle',()=>{
      if(!section.open)return;
      document.querySelectorAll('.studio-section').forEach(other=>{
        if(other!==section)other.open=false;
      });
      markActivePanel(section.id);
    });
  });
  panelNavigation.forEach(button=>{
    button.addEventListener('click',()=>{
      const target=$(button.dataset.jump);if(!target)return;
      if(target.tagName==='DETAILS'){
        document.querySelectorAll('.studio-section').forEach(panel=>{panel.open=panel===target;});
      }
      markActivePanel(target.id);
      // Scroll just the inspector on desktop; scrollIntoView would also move the
      // outer document and hide the fixed editing header behind the browser bar.
      const inspector=target.closest('.studio-inspector');
      if(inspector && window.matchMedia('(min-width:1001px)').matches){
        const pinned=inspector.querySelector('.studio-inspector-sticky')?.getBoundingClientRect().height||0;
        inspector.scrollTop+=target.getBoundingClientRect().top-inspector.getBoundingClientRect().top-pinned;
      }else target.scrollIntoView({behavior:'auto',block:'nearest'});
      if(target.tagName==='DETAILS')target.querySelector('summary')?.focus({preventScroll:true});
      else target.querySelector('input,select')?.focus({preventScroll:true});
    });
  });
  // One HSL family at a time keeps the color mixer compact and visually scannable.
  const colorButtons=[...document.querySelectorAll('.studio-color-family-tab')];
  const colorGroups=[...document.querySelectorAll('.hsl-color-group[data-hsl-group]')];
  function showColorFamily(color){
    for(const group of colorGroups){
      const selected=group.dataset.hslGroup===color;
      group.hidden=!selected;
      group.open=selected;
    }
    for(const button of colorButtons){
      button.setAttribute('aria-pressed',String(button.dataset.hslSelect===color));
    }
  }
  for(const button of colorButtons){
    button.addEventListener('click',()=>showColorFamily(button.dataset.hslSelect));
  }
  if(colorButtons.length)showColorFamily('red');
  window.addEventListener('pagehide',()=>{
    if(controller)controller.abort();if(imageUrl)URL.revokeObjectURL(imageUrl);if(beforeUrl)URL.revokeObjectURL(beforeUrl);
  });
  populatePresets();loadForm(saved);changeZoom(1);updateCompareUI();
})();
