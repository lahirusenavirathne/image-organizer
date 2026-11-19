"""Reviewable moves and non-destructive exports, with collisions prevented."""
from __future__ import annotations
import csv
import os
import json
import re
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from PIL import Image, ImageOps
from .db import connect, photo_by_id

INVALID = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
RESERVED = {'CON','PRN','AUX','NUL',*(f'COM{i}' for i in range(1,10)),*(f'LPT{i}' for i in range(1,10))}

def safe_part(value: str, fallback='Unclassified') -> str:
    name=INVALID.sub('_',value or '').strip(' .')[:90]
    if not name or name in ('.','..'): name=fallback
    if name.split('.')[0].upper() in RESERVED: name='_'+name
    return name

def unique_path(dest: Path, reserved: set[str] | None = None) -> Path:
    if reserved is None: reserved=set()
    p=dest
    i=2
    while p.exists() or str(p).casefold() in reserved:
        p=dest.with_name(f'{dest.stem}_{i}{dest.suffix}')
        i+=1
    reserved.add(str(p).casefold())
    return p

def preview_moves(db_path: Path, ids: list[int], destination: Path) -> list[dict]:
    destination=Path(destination).resolve()
    if not destination.is_dir(): raise ValueError('Destination folder does not exist')
    reserved=set()
    plan=[]
    with connect(db_path) as con:
        for pid in dict.fromkeys(ids):
            row=photo_by_id(con,pid)
            if not row: continue
            src=Path(row['path'])
            if not src.exists(): continue
            try: acts=json.loads(row['activities'])
            except (ValueError, TypeError): acts=[]
            loc=safe_part(row['location'], 'Location Unknown')
            activity=safe_part(acts[0] if acts else '', 'Activity Unknown')
            outdir=destination / loc / activity
            candidate=outdir / safe_part(src.stem,'Photo')
            proposed=unique_path(candidate.with_suffix(src.suffix),reserved)
            if proposed.resolve()==src.resolve(): continue
            plan.append({'id':pid,'source':str(src),'destination':str(proposed)})
    return plan

def move_no_overwrite(src: Path, dst: Path):
    """Exclusive-create+copy-verify-delete, safe across drive boundaries and name races."""
    if src.resolve()==dst.resolve(): raise ValueError('Source and destination are identical')
    if not src.is_file(): raise FileNotFoundError(src)
    src_size=src.stat().st_size
    created=False
    try:
        with src.open('rb') as inp, dst.open('xb') as out:
            created=True  # O_EXCL: destination collision always raises instead of overwriting.
            shutil.copyfileobj(inp,out,length=1024*1024)
            out.flush()
            os.fsync(out.fileno())
        if dst.stat().st_size!=src_size:
            raise OSError('Copied file size mismatch; original has been retained')
        shutil.copystat(src,dst)
        src.unlink()
    except Exception:
        if created:
            try: dst.unlink(missing_ok=True)
            except OSError: pass
        raise


def execute_moves(db_path: Path, plan: list[dict], progress=None):
    # Re-check every source and destination when executing; never overwrite.
    batch=uuid.uuid4().hex
    completed=[]; errors=[]
    with connect(db_path) as con:
        for n,move in enumerate(plan,1):
            src,dst=Path(move['source']),Path(move['destination'])
            try:
                row=photo_by_id(con,move['id'])
                if not row or Path(row['path'])!=src: raise RuntimeError('Photo path changed since preview')
                if not src.is_file(): raise FileNotFoundError(src)
                if dst.exists(): raise FileExistsError(f'Refusing to overwrite {dst}')
                dst.parent.mkdir(parents=True, exist_ok=True)
                move_no_overwrite(src,dst)
                try:
                    con.execute('UPDATE photos SET path=? WHERE id=?',(str(dst),move['id']))
                    con.execute('INSERT INTO moves (photo_id,previous_path,new_path,batch_id) VALUES (?,?,?,?)',
                                (move['id'],str(src),str(dst),batch))
                    con.commit()
                except Exception:
                    con.rollback()
                    if dst.exists() and not src.exists(): move_no_overwrite(dst,src)
                    raise
                completed.append(str(dst))
            except Exception as exc:
                errors.append(f'{src}: {exc}')
            if progress and n%5==0: progress(f'Moving approved files: {n}/{len(plan)}')
    return {'moved':len(completed),'errors':errors[:12],'batch_id':batch}

def undo_last_batch(db_path: Path, progress=None):
    restored=0; errors=[]
    with connect(db_path) as con:
        latest=con.execute('SELECT batch_id FROM moves WHERE undone_at IS NULL ORDER BY id DESC LIMIT 1').fetchone()
        if not latest: return {'restored':0,'errors':['There are no active moves to undo']}
        batch=latest['batch_id']
        moves=con.execute('SELECT * FROM moves WHERE batch_id=? AND undone_at IS NULL ORDER BY id DESC',(batch,)).fetchall()
        for n,m in enumerate(moves,1):
            dest=Path(m['previous_path']); current=Path(m['new_path'])
            try:
                if dest.exists(): raise FileExistsError(f'Original path already exists: {dest}')
                if not current.is_file(): raise FileNotFoundError(current)
                row=photo_by_id(con,m['photo_id'])
                if not row or row['path']!=str(current): raise RuntimeError('Catalog path changed')
                dest.parent.mkdir(parents=True,exist_ok=True)
                move_no_overwrite(current,dest)
                try:
                    con.execute('UPDATE photos SET path=? WHERE id=?',(str(dest),m['photo_id']))
                    con.execute("UPDATE moves SET undone_at=CURRENT_TIMESTAMP WHERE id=?",(m['id'],))
                    con.commit()
                except Exception:
                    con.rollback()
                    if dest.exists() and not current.exists(): move_no_overwrite(dest,current)
                    raise
                restored+=1
            except Exception as exc:
                errors.append(str(exc))
            if progress and n%5==0: progress(f'Undoing move batch: {n}/{len(moves)}')
    return {'restored':restored,'errors':errors[:12]}

FORMAT_SUFFIX={'JPEG':'.jpg','PNG':'.png','WEBP':'.webp','TIFF':'.tif'}

def export_image(source: Path, target: Path, width: int, height: int, mode: str, fmt: str, quality: int):
    with Image.open(source) as f:
        im=ImageOps.exif_transpose(f).copy()
    if width and height:
        if mode=='Crop to fill': im=ImageOps.fit(im,(width,height),Image.Resampling.LANCZOS)
        else:
            # Exact dimensions with padding; transparent for alpha-compatible formats, white for JPEG.
            color=(255,255,255,0) if fmt in ('PNG','WEBP','TIFF') else (255,255,255)
            if fmt in ('PNG','WEBP','TIFF'): im=im.convert('RGBA')
            else: im=im.convert('RGB')
            im=ImageOps.pad(im,(width,height),method=Image.Resampling.LANCZOS,color=color)
    elif width or height:
        w,h=im.size
        size=(width,max(1,round(h*width/w))) if width else (max(1,round(w*height/h)),height)
        im=im.resize(size,Image.Resampling.LANCZOS)
    if fmt=='JPEG':
        if im.mode!='RGB':
            flat=Image.new('RGB',im.size,'white')
            if 'A' in im.getbands(): flat.paste(im,mask=im.getchannel('A'))
            else: flat.paste(im.convert('RGB'))
            im=flat
        im.save(target,'JPEG',quality=quality,optimize=True)
    elif fmt=='WEBP': im.save(target,'WEBP',quality=quality,method=4)
    elif fmt=='PNG': im.save(target,'PNG',optimize=True)
    elif fmt=='TIFF': im.save(target,'TIFF',compression='tiff_lzw')
    else: raise ValueError('Unsupported export format')

def export_photos(db_path: Path, ids: list[int], destination: Path, *, width:int,
                  height:int, mode:str, fmt:str, quality:int, progress=None):
    if width<0 or height<0 or max(width,height)>16000: raise ValueError('Dimensions must be between 0 and 16000 pixels')
    if not width and not height: raise ValueError('Specify at least one dimension')
    if fmt not in FORMAT_SUFFIX: raise ValueError('Invalid format')
    destination=Path(destination).resolve()
    destination.mkdir(parents=True,exist_ok=True)
    batch=datetime.now().strftime('%Y%m%d_%H%M%S')+'_'+uuid.uuid4().hex[:6]
    reserved=set(); entries=[]; errors=[]
    with connect(db_path) as con:
        for i,pid in enumerate(dict.fromkeys(ids),1):
            row=photo_by_id(con,pid)
            if not row: continue
            src=Path(row['path'])
            dst=unique_path(destination / (safe_part(src.stem,'Photo') + FORMAT_SUFFIX[fmt]),reserved)
            try:
                export_image(src,dst,width,height,mode,fmt,quality)
                entries.append({'exported_path':str(dst),'original_path':row['original_path'],
                    'current_path':str(src),'location':row['location'],'attraction':row['attraction'],
                    'activities':', '.join(json.loads(row['activities'])),
                    'photographer':row['artist'],'copyright':row['copyright'],
                    'license':row['license'],'source_url':row['source_url']})
            except Exception as exc:
                dst.unlink(missing_ok=True)
                if len(errors)<12: errors.append(f'{src.name}: {exc}')
            if progress and i%5==0: progress(f'Exported: {i}/{len(ids)}')
    if entries:
        manifest=destination / f'export_manifest_{batch}.csv'
        with open(manifest,'w',encoding='utf-8-sig',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=list(entries[0]))
            writer.writeheader(); writer.writerows(entries)
    return {'exported':len(entries),'manifest':str(manifest) if entries else '',
            'errors':errors,'destination':str(destination)}
