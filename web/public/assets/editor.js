'use strict';
(() => {
  const root = document.getElementById('photo-editor');
  if (!root) return;
  const form = document.getElementById('editor-form');
  const picture = document.getElementById('editor-preview');
  const message = document.getElementById('editor-status');
  const loading = document.getElementById('editor-loading');
  const before = document.getElementById('editor-before');
  const saveState = document.getElementById('editor-save-state');
  const previewHelp = document.getElementById('editor-preview-help');
  const photoId = Number(root.dataset.photoId);
  const csrf = document.querySelector('meta[name="csrf-token"]')?.content || '';
  let revision = Number(root.dataset.revision);
  let saved;
  try { saved = JSON.parse(root.dataset.recipe || '{}'); }
  catch { saved = {}; }
  const baseline = {rotate:0,crop:'original',exposure:0,contrast:0,highlights:0,shadows:0,saturation:0,warmth:0,sharpness:0};
  let timer = null, controller = null, imageUrl = null, seq = 0;
  const inputs = [...form.querySelectorAll('[name]')];
  const field = name => form.elements.namedItem(name);
  const status = (text, error = false) => { message.textContent = text; message.classList.toggle('error', error); };
  const savedState = (dirty, text = dirty ? 'Unsaved changes' : 'All changes saved') => {
    if (saveState) { saveState.dataset.dirty = String(dirty); saveState.lastChild.textContent = ' ' + text; }
  };
  function paintRange(el) {
    if(el.type !== 'range') return;
    const min=Number(el.min),max=Number(el.max),value=Number(el.value);
    const percent=max>min ? Math.max(0, Math.min(100, (value-min)*100/(max-min))) : 0;
    el.style.setProperty('--slider-pct', percent+'%');
  }
  function recipe() {
    const r = { ...baseline, rotate:Number(field('rotate').value), crop:field('crop').value };
    for (const key of ['exposure','contrast','highlights','shadows','saturation','warmth','sharpness'])
      r[key] = Number(field(key).value);
    return r;
  }
  function updateLabels() {
    for (const key of ['exposure','contrast','highlights','shadows','saturation','warmth','sharpness'])
      {
        const input=field(key);
        document.getElementById('edit-'+key+'-value').textContent=String(input.value);
        paintRange(input);
      }
  }
  function loadForm(values) {
    const current={...baseline,...values};
    for(const key of Object.keys(baseline))field(key).value=String(current[key]);
    updateLabels();queuePreview();savedState(false);
  }
  async function send(action, params, abortSignal=null) {
    const data = new FormData();data.set('action', action);data.set('id', String(photoId));
    data.set('recipe', JSON.stringify(params));
    data.set('csrf', csrf);
    if(action==='save')data.set('version',String(revision));
    if(action==='export'||action==='save_copy'){
      data.set('width',field('width').value);data.set('height',field('height').value);
      data.set('format',field('format').value);
      if(action==='save_copy')data.set('copy_name',field('copy_name').value.trim());
    }
    const res=await fetch('editor_action.php',{method:'POST',body:data,credentials:'same-origin',signal:abortSignal,cache:'no-store'});
    if(!res.ok){const error=await res.json().catch(()=>null);throw new Error(error?.error||`Server returned HTTP ${res.status}`);}
    return res;
  }
  function queuePreview(){clearTimeout(timer);timer=setTimeout(refresh,420);}
  async function refresh() {
    if(controller) controller.abort();
    controller=new AbortController();const local=++seq;
    loading.hidden=false;
    try {
      const r=before.checked?baseline:recipe();
      const res=await send('preview',r,controller.signal);
      const blob=await res.blob();
      if(local!==seq)return;
      const next=URL.createObjectURL(blob),old=imageUrl;
      imageUrl=next;picture.onload=()=>{if(old)URL.revokeObjectURL(old);};
      picture.src=next;loading.hidden=true;
      if(previewHelp)previewHelp.textContent=before.checked?'Showing the unedited original. Turn off Show original to compare your adjustments.':'Showing edited preview · Original file preserved';
    } catch(error) {
      if(error.name==='AbortError')return;
      loading.hidden=true;status('Preview error: '+error.message,true);
    }
  }
  async function save(){
    try {const res=await send('save',recipe());const data=await res.json();
      revision=data.version;root.dataset.revision=String(revision);status('Adjustments saved. Original photograph unchanged.');savedState(false);
    } catch(error){status('Save failed: '+error.message,true);}
  }
  function exportSettingsValid(requireCopyName = false) {
    // Downloading a file must not depend on the unrelated library-copy filename.
    for(const key of ['width','height','format'])if(!field(key).reportValidity())return false;
    if(requireCopyName && !field('copy_name').reportValidity())return false;
    const width=Number(field('width').value),height=Number(field('height').value);
    if(width<0||height<0||(width===0&&height===0)||width>2500||height>2500||width*height>2500000){
      status('Specify an image no larger than 2.5 megapixels and 2500 pixels per side.',true);return false;
    }
    return true;
  }
  async function exportCopy() {
    if(!exportSettingsValid())return;
    const button=document.getElementById('editor-export');button.disabled=true;
    status('Preparing your new edited file…');
    try{
      const res=await send('export',recipe());const blob=await res.blob();
      const url=URL.createObjectURL(blob);const a=document.createElement('a');
      a.href=url;a.download=`photo-${photoId}-edited.${field('format').value}`;
      a.style.display='none';document.body.append(a);a.click();a.remove();
      setTimeout(()=>URL.revokeObjectURL(url),30000);
      status('Edited copy downloaded. The original stays unchanged.');
    }catch(error){status('Export failed: '+error.message,true);}
    finally{button.disabled=false;}
  }
  async function saveAsCopy() {
    if(!exportSettingsValid(true))return;
    const button=document.getElementById('editor-save-copy');button.disabled=true;
    status('Saving edited photograph to your library…');
    try {
      const res=await send('save_copy',recipe());const result=await res.json();
      status('Saved a new edited photograph in the original folder. Your original is unchanged.');
      const link=document.createElement('a');
      link.href=`editor.php?id=${encodeURIComponent(String(result.id))}`;
      link.className='studio-copy-success';link.textContent='Open new copy: '+result.name;
      message.append(link);
    }catch(error){status('Save as copy failed: '+error.message,true);}
    finally{button.disabled=false;}
  }
  for(const el of inputs){
    if(!Object.prototype.hasOwnProperty.call(baseline,el.name))continue;
    el.addEventListener(el.type==='range'?'input':'change',()=>{updateLabels();savedState(true);if(!before.checked)queuePreview();});
  }
  before.addEventListener('change',queuePreview);
  document.getElementById('editor-save').addEventListener('click',save);
  document.getElementById('editor-export').addEventListener('click',exportCopy);
  document.getElementById('editor-save-copy').addEventListener('click',saveAsCopy);
  document.getElementById('editor-reset').addEventListener('click',()=>{before.checked=false;loadForm(baseline);savedState(true);status('Sliders reset. Click Save adjustments to update the saved recipe.');});
  const exportJump=document.getElementById('editor-top-export');
  if(exportJump)exportJump.addEventListener('click',()=>{
    document.getElementById('panel-export').scrollIntoView({behavior:'auto',block:'center'});
    field('width').focus({preventScroll:true});
  });
  document.querySelectorAll('.studio-tool[data-jump]').forEach(button=>{
    button.addEventListener('click',()=>{
      const target=document.getElementById(button.dataset.jump);
      if(!target)return;
      if(target.tagName==='DETAILS')target.open=true;
      document.querySelectorAll('.studio-tool').forEach(el=>{el.classList.toggle('active',el===button);el.setAttribute('aria-current',el===button?'true':'false');});
      target.scrollIntoView({behavior:'auto',block:'nearest'});
      if(target.tagName==='DETAILS')target.querySelector('summary')?.focus({preventScroll:true});
      else target.querySelector('input,select')?.focus({preventScroll:true});
    });
  });
  window.addEventListener('pagehide',()=>{if(controller)controller.abort();if(imageUrl)URL.revokeObjectURL(imageUrl);});
  loadForm(saved);
})();
