"""Non-destructive photo metadata reconciliation inside explicitly selected folders.

Fields are filled only when empty. The fingerprint must be identical, manually
reviewed fields are protected and conflicting nonempty values stay untouched.
The local physical source path, GPS, faces and AI-inferred identity never transfer.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit
from . import db, drive, web_sync

# server_field -> (local_column, maximum_length)
SAFE_FIELDS = {
    'location': ('location', 150),
    'attraction': ('attraction', 190),
    'activities': ('activities', 500),
    'source_url': ('source_url', 1000),
    'photographer': ('artist', 255),
    'copyright_text': ('copyright', 1000),
    'license': ('license', 255),
    'rights_status': ('rights_status', 32),
}
TAGS = {'location','attraction','activities'}
RIGHTS = {'Verified','Permission required'}


def _normalized(value) -> str:
    return value.strip() if isinstance(value,str) else ''


def _meaningful(field: str, value: str) -> bool:
    return bool(value) and not (field=='rights_status' and value=='Unknown')


def _web_value(field: str, value: str) -> str:
    """Convert SQLite's structured activity list into web display categories."""
    if field!='activities': return _normalized(value)
    try:
        data=json.loads(value)
    except (ValueError,TypeError): return _normalized(value)
    if isinstance(data,list) and all(isinstance(s,str) for s in data):
        return ', '.join(s.strip() for s in data if s.strip())
    return ''


def _local_value(field: str, value: str) -> str:
    if field=='activities':
        return json.dumps([v.strip() for v in value.split(',') if v.strip()],ensure_ascii=False)
    return value


def _safe_value(field: str, raw) -> str:
    if not isinstance(raw,str): return ''
    value=raw.strip()
    if not value or any(ord(c)<32 and c not in '\t' for c in value):return ''
    if len(value.encode('utf-8'))>SAFE_FIELDS[field][1]:return ''
    if field=='rights_status' and value not in RIGHTS:return ''
    if field=='source_url':
        parts=urlsplit(value)
        if parts.scheme not in ('http','https') or not parts.netloc or parts.username or parts.password:
            return ''
    return value


def merge_plan(local: dict, remote: dict) -> dict:
    """Pure policy: decide per-field fills, retain all disagreements for review."""
    to_web={};to_local={};conflicts=[]
    for web_key,(local_key,_) in SAFE_FIELDS.items():
        local_raw=local.get(local_key)
        remote_raw=remote.get(web_key)
        local_value=_safe_value(web_key,_web_value(web_key,_normalized(local_raw)))
        remote_value=_safe_value(web_key,_normalized(remote_raw))
        if local_value==remote_value:continue
        local_filled=_meaningful(web_key,local_value)
        remote_filled=_meaningful(web_key,remote_value)
        if local_filled and remote_filled:
            conflicts.append(web_key)
            continue
        if local_filled and not remote_filled:
            # The server independently refuses changes to reviewed tags/rights.
            if remote.get('ai_status')=='reviewed' and web_key in (TAGS|{'rights_status'}):
                conflicts.append(web_key)
            else:
                to_web[web_key]=local_value
        elif remote_filled and not local_filled:
            # A manual blank is intentional; local AI/manual category choices win.
            if (web_key=='location' and local.get('location_source')=='Manual') or \
               (web_key in {'activities','attraction'} and local.get('ai_source')=='Manual'):
                conflicts.append(web_key)
            else:
                to_local[local_key]=_local_value(web_key,remote_value)
    return {'to_web':to_web,'to_local':to_local,'conflicts':conflicts}


def _apply_missing_local(con, photo_id: int, fields: dict) -> int:
    """Atomic blank-only SQL writes. Never flip AI/source flags to Manual."""
    count=0
    for local_col,val in fields.items():
        web_field=next(w for w,(l,_) in SAFE_FIELDS.items() if l==local_col)
        special="(TRIM(COALESCE(rights_status,''))='' OR rights_status='Unknown')" if local_col=='rights_status' else \
                f"TRIM(COALESCE({local_col},''))=''"
        guard=''
        if web_field=='location':guard=" AND COALESCE(location_source,'')<>'Manual'"
        elif web_field in ('activities','attraction'):guard=" AND COALESCE(ai_source,'')<>'Manual'"
        statement=con.execute(f'''UPDATE photos SET {local_col}=?
                       WHERE id=? AND deleted_at IS NULL AND {special}{guard}''',(val,photo_id))
        count+=statement.rowcount
    if count and 'location' in fields:
        con.execute("UPDATE photos SET location_source='Web Sync' WHERE id=? AND location=? AND COALESCE(location_source,'')<>'Manual'", (photo_id,fields['location']))
    if count and ('activities' in fields or 'attraction' in fields):
        con.execute("UPDATE photos SET ai_source='Web Sync' WHERE id=? AND COALESCE(ai_source,'')<>'Manual'", (photo_id,))
    return count


def sync_selected_metadata(db_path: Path, client: web_sync.ApiClient, *,
                           selected_ids: list[int], remote_parent_id: int=0,
                           limit: int=10, progress=None) -> dict:
    """10 pairs per click, round-robin across the selected photo set only."""
    from .folder_sync import folder_selection
    plan=folder_selection(db_path,selected_ids)
    limit=max(1,min(10,int(limit)))
    stats={'metadata_pairs':0,'metadata_web_updated':0,'metadata_local_updated':0,
           'metadata_conflicts':0,'metadata_failed':0,'metadata_skipped':0,
           'metadata_more':False,'metadata_examples':[]}
    scope=hashlib.sha256((str(remote_parent_id)+':'+','.join(map(str,sorted(selected_ids)))).encode()).hexdigest()
    with db.connect(db_path) as con:
        web_sync.migrate(con)
        con.execute('''CREATE TABLE IF NOT EXISTS web_sync_metadata_cursor (
            server_url TEXT NOT NULL, selection_key TEXT NOT NULL, last_photo_id INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY(server_url,selection_key))''')
        last=con.execute('''SELECT last_photo_id FROM web_sync_metadata_cursor
            WHERE server_url=? AND selection_key=?''',(client.endpoint,scope)).fetchone()
        last_id=int(last['last_photo_id']) if last else 0
        # A job never grants additional folder access: intersect with the live
        # selected-folder SQLite plan before every read or remote update.
        allowed=set(plan['covered'])
        rows=con.execute('''SELECT p.*, j.remote_id, j.folder_id AS remote_folder_id, j.sha256 AS synced_sha
            FROM photos p JOIN web_sync_jobs j ON j.photo_id=p.id
            WHERE j.server_url=? AND j.state='done' AND j.remote_id IS NOT NULL
              AND p.deleted_at IS NULL ORDER BY p.id''',(client.endpoint,)).fetchall()
        matches=[dict(r) for r in rows if r['folder_id'] in allowed]
        # A photo might have moved, but do not trust a stale checkpoint's folder.
        matches=[r for r in matches if r['folder_id'] is not None]
    if not matches:return stats
    # Resolve the CURRENT remote path from the selected folder tree, never from
    # a historical checkpoint alone. Otherwise moving a local photo could let
    # a selected-folder run modify metadata in an unrelated remote folder.
    folder_paths={fid:folder['path'] for fid,folder in plan['covered'].items()}
    folder_cache={():remote_parent_id}
    def remote_path(path:tuple[str,...]) -> int:
        if path in folder_cache:return folder_cache[path]
        parent=remote_path(path[:-1])
        rows=[r for r in client.list_folders(parent) if r.get('name')==path[-1]]
        if len(rows)!=1:
            raise web_sync.SyncError('Selected web folder missing or ambiguous','folder_missing')
        folder_cache[path]=int(rows[0]['id'])
        return folder_cache[path]
    after=[r for r in matches if r['id']>last_id]
    before=[r for r in matches if r['id']<=last_id]
    candidates=(after+before)[:limit]
    stats['metadata_more']=len(after)>len(candidates)
    for row in candidates:
        pid=int(row['id']);remote_id=int(row['remote_id'])
        try:
            path=Path(row['path'])
            if not path.is_file() or web_sync.file_hash(path)!=row['synced_sha']:
                stats['metadata_skipped']+=1;continue
            if progress:progress(f'Selected-folder metadata {stats["metadata_pairs"]+1}/{len(candidates)}')
            expected_folder=remote_path(folder_paths[int(row['folder_id'])])
            if expected_folder!=int(row['remote_folder_id']):
                stats['metadata_conflicts']+=1;continue
            remote=client.get_photo(remote_id)
            if remote.get('sha256')!=row['synced_sha'] or int(remote.get('folder_id') or 0)!=int(row['remote_folder_id']):
                stats['metadata_conflicts']+=1;continue
            plan_fields=merge_plan(row,remote)
            stats['metadata_conflicts']+=len(plan_fields['conflicts'])
            if plan_fields['to_web']:
                response=client.fill_metadata(remote_id,row['synced_sha'],plan_fields['to_web'])
                stats['metadata_web_updated']+=len(response['updated'])
                stats['metadata_conflicts']+=len(response.get('ignored',[]))
            if plan_fields['to_local']:
                with db.connect(db_path) as con:
                    stats['metadata_local_updated']+=_apply_missing_local(con,pid,plan_fields['to_local'])
            stats['metadata_pairs']+=1
        except (web_sync.SyncError, ValueError, OSError, KeyError, TypeError) as err:
            stats['metadata_failed']+=1
            if len(stats['metadata_examples'])<4:
                stats['metadata_examples'].append('Metadata for a selected photograph could not be reconciled; retry or review')
            if isinstance(err,web_sync.SyncError) and err.status in (401,403,429):break
        finally:
            with db.connect(db_path) as con:
                con.execute('''INSERT INTO web_sync_metadata_cursor(server_url,selection_key,last_photo_id)
                    VALUES(?,?,?) ON CONFLICT(server_url,selection_key)
                    DO UPDATE SET last_photo_id=excluded.last_photo_id''',(client.endpoint,scope,pid))
    return stats
