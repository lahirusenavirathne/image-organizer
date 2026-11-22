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
  const baseline = {rotate:0,crop:'original',exposure:0,contrast:0,highlights:0,shadows:0,saturation:0,warmth:0,sharpness:0};
  const recipeFields = Object.keys(baseline);
  const toneFields = ['exposure','contrast','highlights','shadows','saturation','warmth','sharpness'];
  const inputs = recipeFields.map(name => form.elements.namedItem(name));
  const field = name => form.elements.namedItem(name);
  let timer = null, controller = null, imageUrl = null, beforeUrl = null, seq = 0;
  let beforeGeometry = '', zoom = 1, panX = 0, panY = 0, pointer = null;
  let undoStack = [], redoStack = [], currentSnapshot = '', lastEditKey = '', lastEditAt = 0;
  const presetKey = 'glpm-photo-editor-presets-v1';
  const status = (text, error = false) => { message.textContent = text; message.classList.toggle('error', error); };
  const safeStorageRead = () => { try { return localStorage.getItem(presetKey); } catch { return null; } };
  const safeStorageWrite = value => { try { localStorage.setItem(presetKey, value); return true; } catch { return false; } };
  const normalize = values => ({ ...baseline, ...Object.fromEntries(recipeFields.filter(k => values && Object.prototype.hasOwnProperty.call(values,k)).map(k => [k,values[k]])) });
  function recipe() {
    const r = { ...baseline, rotate:Number(field('rotate').value), crop:field('crop').value };
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
  function updateLabels() {
    for (const key of toneFields) {
      const input=field(key);$( 'edit-'+key+'-value').textContent=String(input.value);paintRange(input);
    }
    $('editor-quality-label').textContent=field('quality').value+'%';
    $('editor-quality').disabled=field('format').value==='png';
    $('editor-quality-hint').textContent=field('format').value==='png' ? 'PNG is lossless; the quality control is not used.' : 'Higher quality creates larger files. 80–90 is a useful web starting point.';
  }
  function updateUndoButtons() {$('editor-undo').disabled=!undoStack.length;$('editor-redo').disabled=!redoStack.length;}
  function loadForm(values, preserveHistory = false) {
    const normalized=normalize(values);
    for (const key of recipeFields) field(key).value=String(normalized[key]);
    if (!preserveHistory) {undoStack=[];redoStack=[];currentSnapshot=serial(normalized);lastEditKey='';updateUndoButtons();}
    updateLabels();savedState();queuePreview();
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
    const geometry=settings.crop+'|'+settings.rotate;
    try {
      const editedResponse=await send('preview',settings,controller.signal);
      const editedBlob=await editedResponse.blob();
      if(local!==seq)return;
      let priorBlob=null;
      if(compare.checked && (geometry!==beforeGeometry || !beforeUrl)) {
        const beforeResponse=await send('preview_before',settings,controller.signal);
        priorBlob=await beforeResponse.blob();
      }
      if(local!==seq)return;
      const newUrl=URL.createObjectURL(editedBlob),oldUrl=imageUrl;
      imageUrl=newUrl;picture.onload=()=>{if(oldUrl)URL.revokeObjectURL(oldUrl);};picture.src=newUrl;
      if(priorBlob) {
        const oldBefore=beforeUrl;beforeUrl=URL.createObjectURL(priorBlob);
        original.onload=()=>{if(oldBefore)URL.revokeObjectURL(oldBefore);};original.src=beforeUrl;
        beforeGeometry=geometry;
      }
      updateCompareUI();loading.hidden=true;
      if(previewHelp)previewHelp.textContent=compare.checked?'Drag the comparison slider to see original tones versus edited tones. Crop and rotation match.':'Showing adjusted preview · Original file preserved.';
    } catch(error) {
      if(error.name==='AbortError'||local!==seq)return;
      loading.hidden=true;status('Preview error: '+error.message,true);
    }
  }
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
    el.addEventListener(el.type==='range'?'input':'change',()=>{updateLabels();recordEdit(el.name);});
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
    if(event.button!==0||zoom===1)return;
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
  window.addEventListener('resize',()=>{clampPan();renderZoom();});
  $('editor-save').addEventListener('click',save);
  $('editor-export').addEventListener('click',exportCopy);
  $('editor-save-copy').addEventListener('click',saveAsCopy);
  $('editor-reset').addEventListener('click',()=>{
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
    updateLabels();recordEdit('preset');status('Applied preset: '+selected.name);
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
  document.querySelectorAll('.studio-tool[data-jump]').forEach(button=>{
    button.addEventListener('click',()=>{
      const target=$(button.dataset.jump);if(!target)return;
      if(target.tagName==='DETAILS')target.open=true;
      document.querySelectorAll('.studio-tool').forEach(el=>{el.classList.toggle('active',el===button);el.setAttribute('aria-current',el===button?'true':'false');});
      target.scrollIntoView({behavior:'auto',block:'nearest'});
      if(target.tagName==='DETAILS')target.querySelector('summary')?.focus({preventScroll:true});
      else target.querySelector('input,select')?.focus({preventScroll:true});
    });
  });
  window.addEventListener('pagehide',()=>{
    if(controller)controller.abort();if(imageUrl)URL.revokeObjectURL(imageUrl);if(beforeUrl)URL.revokeObjectURL(beforeUrl);
  });
  populatePresets();loadForm(saved);changeZoom(1);updateCompareUI();
})();
