"""Drive-style *local* organization for desktop photographs.

Folders are virtual collections in SQLite. Indexed originals stay at their existing
filesystem paths. Trash and permanent removal apply to the catalog, not to source
photographs (which may be on external drives). Only user-requested copies are
materialized in an application-managed directory. There is NO cloud sync here.
"""
from __future__ import annotations

import os
import shutil
import sqlite3
import uuid
from pathlib import Path

from . import db
from .metadata import image_paths, read_image
from .operations import safe_part, unique_path


def migrate(con: sqlite3.Connection):
    for name, decl in {
        'folder_id': 'INTEGER REFERENCES desktop_folders(id)',
        'display_name': "TEXT NOT NULL DEFAULT ''",
        'starred': 'INTEGER NOT NULL DEFAULT 0',
        'deleted_at': 'TEXT DEFAULT NULL',
        'trash_batch': 'TEXT DEFAULT NULL',
        'copied_from_id': 'INTEGER DEFAULT NULL',
    }.items():
        fields = {row['name'] for row in con.execute('PRAGMA table_info(photos)')}
        if name not in fields:
            con.execute(f'ALTER TABLE photos ADD COLUMN {name} {decl}')
    con.executescript('''
    CREATE TABLE IF NOT EXISTS desktop_folders (
      id INTEGER PRIMARY KEY,
      parent_id INTEGER REFERENCES desktop_folders(id),
      name TEXT NOT NULL,
      deleted_at TEXT DEFAULT NULL,
      trash_batch TEXT DEFAULT NULL,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE INDEX IF NOT EXISTS idx_desktop_folders_parent ON desktop_folders(parent_id);
    CREATE INDEX IF NOT EXISTS idx_photos_desktop_folder ON photos(folder_id,deleted_at);
    CREATE INDEX IF NOT EXISTS idx_photos_desktop_starred ON photos(starred,deleted_at);
    ''')


def valid_name(raw: str, *, limit: int = 190) -> str:
    if not isinstance(raw, str):
        raise ValueError('Enter a name')
    name=raw.strip()
    if not name or name in ('.', '..') or len(name)>limit or any(ord(c)<32 or c in '/\\' for c in name):
        raise ValueError('Names cannot be empty, too long, or contain slashes/control characters')
    return name


def folder(con, fid: int | None, *, include_trash: bool = False):
    if fid is None:
        return None
    row=con.execute('SELECT * FROM desktop_folders WHERE id=?',(fid,)).fetchone()
    if not row or (not include_trash and row['deleted_at']):
        raise ValueError('Folder not found or in Trash')
    return row


def create_folder(con, name: str, parent: int | None = None):
    name=valid_name(name)
    folder(con,parent)
    exists=con.execute('SELECT 1 FROM desktop_folders WHERE parent_id IS ? AND name=? COLLATE NOCASE AND deleted_at IS NULL',
                       (parent,name)).fetchone()
    if exists: raise ValueError('A folder with this name already exists here')
    cursor=con.execute('INSERT INTO desktop_folders(parent_id,name) VALUES(?,?)',(parent,name))
    return cursor.lastrowid


def children(con, parent: int | None, *, include_trashed: bool=False):
    return con.execute('SELECT * FROM desktop_folders WHERE parent_id IS ? AND deleted_at IS '
                       + ('NOT NULL' if include_trashed else 'NULL') + ' ORDER BY name COLLATE NOCASE', (parent,)).fetchall()


def all_folders(con, *, include_trashed=False):
    return con.execute('SELECT * FROM desktop_folders WHERE deleted_at IS '
                       + ('NOT NULL' if include_trashed else 'NULL') + ' ORDER BY name COLLATE NOCASE').fetchall()


def ancestors(con, fid: int | None):
    visited=set();result=[]
    while fid is not None:
        if fid in visited: raise ValueError('Folder hierarchy cycle')
        visited.add(fid)
        row=folder(con,fid)
        result.append(row)
        fid=row['parent_id']
        if len(result)>60: raise ValueError('Folder hierarchy too deep')
    return result[::-1]


def rename_folder(con, fid: int, name: str):
    item=folder(con,fid)
    name=valid_name(name)
    exists=con.execute('SELECT 1 FROM desktop_folders WHERE parent_id IS ? AND name=? COLLATE NOCASE AND id<>? AND deleted_at IS NULL',
                       (item['parent_id'],name,fid)).fetchone()
    if exists: raise ValueError('A sibling folder already has this name')
    con.execute('UPDATE desktop_folders SET name=? WHERE id=?',(name,fid))


def descendants(con, fid: int) -> list[int]:
    folder(con,fid,include_trash=True)
    rows=con.execute('SELECT id,parent_id FROM desktop_folders').fetchall()
    by_parent={}
    for row in rows: by_parent.setdefault(row['parent_id'],[]).append(row['id'])
    found=[];seen=set();queue=[fid]
    while queue:
        x=queue.pop(0)
        if x in seen: raise ValueError('Invalid cyclic folder hierarchy')
        seen.add(x);found.append(x)
        queue.extend(by_parent.get(x,[]))
        if len(found)>25000: raise ValueError('Folder hierarchy too large')
    return found


def move_folder(con, fid: int, parent: int | None):
    current=folder(con,fid)
    folder(con,parent)
    if parent in descendants(con,fid): raise ValueError('Cannot move folder inside itself or descendants')
    exists=con.execute('SELECT 1 FROM desktop_folders WHERE parent_id IS ? AND name=? COLLATE NOCASE AND id<>? AND deleted_at IS NULL',
                       (parent,current['name'],fid)).fetchone()
    if exists: raise ValueError('A folder with this name already exists at the destination')
    con.execute('UPDATE desktop_folders SET parent_id=? WHERE id=?',(parent,fid))


def _active_photo(con,pid):
    row=con.execute('SELECT * FROM photos WHERE id=? AND deleted_at IS NULL',(pid,)).fetchone()
    if not row: raise ValueError('Photo not found in active library')
    return row


def _trashed_photo(con,pid):
    row=con.execute('SELECT * FROM photos WHERE id=? AND deleted_at IS NOT NULL',(pid,)).fetchone()
    if not row: raise ValueError('Photo not found in Trash')
    return row


def _ids(con, ids, *, trashed=False, limit=100):
    numbers=list(dict.fromkeys(int(x) for x in ids))
    if not numbers or len(numbers)>limit: raise ValueError('Select between 1 and '+str(limit)+' photographs')
    for pid in numbers:
        (_trashed_photo if trashed else _active_photo)(con,pid)
    return numbers


def set_photo_name(con, pid: int, name: str):
    _active_photo(con,pid)
    con.execute('UPDATE photos SET display_name=? WHERE id=?',(valid_name(name,limit=220),pid))


def set_star(con, ids, value: bool):
    ids=_ids(con,ids)
    con.executemany('UPDATE photos SET starred=? WHERE id=?',[(int(value),pid) for pid in ids])
    return len(ids)


def move_photos(con, ids, destination: int | None):
    ids=_ids(con,ids)
    folder(con,destination)
    con.executemany('UPDATE photos SET folder_id=? WHERE id=?',[(destination,pid) for pid in ids])
    return len(ids)


def trash_photos(con, ids):
    ids=_ids(con,ids)
    batch=uuid.uuid4().hex
    con.executemany("UPDATE photos SET deleted_at=CURRENT_TIMESTAMP,trash_batch=? WHERE id=?",[(batch,pid) for pid in ids])
    return len(ids)


def restore_photos(con, ids):
    ids=_ids(con,ids,trashed=True)
    for pid in ids:
        row=_trashed_photo(con,pid)
        if row['folder_id'] is not None:
            try:folder(con,row['folder_id'])
            except ValueError: con.execute('UPDATE photos SET folder_id=NULL WHERE id=?',(pid,))
    con.executemany('UPDATE photos SET deleted_at=NULL,trash_batch=NULL WHERE id=?',[(pid,) for pid in ids])
    return len(ids)


def remove_catalog_records(con, ids):
    """Never unlink the user's source files, even if they are on another drive."""
    ids=_ids(con,ids,trashed=True,limit=50)
    con.executemany('DELETE FROM photos WHERE id=?',[(pid,) for pid in ids])
    return len(ids)


def trash_folder(con,fid: int):
    folder(con,fid)
    ids=descendants(con,fid);batch=uuid.uuid4().hex
    marks=','.join('?' for _ in ids)
    con.execute(f"UPDATE desktop_folders SET deleted_at=CURRENT_TIMESTAMP,trash_batch=? WHERE id IN ({marks}) AND deleted_at IS NULL",[batch,*ids])
    con.execute(f"UPDATE photos SET deleted_at=CURRENT_TIMESTAMP,trash_batch=? WHERE folder_id IN ({marks}) AND deleted_at IS NULL",[batch,*ids])
    return len(ids)


def restore_folder(con,fid: int):
    row=folder(con,fid,include_trash=True)
    if row['deleted_at'] is None:raise ValueError('Folder is not in Trash')
    if row['parent_id'] is not None:
        try:folder(con,row['parent_id'])
        except ValueError:con.execute('UPDATE desktop_folders SET parent_id=NULL WHERE id=?',(fid,))
    ids=descendants(con,fid)
    batch=row['trash_batch']
    if not batch: raise ValueError('Missing restoration data')
    marks=','.join('?' for _ in ids)
    # Restore only items deleted as part of this folder operation.
    con.execute(f'UPDATE desktop_folders SET deleted_at=NULL,trash_batch=NULL WHERE id IN ({marks}) AND trash_batch=?',[*ids,batch])
    con.execute(f'UPDATE photos SET deleted_at=NULL,trash_batch=NULL WHERE folder_id IN ({marks}) AND trash_batch=?',[*ids,batch])
    return len(ids)


def query_photos(con, search='', location='', activity='', group_id=None,
                 offset=0, limit=120, *, view='all', folder_id=None, sort='newest'):
    wheres=[];args=[]
    if view=='trash': wheres.append('p.deleted_at IS NOT NULL')
    else: wheres.append('p.deleted_at IS NULL')
    if view=='folder' or view=='drive':
        if folder_id is not None:folder(con,folder_id)
        wheres.append('p.folder_id IS ?');args.append(folder_id)
    if view=='starred':wheres.append('p.starred=1')
    if search:
        like='%'+search.replace('\\','\\\\').replace('%','\\%').replace('_','\\_')+'%'
        wheres.append("(p.path LIKE ? ESCAPE '\\' OR p.display_name LIKE ? ESCAPE '\\' OR p.attraction LIKE ? ESCAPE '\\' OR p.activities LIKE ? ESCAPE '\\' OR p.source_url LIKE ? ESCAPE '\\' OR p.copyright LIKE ? ESCAPE '\\')")
        args.extend([like]*6)
    if location: wheres.append('p.location=?');args.append(location)
    if activity: wheres.append('p.activities LIKE ?');args.append('%"'+activity+'"%')
    if group_id is not None:
        wheres.append('EXISTS (SELECT 1 FROM faces f WHERE f.photo_id=p.id AND f.group_id=?)')
        args.append(group_id)
    where=' AND '.join(wheres)
    orders={'newest':'p.id DESC','oldest':'p.id ASC','name':'COALESCE(NULLIF(p.display_name,\'\'),p.path) COLLATE NOCASE ASC',
            'size':'p.file_size DESC'}
    order=orders.get(sort,orders['newest'])
    total=con.execute(f'SELECT COUNT(*) FROM photos p WHERE {where}',args).fetchone()[0]
    rows=con.execute(f'SELECT p.* FROM photos p WHERE {where} ORDER BY {order} LIMIT ? OFFSET ?',args+[limit,offset]).fetchall()
    return rows,total


def _ensure_subfolders(con, parent, parts):
    for name in parts:
        name=valid_name(name)
        row=con.execute('SELECT id FROM desktop_folders WHERE parent_id IS ? AND name=? COLLATE NOCASE AND deleted_at IS NULL',
                        (parent,name)).fetchone()
        parent=row['id'] if row else create_folder(con,name,parent)
    return parent


def import_tree(db_path: Path, folder_path: Path, parent_id: int | None=None, source_url='', progress=None):
    """Index a local folder with virtual hierarchy. Does not copy or move source files."""
    base=Path(folder_path).resolve()
    if not base.is_dir():raise ValueError('Import directory does not exist')
    done=unchanged=failed=0; errors=[]
    with db.connect(db_path) as con:
        folder(con,parent_id)
        # Preserve the selected source folder as one container, just like web folder upload.
        top=_ensure_subfolders(con,parent_id,[base.name])
        cache={():top}
        for n,path in enumerate(image_paths(base),1):
            try:
                rp=str(path.resolve());stat=path.stat()
                parts=path.relative_to(base).parts[:-1]
                if parts not in cache:
                    cache[parts]=_ensure_subfolders(con,top,parts)
                dest=cache[parts]
                old=con.execute('SELECT id,mtime,file_size,deleted_at FROM photos WHERE path=?',(rp,)).fetchone()
                if old and old['mtime']==stat.st_mtime and old['file_size']==stat.st_size:
                    if old['deleted_at'] is None:
                        con.execute('UPDATE photos SET folder_id=? WHERE id=?',(dest,old['id']))
                    unchanged+=1
                    continue
                meta=read_image(path,source_url)
                if old:db.invalidate_faces(con,old['id'])
                db.upsert(con,meta)
                con.execute('UPDATE photos SET folder_id=? WHERE path=?',(dest,rp))
                done+=1
            except Exception as exc:
                failed+=1
                if len(errors)<12: errors.append(f'{path.name}: {exc}')
            if n%30==0:
                con.commit()
                if progress:progress(f'Indexing folders: {n} images, {done} new/changed')
        con.commit()
    return {'indexed':done,'unchanged':unchanged,'failed':failed,'examples':errors}


def copy_photos(db_path: Path, ids, app_dir: Path, destination: int | None, progress=None):
    """Create verified physical copies only inside application-controlled storage."""
    app_dir=Path(app_dir).resolve()
    copies_dir=app_dir/'managed_copies'
    copies_dir.mkdir(parents=True,exist_ok=True)
    made=[];errors=[]
    with db.connect(db_path) as con:
        folder(con,destination)
        for pid in _ids(con,ids,limit=25):
            row=_active_photo(con,pid)
            src=Path(row['path'])
            name=safe_part(Path(row['display_name'] or src.name).stem, 'Photo')
            target=copies_dir/(uuid.uuid4().hex+'_'+name+src.suffix.lower())
            try:
                if not src.is_file():raise FileNotFoundError(src)
                with src.open('rb') as inp,target.open('xb') as out:
                    shutil.copyfileobj(inp,out,length=1024*1024)
                    out.flush();os.fsync(out.fileno())
                if src.stat().st_size!=target.stat().st_size:raise OSError('Copy size mismatch')
                meta=read_image(target)
                db.upsert(con,meta)
                new_id=con.execute('SELECT id FROM photos WHERE path=?',(str(target),)).fetchone()['id']
                # This is a byte-for-byte copy, so manually verified metadata remains relevant.
                con.execute('''UPDATE photos SET folder_id=?,display_name=?,source_url=?,source_folder=?,
                    location=?,location_source=?,activities=?,attraction=?,rights_status=?,
                    artist=?,copyright=?,license=?,ai_source=?,copied_from_id=? WHERE id=?''',
                    (destination,valid_name(('Copy of '+(row['display_name'] or src.name))[:220],limit=220),
                     row['source_url'],row['source_folder'],row['location'],row['location_source'],
                     row['activities'],row['attraction'],row['rights_status'],row['artist'],
                     row['copyright'],row['license'],row['ai_source'],pid,new_id))
                con.commit();made.append(new_id)
            except Exception as exc:
                con.rollback()
                target.unlink(missing_ok=True)
                if len(errors)<12:errors.append(f'{src.name}: {exc}')
            if progress:progress(f'Copied {len(made)} of {len(ids)} selected images')
    return {'copied':len(made),'errors':errors}


def purge_folder(con,fid: int):
    """Remove a trashed virtual folder tree and its trashed catalog records, never source files."""
    row=folder(con,fid,include_trash=True)
    if not row['deleted_at']:raise ValueError('Folder is not in Trash')
    ids=descendants(con,fid)
    marks=','.join('?' for _ in ids)
    # A photo can be restored independently, in which case it must be kept.
    con.execute(f'UPDATE photos SET folder_id=NULL WHERE folder_id IN ({marks}) AND deleted_at IS NULL',ids)
    deleted=con.execute(f'DELETE FROM photos WHERE folder_id IN ({marks}) AND deleted_at IS NOT NULL',ids).rowcount
    for child in reversed(ids):
        con.execute('DELETE FROM desktop_folders WHERE id=?',(child,))
    return {'folders':len(ids),'catalog_records':deleted}


def save_originals(db_path: Path, ids, destination: Path, progress=None):
    """Copy intact source files to an export folder, refusing every collision."""
    destination=Path(destination).resolve()
    destination.mkdir(parents=True,exist_ok=True)
    copied=0;errors=[];reserved=set()
    with db.connect(db_path) as con:
        for pid in _ids(con,ids,limit=100):
            row=_active_photo(con,pid)
            src=Path(row['path'])
            requested=(row['display_name'] or src.name)
            name=safe_part(Path(requested).stem,'Photo')+src.suffix
            dst=unique_path(destination/name,reserved)
            created=False
            try:
                if not src.is_file():raise FileNotFoundError(src)
                if src.resolve()==dst.resolve():raise ValueError('Source and destination are identical')
                with src.open('rb') as inp,dst.open('xb') as out:
                    created=True
                    shutil.copyfileobj(inp,out,length=1024*1024)
                    out.flush();os.fsync(out.fileno())
                if src.stat().st_size!=dst.stat().st_size:raise OSError('Copy size mismatch')
                shutil.copystat(src,dst);copied+=1
            except Exception as exc:
                if created:dst.unlink(missing_ok=True)
                if len(errors)<12:errors.append(f'{src.name}: {exc}')
            if progress:progress(f'Saved {copied} originals')
    return {'copied':copied,'errors':errors,'destination':str(destination)}
