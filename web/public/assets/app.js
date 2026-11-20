'use strict';
const $ = (id) => document.getElementById(id);
const csrf = document.querySelector('meta[name="csrf-token"]').content;
const state = {page: 1, pages: 1, view: 'all', photos: [], selected: new Set(), current: null, total: 0, matches: null, busy: false};
const escapeHtml = (value) => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const sizeStr = (n) => (Number(n) / 1024 / 1024).toFixed(2) + ' MB';
const fmt = (p) => [p.location, p.attraction].filter(Boolean).join(' · ') || 'Location unknown';
function notice(text, isError=false) {
  const el=$('notice');el.hidden=false;el.className='notice'+(isError?' error':'');el.textContent=text;
}
async function request(action, data, method='POST') {
  const options={method, credentials:'same-origin',headers:{'X-CSRF-Token':csrf}};
  let url='api.php?action='+encodeURIComponent(action);
  if(method==='GET')url+='&'+new URLSearchParams(data);
  else if(data instanceof FormData)options.body=data;
  else {const fd=new FormData();for(const [key,value] of Object.entries(data||{}))fd.set(key,value);options.body=fd;}
  let result;try{const response=await fetch(url,options);result=await response.json();if(!response.ok||result.error)throw new Error(result.error||'Request failed');}
  catch(err){if(err instanceof SyntaxError)throw new Error('Unexpected server response. Check HTTPS, PHP and hosting error logs.');throw err;}
  return result;
}
function navTo(view) {
  state.view=view;state.page=1;state.matches=null;
  document.querySelectorAll('[data-view]').forEach(button=>button.classList.toggle('active',button.dataset.view===view));
  const titles={all:'Photo library',locations:'Locations',activities:'Activities',sources:'Sources',review:'Review AI tags',similar:'Similar photographs',exports:'Export studio'};
  $('view-title').textContent=titles[view];
  $('view-subtitle').textContent=({similar:'Compare images using exact hashes and visual fingerprints.',review:'Inspect and approve suggested AI classifications.',exports:'Prepare website and social media images with precise dimensions.'})[view]||'Browse, filter and manage your travel photography.';
  $('filters').hidden=!['locations','activities','sources'].includes(view);
  if(view==='exports'){openExport();}
  if(view==='similar' && state.current){showSimilar(state.current);}
  else if(view==='similar') { $('gallery').replaceChildren();$('empty').hidden=false;$('empty').querySelector('h2').textContent='Select a photograph first';$('empty').querySelector('p').textContent='Return to All photos and choose Find similar photos from an image.'; }
  else load();
  $('sidebar').classList.remove('open');$('menu-toggle').setAttribute('aria-expanded','false');
}
async function load() {
  if(state.busy)return;state.busy=true;$('gallery').setAttribute('aria-busy','true');
  const q={page:state.page,q:$('search').value.trim(),location:$('filter-location').value,activity:$('filter-activity').value.trim(),rights:$('filter-rights').value,view:state.view};
  try {
    const result=await request('list',q,'GET');state.photos=result.photos;state.page=result.page;state.pages=result.pages;state.total=result.total;
    const select=$('filter-location');const prior=select.value;select.replaceChildren(new Option('All locations',''));
    for(const loc of result.locations)select.add(new Option(loc,loc));select.value=prior;
    renderPhotos(state.photos);$('photo-count').textContent=result.total.toLocaleString()+' photos indexed';
    $('page-indicator').textContent=`Page ${state.page} of ${state.pages}`;$('prev-page').disabled=state.page<=1;$('next-page').disabled=state.page>=state.pages;
  } catch(e){notice(e.message,true);}finally{state.busy=false;$('gallery').setAttribute('aria-busy','false');}
}
function renderPhotos(photos, similarity=false) {
  const gallery=$('gallery');gallery.replaceChildren();$('empty').hidden=photos.length>0;
  if(!photos.length){$('empty').querySelector('h2').textContent='No photographs to display';$('empty').querySelector('p').textContent='Try removing filters or uploading photographs.';}
  for(const [i,p] of photos.entries()) {
    const article=document.createElement('article');article.className='photo-card';
    const selected=state.selected.has(Number(p.id));
    const img=document.createElement('img');img.src=`image.php?id=${encodeURIComponent(p.id)}&type=thumb`;img.alt=p.original_name||p.name||'Photo';img.width=400;img.height=300;img.loading=i===0?'eager':'lazy';if(i===0)img.fetchPriority='high';
    const tile=document.createElement('button');tile.type='button';tile.className='photo-open';tile.setAttribute('aria-label','Open '+(p.original_name||p.name));tile.append(img);tile.addEventListener('click',()=>inspectPhoto(p));
    const select=document.createElement('input');select.type='checkbox';select.checked=selected;select.setAttribute('aria-label','Select '+(p.original_name||p.name));select.addEventListener('change',()=>{if(select.checked)state.selected.add(Number(p.id));else state.selected.delete(Number(p.id));updateSelected();article.classList.toggle('is-selected',select.checked);});
    const check=document.createElement('label');check.className='photo-check';check.append(select);
    const information=document.createElement('div');information.className='photo-meta';
    const name=document.createElement('div');name.className='photo-name';name.textContent=p.original_name||p.name||'Photo';name.title=name.textContent;
    const location=document.createElement('div');location.className='photo-location';location.textContent=fmt(p);
    information.append(name,location);
    if(similarity && p.type){const badge=document.createElement('span');badge.className='similar-tag';badge.textContent=p.type+(Number.isFinite(Number(p.distance))?' · d='+p.distance:'');information.append(badge);}
    article.classList.toggle('is-selected',selected);article.append(tile,check,information);gallery.append(article);
  }
  updateSelected();
}
function updateSelected(){$('selection-count').textContent=state.selected.size+' selected';}
function inspectPhoto(p) {
  state.current=Number(p.id);
  $('inspector').hidden=false;$('detail-image').src=`image.php?id=${p.id}&type=thumb`;$('detail-image').alt=p.original_name||p.name;
  $('detail-name').textContent=p.original_name||p.name||'Photograph';
  $('detail-size').textContent=`${p.width||'?'} × ${p.height||'?'} px · ${p.file_size?sizeStr(p.file_size):''}`;
  const form=$('details-form');
  for(const key of ['location','attraction','activities','source_folder','source_url','photographer','copyright_text','license','rights_status'])if(form.elements[key])form.elements[key].value=p[key]|| (key==='rights_status'?'Unknown':'');
  $('ai-note').textContent=`AI: ${p.ai_status||'not analyzed'}${p.ai_note?' — '+p.ai_note:''}`;
}
async function showSimilar(id) {
  navToShallow('similar');
  try{
    const data=await request('similar',{id},'GET');state.matches=data.matches;
    renderPhotos(data.matches.map(m=>({...m,original_name:m.name})),true);
    $('photo-count').textContent=data.matches.length+' candidate matches';$('page-indicator').textContent='Review each result';$('prev-page').disabled=true;$('next-page').disabled=true;
    if(!data.matches.length)notice('No close matches found in the indexed photo library.');
  }catch(e){notice(e.message,true);}
}
function navToShallow(view){state.view=view;document.querySelectorAll('[data-view]').forEach(b=>b.classList.toggle('active',b.dataset.view===view));$('view-title').textContent='Visually similar photographs';$('view-subtitle').textContent='Matches are suggestions, not proof of identical locations.';}
async function saveDetails(event){event.preventDefault();if(!state.current)return;const fd=new FormData($('details-form'));fd.set('id',String(state.current));
  try{await request('save',fd);notice('Metadata saved. Review complete; originals were not modified.');await load();}
  catch(e){notice(e.message,true);}
}
async function uploadFiles(fileList) {
  const files=[...fileList];if(!files.length)return;
  let ok=0;let errors=[];
  for(const [i,file] of files.entries()) {
    notice(`Uploading ${i+1} of ${files.length}: ${file.name}`);
    if(!['image/jpeg','image/png','image/webp'].includes(file.type) || file.size>25*1024*1024){errors.push(file.name+' (unsupported or >25MB)');continue;}
    const fd=new FormData();fd.append('photo',file,file.name);
    try{await request('upload',fd);ok++;}catch(e){errors.push(file.name+': '+e.message);}
  }
  state.page=1;await load();notice(`Uploaded ${ok} of ${files.length}.${errors.length?' Problems: '+errors.slice(0,3).join('; '):''}`,errors.length>0);
  $('upload').value='';
}
function selectedIds(){return [...state.selected];}
function openExport(){const ids=selectedIds();if(!ids.length){notice('Select photos in the gallery to export.');return;}if(ids.length>12){notice('Select up to 12 photos per export to protect shared-hosting memory and processing time.',true);return;}$('export-ids').value=ids.join(',');$('export-dialog').showModal();}
function updatePreset(){const value=$('preset').value;if(value!=='custom'){const[w,h]=value.split('x');$('export-width').value=w;$('export-height').value=h;}const custom=value==='custom';$('export-width').readOnly=!custom;$('export-height').readOnly=!custom;}
function throttleInput(callback,delay=280){let timeout;return()=>{clearTimeout(timeout);timeout=setTimeout(callback,delay);};}
function init(){
  document.querySelectorAll('[data-view]').forEach(b=>b.addEventListener('click',()=>navTo(b.dataset.view)));
  $('search').addEventListener('input',throttleInput(()=>{state.page=1;load();}));
  $('filter-location').addEventListener('change',()=>{state.page=1;load();});
  $('filter-activity').addEventListener('input',throttleInput(()=>{state.page=1;load();}));
  $('filter-rights').addEventListener('change',()=>{state.page=1;load();});
  $('filters').addEventListener('reset',()=>setTimeout(()=>{state.page=1;load();},0));
  $('filter-toggle').addEventListener('click',()=>{const el=$('filters');el.hidden=!el.hidden;$('filter-toggle').setAttribute('aria-expanded',String(!el.hidden));});
  $('prev-page').addEventListener('click',()=>{state.page=Math.max(1,state.page-1);load();});
  $('next-page').addEventListener('click',()=>{state.page=Math.min(state.pages,state.page+1);load();});
  $('clear-selection').addEventListener('click',()=>{state.selected.clear();renderPhotos(state.photos);});
  $('select-page').addEventListener('click',()=>{for(const p of state.photos)state.selected.add(Number(p.id));renderPhotos(state.photos);});
  $('upload').addEventListener('change',e=>uploadFiles(e.target.files));
  $('import-sftp').addEventListener('click',async()=>{if(!confirm('Import up to 12 photos from private/incoming on the server? Originals will become part of your managed library.'))return;try{const r=await request('import_inbox',{});notice(`SFTP batch imported: ${r.imported}. ${r.failures.length?'Errors: '+r.failures.join('; '):''}`);await load();}catch(e){notice(e.message,true);}});
  $('inspector-close').addEventListener('click',()=>{$('inspector').hidden=true;});
  $('details-form').addEventListener('submit',saveDetails);
  $('find-similar').addEventListener('click',()=>{if(state.current)showSimilar(state.current);});
  $('view-full').addEventListener('click',()=>{if(!state.current)return;$('full-image').src=`image.php?id=${state.current}&type=original`;$('preview-dialog').showModal();});
  $('open-export').addEventListener('click',openExport);$('preset').addEventListener('change',updatePreset);updatePreset();
  document.querySelectorAll('[data-close]').forEach(b=>b.addEventListener('click',()=>$(b.dataset.close).close()));
  $('menu-toggle').addEventListener('click',()=>{let on=$('sidebar').classList.toggle('open');$('menu-toggle').setAttribute('aria-expanded',String(on));});
  document.addEventListener('keydown',e=>{if(e.key==='Escape'){$('sidebar').classList.remove('open');$('menu-toggle').setAttribute('aria-expanded','false');}});
  $('tag-ai').addEventListener('click',async()=>{
    const ids=selectedIds();if(!ids.length){notice('Select at least one photo for cloud tagging.');return;}if(ids.length>5){notice('For cost and privacy, tag at most five photos per action.',true);return;}
    if(!confirm(`Send ${ids.length} resized photos to OpenAI for optional image classification? This may incur API charges and may include people. No request will be sent without confirmation.`))return;
    let done=0,errors=[];for(const id of ids){try{await request('cloud_ai',{id,confirm:'yes'});done++;}catch(e){errors.push('Photo '+id+': '+e.message);}}
    notice(`Cloud tagging complete: ${done}/${ids.length}. ${errors.join('; ')}`,errors.length>0);await load();
  });
  load();
}
init();
