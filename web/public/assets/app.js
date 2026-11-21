'use strict';
const $=(id)=>document.getElementById(id);
const csrf=document.querySelector('meta[name="csrf-token"]')?.content||'';
const userRole=document.body.dataset.role||'viewer';
const canEdit=userRole!=='viewer';
const isAdmin=userRole==='admin';
const state={view:'drive',folder:null,page:1,pages:1,photos:[],folders:[],folderOptions:[],selected:new Set(),current:null,total:0,sort:'newest',listView:false,busy:false,manager:null};
const escapeHtml=(value)=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const sizeStr=n=>`${(Number(n||0)/1024/1024).toFixed(2)} MB`;
const fmt=p=>[p.location,p.attraction].filter(Boolean).join(' · ')||'Location unknown';
const idList=()=>[...state.selected];
function notice(text,isError=false){const el=$('notice');el.hidden=false;el.className='notice'+(isError?' error':'');el.textContent=text;}
function clearNotice(){$('notice').hidden=true;}
async function call(url,action,data={},method='POST'){
  const opts={method,credentials:'same-origin',headers:{'X-CSRF-Token':csrf}};
  let endpoint=url+'?action='+encodeURIComponent(action);
  if(method==='GET')endpoint+='&'+new URLSearchParams(data);
  else if(data instanceof FormData)opts.body=data;
  else{const fd=new FormData();for(const [key,value] of Object.entries(data))fd.set(key,value);opts.body=fd;}
  let response,body;
  try{response=await fetch(endpoint,opts);body=await response.json();}
  catch{throw new Error('Unexpected server response. Check DreamHost PHP logs and your network.');}
  if(!response.ok||body.error)throw new Error(body.error||`Request failed (${response.status})`);
  return body;
}
const request=(action,data={},method='POST')=>call('api.php',action,data,method);
const drive=(action,data={},method='POST')=>call('drive_api.php',action,data,method);
function setCurrentFolder(id){state.folder=id==null?null:Number(id);state.page=1;state.selected.clear();state.current=null;$('inspector').hidden=true;clearNotice();navTo('drive');}
function navTo(view){
  if(view==='trash'&&!canEdit){notice('Trash is available to Editors and Administrators.',true);return;}
  state.view=view;state.page=1;state.selected.clear();
  document.querySelectorAll('[data-view]').forEach(b=>b.classList.toggle('active',b.dataset.view===view));
  const titles={drive:'My Drive',all:'All photos',recent:'Recently added',trash:'Trash',locations:'Locations',activities:'Activities',sources:'Sources',review:'Review AI tags',similar:'Similar photographs',exports:'Export studio'};
  $('view-title').textContent=titles[view]||'Photo library';
  $('view-subtitle').textContent=view==='trash'?'Items can be restored until permanently deleted.':view==='drive'?'Organize photographs into folders, just like a drive.':view==='similar'?'Find potential duplicates and visually similar photos.':'Browse and manage your Sri Lankan travel photographs.';
  $('filters').hidden=!['locations','activities','sources'].includes(view);
  if(view==='exports'){openExport();}
  if(view==='similar'){
    if(state.current)showSimilar(state.current);
    else{$('folder-section').hidden=true;$('gallery').replaceChildren();$('empty').hidden=false;$('empty').querySelector('h2').textContent='Choose a photograph';$('empty').querySelector('p').textContent='Open a photo and choose Find similar photos.';}
  } else load();
  $('sidebar').classList.remove('open');$('menu-toggle').setAttribute('aria-expanded','false');
}
function decorateNav(){
  if(!canEdit){for(const e of document.querySelectorAll('.edit-only,.admin-only,[data-view="trash"]'))e.hidden=true;}
  else if(!isAdmin){for(const e of document.querySelectorAll('.admin-only'))e.hidden=true;}
}
function breadcrumbs(items){
  const el=$('breadcrumbs');el.replaceChildren();el.hidden=state.view!=='drive';
  if(state.view!=='drive')return;
  const root=document.createElement('button');root.type='button';root.textContent='My Drive';root.addEventListener('click',()=>setCurrentFolder(null));el.append(root);
  for(const crumb of items){const span=document.createElement('span');span.textContent=' / ';span.setAttribute('aria-hidden','true');const b=document.createElement('button');b.type='button';b.textContent=crumb.name;b.addEventListener('click',()=>setCurrentFolder(crumb.id));el.append(span,b);}
}
async function load(){
  if(state.busy)return;state.busy=true;$('gallery').setAttribute('aria-busy','true');
  const view=['locations','activities','sources','exports'].includes(state.view)?'all':state.view;
  const q={view,folder:state.folder??'',page:state.page,q:$('search').value.trim(),sort:state.sort,location:$('filter-location').value,activity:$('filter-activity').value.trim(),rights:$('filter-rights').value};
  try{
    const result=await drive('list',q,'GET');state.photos=result.photos;state.folders=result.folders;state.folderOptions=result.folder_options;state.page=result.page;state.pages=result.pages;state.total=result.total;
    const select=$('filter-location'),prior=select.value;select.replaceChildren(new Option('All locations',''));for(const loc of (result.locations||[]))select.add(new Option(loc,loc));select.value=prior;
    breadcrumbs(result.breadcrumbs||[]);renderFolders(state.folders);renderPhotos(state.photos);
    const n=state.total+state.folders.length;
    $('photo-count').textContent=state.view==='trash'?`${n} deleted items`:`${n.toLocaleString()} items`; // photos page total + current folder cards
    $('page-indicator').textContent=`Page ${state.page} of ${state.pages}`;
    $('prev-page').disabled=state.page<=1;$('next-page').disabled=state.page>=state.pages;
    $('new-folder').hidden=!canEdit||state.view!=='drive';
    $('open-export').hidden=!canEdit||state.view==='trash';
    $('tag-ai').hidden=!canEdit||state.view==='trash';
    $('upload').disabled=!canEdit||state.view==='trash';
    $('upload-folder').disabled=!canEdit||state.view==='trash';
    $('move-selected').hidden=!canEdit||state.view==='trash';
    $('copy-selected').hidden=!canEdit||state.view==='trash';
    $('trash-selected').hidden=!canEdit||state.view==='trash';
    $('restore-selected').hidden=!canEdit||state.view!=='trash';
    $('purge-selected').hidden=!isAdmin||state.view!=='trash';
    $('download-selected').hidden=!canEdit||state.view==='trash';
  }catch(e){notice(e.message,true);}finally{state.busy=false;$('gallery').setAttribute('aria-busy','false');}
}
function renderFolders(folders){
  $('folder-section').hidden=folders.length===0;const section=$('folder-grid');section.replaceChildren();
  for(const folder of folders){
    const card=document.createElement('article');card.className='folder-card';
    const open=document.createElement('button');open.type='button';open.className='folder-open';open.innerHTML='<span aria-hidden="true" class="folder-symbol">📁</span>';
    const label=document.createElement('span');label.className='folder-name';label.textContent=folder.name;open.append(label);
    if(state.view==='trash'){open.disabled=true;open.title='Restore the folder before opening it';}
    else open.addEventListener('click',()=>setCurrentFolder(folder.id));
    const controls=document.createElement('div');controls.className='folder-controls';
    if(canEdit){
      if(state.view==='trash'){
        controls.append(actionButton('Restore',()=>folderAction('restore_folder',folder.id,`Restored ${folder.name}`)));
        if(isAdmin)controls.append(actionButton('Delete forever',()=>purgeOne('folder',folder.id),true));
      }else{
        controls.append(actionButton('Rename',()=>manage('rename_folder',{id:folder.id,name:folder.name})));
        controls.append(actionButton('Move',()=>manage('move_folder',{id:folder.id,name:folder.name})));
        controls.append(actionButton('Trash',()=>trashFolder(folder),true));
        controls.append(actionButton('ZIP',()=>downloadFolder(folder.id)));
      }
    }
    card.append(open,controls);section.append(card);
  }
}
function actionButton(text,handler,danger=false){const button=document.createElement('button');button.type='button';button.className='mini-action'+(danger?' danger':'');button.textContent=text;button.addEventListener('click',handler);return button;}
function renderPhotos(photos,similarity=false){
  const gallery=$('gallery');gallery.replaceChildren();gallery.classList.toggle('list-mode',state.listView);
  const empty=photos.length===0&&state.folders.length===0;
  $('empty').hidden=!empty;$('files-heading').hidden=state.view==='trash'||!state.folders.length;
  if(empty){$('empty').querySelector('h2').textContent='No photographs to display';$('empty').querySelector('p').textContent=state.view==='drive'?'Create a folder or upload photographs to this location.':'Try changing your filters or visiting My Drive.';}
  for(const [i,p] of photos.entries()){
    const id=Number(p.id),selected=state.selected.has(id);
    const article=document.createElement('article');article.className='photo-card';article.classList.toggle('is-selected',selected);
    const image=state.view==='trash'?document.createElement('span'):document.createElement('img');if(state.view==='trash'){image.className='trashed-photo';image.textContent='🗑';}else{image.src=`image.php?id=${id}&type=thumb`;image.alt=p.original_name||p.name||'Photograph';image.width=400;image.height=300;image.loading=i===0?'eager':'lazy';if(i===0)image.fetchPriority='high';}
    const open=document.createElement('button');open.type='button';open.className='photo-open';open.setAttribute('aria-label','Open '+(p.original_name||p.name));open.append(image);open.disabled=state.view==='trash';open.addEventListener('click',()=>inspectPhoto(p));
    const checkbox=document.createElement('input');checkbox.type='checkbox';checkbox.checked=selected;checkbox.setAttribute('aria-label','Select '+(p.original_name||p.name));checkbox.addEventListener('change',()=>{if(checkbox.checked)state.selected.add(id);else state.selected.delete(id);article.classList.toggle('is-selected',checkbox.checked);updateSelected();});
    const cWrap=document.createElement('label');cWrap.className='photo-check';cWrap.append(checkbox);
    const information=document.createElement('div');information.className='photo-meta';const name=document.createElement('div');name.className='photo-name';name.textContent=p.original_name||p.name||'Photo';name.title=name.textContent;
    const desc=document.createElement('div');desc.className='photo-location';desc.textContent=state.view==='trash'?'In Trash':fmt(p);information.append(name,desc);
    if(similarity && p.type){const tag=document.createElement('span');tag.className='similar-tag';tag.textContent=p.type+(Number.isFinite(Number(p.distance))?' · d='+p.distance:'');information.append(tag);}
    article.append(open,cWrap,information);gallery.append(article);
  }
  updateSelected();
}
function updateSelected(){const n=state.selected.size;$('selection-count').textContent=`${n} selected`;for(const id of ['move-selected','copy-selected','trash-selected','restore-selected','purge-selected','download-selected','open-export','tag-ai']){const b=$(id);if(b)b.disabled=n===0;}}
function inspectPhoto(p){
  if(state.view==='trash')return;state.current=Number(p.id);
  $('inspector').hidden=false;$('detail-image').src=`image.php?id=${p.id}&type=thumb`;$('detail-image').alt=p.original_name||p.name||'Photo';
  $('detail-name').textContent=p.original_name||p.name||'';
  $('detail-size').textContent=`${p.width||'?'} × ${p.height||'?'} px · ${sizeStr(p.file_size)}`;
  const form=$('details-form');for(const key of ['location','attraction','activities','source_folder','source_url','photographer','copyright_text','license','rights_status'])if(form.elements[key])form.elements[key].value=p[key]||(key==='rights_status'?'Unknown':'');
  $('ai-note').textContent=`AI: ${p.ai_status||'not analyzed'}${p.ai_note?' — '+p.ai_note:''}`;
  for(const el of form.querySelectorAll('input,select,button'))el.disabled=!canEdit;
  $('rename-current').hidden=!canEdit;
}
async function showSimilar(id){
  state.view='similar';state.selected.clear();document.querySelectorAll('[data-view]').forEach(b=>b.classList.toggle('active',b.dataset.view==='similar'));
  $('view-title').textContent='Visually similar photographs';$('folder-section').hidden=true;$('breadcrumbs').hidden=true;
  try{const data=await request('similar',{id},'GET');state.folders=[];renderPhotos(data.matches.map(p=>({...p,original_name:p.name})),true);$('photo-count').textContent=data.matches.length+' candidate matches';$('page-indicator').textContent='Review candidates';$('prev-page').disabled=true;$('next-page').disabled=true;if(!data.matches.length)notice('No close matches found. This feature mainly detects edited or resized copies.');}
  catch(e){notice(e.message,true);}
}
async function saveDetails(e){e.preventDefault();if(!canEdit||!state.current)return;const fd=new FormData($('details-form'));fd.set('id',String(state.current));
  try{await request('save',fd);notice('Photo details updated. The original file is unchanged.');await load();}
  catch(error){notice(error.message,true);}
}
async function uploadFiles(list){
  if(!canEdit || state.view==='trash'){notice('Uploading is not permitted here.',true);return;}
  const files=[...list];if(!files.length)return;
  let count=0;const errors=[];
  for(const [i,file] of files.entries()){
    notice(`Uploading ${i+1} of ${files.length}: ${file.name}`);
    if(!['image/jpeg','image/png','image/webp'].includes(file.type)||file.size>25*1024*1024){errors.push(`${file.name}: unsupported type or over 25 MB`);continue;}
    const fd=new FormData();fd.append('photo',file,file.name);fd.set('folder',String(state.view==='drive'?(state.folder??''):''));
    if(file.webkitRelativePath)fd.set('relative_path',file.webkitRelativePath);
    try{await request('upload',fd);count++;}catch(e){errors.push(`${file.name}: ${e.message}`);}
  }
  state.page=1;state.selected.clear();await load();notice(`Uploaded ${count}/${files.length} photographs.${errors.length?' Errors: '+errors.slice(0,4).join('; '):''}`,errors.length>0);
  $('upload').value='';$('upload-folder').value='';
}
function openExport(){if(!canEdit){notice('Viewers cannot export.',true);return;}const ids=idList();if(!ids.length){notice('Select photographs to export.');return;}if(ids.length>12){notice('Export up to 12 photos per batch.',true);return;}$('export-ids').value=ids.join(',');$('export-dialog').showModal();}
function updatePreset(){const value=$('preset').value;if(value!=='custom'){const[w,h]=value.split('x');$('export-width').value=w;$('export-height').value=h;}const custom=value==='custom';$('export-width').readOnly=!custom;$('export-height').readOnly=!custom;}
function manage(mode,context={}){
  if(!canEdit)return;
  state.manager={mode,context};const needsFolder=['move_photos','copy_photos','move_folder'].includes(mode);
  $('manager-name-row').hidden=needsFolder;$('manager-folder-row').hidden=!needsFolder;
  $('manager-name').required=!needsFolder;$('manager-name').maxLength=mode==='rename_photo'?220:190;
  $('manager-name').value=context.name||'';
  $('manager-title').textContent=({create_folder:'New folder',rename_folder:'Rename folder',rename_photo:'Rename photograph',move_folder:'Move folder',move_photos:'Move selected photographs',copy_photos:'Copy selected photographs'})[mode]||'Manage files';
  $('manager-description').textContent=needsFolder?'Choose a destination. Items are not deleted from their original folder when copying.':'Names do not change the stored original photo bytes.';
  $('manager-submit').textContent=mode==='copy_photos'?'Copy':mode.startsWith('move')?'Move':'Save';
  const select=$('manager-folder');select.replaceChildren(new Option('My Drive (root)',''));
  const byParent=new Map();for(const folder of state.folderOptions){const key=folder.parent_id==null?'root':String(folder.parent_id);if(!byParent.has(key))byParent.set(key,[]);byParent.get(key).push(folder);}
  function build(parent,level=0,seen=new Set()){
    for(const f of (byParent.get(parent)||[])){
      const id=String(f.id);if(seen.has(id)||level>25)continue;
      select.add(new Option('  '.repeat(level+1)+'📁 '+f.name,id));const branch=new Set(seen);branch.add(id);build(id,level+1,branch);
    }
  }build('root');
  select.value=context.destination!=null?String(context.destination):String(state.view==='drive'?(state.folder??''):'');
  $('manager-dialog').showModal();if(!needsFolder)$('manager-name').focus();else select.focus();
}
async function managerSubmit(e){
  e.preventDefault();if(!state.manager)return;
  const{mode,context}=state.manager,data={};
  data.name=$('manager-name').value;data.folder=$('manager-folder').value;data.id=context.id;data.ids=JSON.stringify(idList());
  try{await drive(mode,data);$('manager-dialog').close();state.selected.clear();notice('File operation completed.');await load();}
  catch(error){notice(error.message,true);}
}
async function folderAction(action,id,message){try{await drive(action,{id});notice(message);await load();}catch(e){notice(e.message,true);}}
async function trashFolder(folder){if(!confirm(`Move folder "${folder.name}" and its contents to Trash? You can restore it later.`))return;folderAction('trash_folder',folder.id,`Moved "${folder.name}" to Trash.`);}
async function bulkAction(action,ids,success){
  if(!ids.length){notice('Select photographs first.');return;}
  try{await drive(action,{ids:JSON.stringify(ids)});state.selected.clear();notice(success);await load();}
  catch(e){notice(e.message,true);}
}
async function restoreSelected(){const ids=idList();let ok=0,errors=[];for(const id of ids){try{await drive('restore_photo',{id});ok++;}catch(e){errors.push(`Photo ${id}: ${e.message}`);}}state.selected.clear();await load();notice(`Restored ${ok}/${ids.length}. ${errors.join('; ')}`,errors.length>0);}
async function purgeOne(type,id){
  const phrase=prompt(`Permanently delete this ${type}? This cannot be undone. Type DELETE PERMANENTLY to proceed.`);
  if(phrase!=='DELETE PERMANENTLY')return;
  try{const r=await drive(type==='folder'?'purge_folder':'purge_photo',{id,confirm:phrase});notice(r.cleanup_failed?'Deleted database record but some private files could not be removed. Check hosting logs.':'Permanently deleted.');await load();}catch(e){notice(e.message,true);}
}
async function purgeSelected(){const ids=idList();if(!ids.length)return;const phrase=prompt(`Permanently delete ${ids.length} photographs? Type DELETE PERMANENTLY.`);if(phrase!=='DELETE PERMANENTLY')return;
  let n=0,errors=[];for(const id of ids){try{await drive('purge_photo',{id,confirm:phrase});n++;}catch(e){errors.push(`${id}: ${e.message}`);}}
  state.selected.clear();await load();notice(`Permanently deleted ${n}/${ids.length}. ${errors.join('; ')}`,errors.length>0);
}
function submitDownload(data){const form=document.createElement('form');form.method='post';form.action='download.php';form.hidden=true;for(const[k,v]of Object.entries(data)){const field=document.createElement('input');field.type='hidden';field.name=k;field.value=v;form.append(field);}document.body.append(form);form.submit();setTimeout(()=>form.remove(),5000);}
function downloadFolder(id){submitDownload({csrf,folder:id,mode:'folder'});}
function downloadSelected(){const ids=idList();if(!ids.length){notice('Select photos to download.');return;}if(ids.length>24){notice('For server safety, download up to 24 photographs per ZIP.',true);return;}submitDownload({csrf,ids:JSON.stringify(ids),mode:'selected'});}
function throttleInput(cb,delay=280){let timer;return()=>{clearTimeout(timer);timer=setTimeout(cb,delay);};}
function init(){
  decorateNav();document.querySelectorAll('[data-view]').forEach(b=>b.addEventListener('click',()=>b.dataset.view==='drive'?setCurrentFolder(null):navTo(b.dataset.view)));
  $('search').addEventListener('input',throttleInput(()=>{state.page=1;state.selected.clear();load();}));
  $('filter-location').addEventListener('change',()=>{state.page=1;load();});$('filter-activity').addEventListener('input',throttleInput(()=>{state.page=1;load();}));$('filter-rights').addEventListener('change',()=>{state.page=1;load();});$('filters').addEventListener('reset',()=>setTimeout(()=>{state.page=1;load();},0));
  $('filter-toggle').addEventListener('click',()=>{const e=$('filters');e.hidden=!e.hidden;$('filter-toggle').setAttribute('aria-expanded',String(!e.hidden));});
  $('sort-by').addEventListener('change',()=>{state.sort=$('sort-by').value;state.selected.clear();load();});
  $('view-toggle').addEventListener('click',()=>{state.listView=!state.listView;$('view-toggle').setAttribute('aria-pressed',String(state.listView));$('view-toggle').textContent=state.listView?'Grid view':'List view';$('gallery').classList.toggle('list-mode',state.listView);});
  $('prev-page').addEventListener('click',()=>{state.page=Math.max(1,state.page-1);load();});$('next-page').addEventListener('click',()=>{state.page=Math.min(state.pages,state.page+1);load();});
  $('clear-selection').addEventListener('click',()=>{state.selected.clear();renderPhotos(state.photos);});$('select-page').addEventListener('click',()=>{for(const p of state.photos)state.selected.add(Number(p.id));renderPhotos(state.photos);});
  $('inspector-close').addEventListener('click',()=>{$('inspector').hidden=true;});$('details-form').addEventListener('submit',saveDetails);
  $('find-similar').addEventListener('click',()=>{if(state.current)showSimilar(state.current);});
  $('view-full').addEventListener('click',()=>{if(!state.current)return;$('full-image').src=`image.php?id=${state.current}&type=original`;$('preview-dialog').showModal();});
  $('download-current').hidden=!canEdit;
  $('download-current').addEventListener('click',()=>{if(state.current)window.location.href=`image.php?id=${state.current}&type=original&download=1`;});
  if(canEdit){
    $('new-folder').addEventListener('click',()=>manage('create_folder'));
    $('upload').addEventListener('change',e=>uploadFiles(e.target.files));$('upload-folder').addEventListener('change',e=>uploadFiles(e.target.files));
    $('move-selected').addEventListener('click',()=>manage('move_photos'));
    $('copy-selected').addEventListener('click',()=>manage('copy_photos'));
    $('trash-selected').addEventListener('click',()=>{const ids=idList();if(ids.length&&confirm(`Move ${ids.length} photographs to Trash?`))bulkAction('trash_photos',ids,'Photographs moved to Trash.');});
    $('restore-selected').addEventListener('click',restoreSelected);
    $('rename-current').addEventListener('click',()=>{const p=state.photos.find(photo=>Number(photo.id)===state.current);if(p)manage('rename_photo',{id:p.id,name:p.original_name});});
    $('manager-form').addEventListener('submit',managerSubmit);
    if(isAdmin)$('purge-selected').addEventListener('click',purgeSelected);
  }
  if(isAdmin)$('import-sftp').addEventListener('click',async()=>{
    if(!confirm('Import up to 12 photos from the private SFTP incoming folder?'))return;
    try{const r=await request('import_inbox',{});notice(`Imported ${r.imported} photos. ${r.failures.length?'Errors: '+r.failures.join('; '):''}`);await load();}catch(e){notice(e.message,true);}
  });
  $('open-export').addEventListener('click',openExport);$('download-selected').addEventListener('click',downloadSelected);
  $('preset').addEventListener('change',updatePreset);updatePreset();
  document.querySelectorAll('[data-close]').forEach(b=>b.addEventListener('click',()=>$(b.dataset.close).close()));
  $('menu-toggle').addEventListener('click',()=>{$('sidebar').classList.toggle('open');$('menu-toggle').setAttribute('aria-expanded',String($('sidebar').classList.contains('open')));});
  document.addEventListener('keydown',e=>{if(e.key==='Escape'){$('sidebar').classList.remove('open');$('menu-toggle').setAttribute('aria-expanded','false');}});
  if(canEdit){
    let dragDepth=0;document.addEventListener('dragenter',e=>{if(!e.dataTransfer?.types?.includes('Files'))return;dragDepth++;$('drop-zone').hidden=false;});
    document.addEventListener('dragover',e=>{if(e.dataTransfer?.types?.includes('Files'))e.preventDefault();});
    document.addEventListener('dragleave',()=>{dragDepth=Math.max(0,dragDepth-1);if(dragDepth===0)$('drop-zone').hidden=true;});
    document.addEventListener('drop',e=>{if(!e.dataTransfer?.files?.length)return;e.preventDefault();dragDepth=0;$('drop-zone').hidden=true;uploadFiles(e.dataTransfer.files);});
  }
  updateSelected();load();
}
init();
