"""Explicitly scoped local folder -> web uploads (no polling or destructive mirroring).

Only photos in actively selected virtual desktop folders and their descendants
are eligible. Ancestor folders are created as *containers* on the web, but
photos from those unselected ancestors or sibling folders are not transferred.
"""
from __future__ import annotations
from pathlib import Path
from typing import Callable
from . import db, drive, web_sync

BATCH_LIMIT = 20


def available_folders(db_path: Path) -> list[dict]:
    """Active local folders, with stable IDs and display paths for an opt-in UI."""
    with db.connect(db_path) as con:
        drive.migrate(con)
        rows = con.execute('SELECT id,parent_id,name FROM desktop_folders '
                           'WHERE deleted_at IS NULL ORDER BY id').fetchall()
    lookup = {int(row['id']): dict(row) for row in rows}
    paths = {}

    def path_for(fid: int, visiting: set[int] | None = None) -> tuple[str, ...]:
        if fid in paths:
            return paths[fid]
        visiting = set() if visiting is None else visiting
        if fid in visiting or len(visiting) > 60:
            raise ValueError('Invalid desktop folder hierarchy')
        if fid not in lookup:
            raise ValueError('A desktop folder or ancestor is in Trash')
        visiting.add(fid)
        row = lookup[fid]
        parent = row['parent_id']
        prefix = path_for(int(parent), visiting) if parent is not None else ()
        result = (*prefix, drive.valid_name(row['name']))
        paths[fid] = result
        visiting.remove(fid)
        return result

    return [dict(id=fid, parent_id=entry['parent_id'], name=entry['name'],
                 path=path_for(fid)) for fid, entry in lookup.items()]


def folder_selection(db_path: Path, selected_ids: list[int]) -> dict:
    """Re-evaluate selection from SQLite each time; never trust stale stored IDs."""
    if not selected_ids or len(selected_ids) > 100:
        raise ValueError('Select between 1 and 100 local folders for web synchronization')
    ids = set()
    for item in selected_ids:
        if isinstance(item, bool) or not isinstance(item, int) or item <= 0:
            raise ValueError('Invalid local folder selection')
        ids.add(item)
    folders = available_folders(db_path)
    lookup = {f['id']: f for f in folders}
    if not ids.issubset(lookup):
        raise ValueError('A selected folder was deleted or moved to Trash. Review the selection.')
    roots = sorted((f for f in folders if f['id'] in ids and not any(
        ancestor['id'] in ids and ancestor['path'] == f['path'][:len(ancestor['path'])]
        for ancestor in folders if len(ancestor['path']) < len(f['path'])
    )), key=lambda f:f['path'])
    # Only active descendant photo folders are in scope; no library-wide fallback.
    covered = {f['id']: f for f in folders if any(
        f['path'][:len(root['path'])] == root['path'] for root in roots)}
    with db.connect(db_path) as con:
        photos = [dict(r) for r in con.execute('''SELECT id,path,display_name,folder_id FROM photos
              WHERE deleted_at IS NULL AND folder_id IS NOT NULL ORDER BY id''')
              if int(r['folder_id']) in covered]
    return {'roots': roots, 'covered': covered, 'photos': photos,
            'folder_count': len(covered), 'photo_count': len(photos)}


def sync_selected_folders(db_path: Path, client: web_sync.ApiClient, *,
                          selected_ids: list[int], remote_parent_id: int=0,
                          limit: int=BATCH_LIMIT,
                          progress: Callable[[str], None] | None=None) -> dict:
    """Upload the next <=20 *changed or pending* photos in selected folders.

    Re-running the same folder selection skips already transferred unchanged
    files. Changed files get a non-destructive preflight and may conflict; no
    cloud-side or PC-side delete, overwrite, or metadata reconciliation occurs.
    """
    if isinstance(remote_parent_id, bool) or not isinstance(remote_parent_id, int) or remote_parent_id < 0:
        raise ValueError('Invalid destination folder')
    limit = max(1, min(BATCH_LIMIT, int(limit)))
    plan = folder_selection(db_path, selected_ids)  # Validate before remote writes.
    info = client.me()
    if info.get('scope') != 'write' or info.get('role') not in ('admin','editor'):
        raise web_sync.SyncError('A write token from an Editor or Admin is required.', 'forbidden')
    resolved = {(): remote_parent_id}
    remote_created = 0
    folder_limit_hit = False

    def ensure_path(path: tuple[str, ...]) -> int:
        nonlocal remote_created
        if path in resolved:
            return resolved[path]
        parent = ensure_path(path[:-1])
        name = path[-1]
        found = client.list_folders(parent)
        matches = [r for r in found if r.get('name') == name]
        if len(matches) > 1:
            raise web_sync.SyncError('Multiple remote folders share the same name; review the destination.', 'conflict')
        if matches:
            fid = int(matches[0]['id'])
        else:
            if remote_created>=50:
                raise web_sync.SyncError('Remote folder creation limit reached; continue next batch', 'folder_batch_limit')
            # Re-query after a lost create response: the remote folder may exist.
            try:
                created = client.create_folder(name, parent)
                fid = int(created['id'])
                remote_created += 1
            except web_sync.SyncError as err:
                again = client.list_folders(parent)
                match = [r for r in again if r.get('name') == name]
                if len(match) != 1:
                    raise err
                fid = int(match[0]['id'])
        if fid <= 0:
            raise web_sync.SyncError('Invalid remote folder response', 'response')
        resolved[path] = fid
        return fid

    stats = {'selected_folders':len(plan['roots']), 'in_scope_photos':plan['photo_count'],
             'attempted':0, 'uploaded':0, 'already_on_web':0, 'conflicts':0,
             'failed':0, 'skipped':0, 'previously_completed':0, 'previous_conflicts':0, 'examples':[],
             'remote_folders_created':0, 'more_may_remain':False, 'folder_limit_hit':False}
    # Create bounded portions of the COMPLETE selected tree, including empty
    # descendants. Unselected ancestors are container-only shells.
    for entry in sorted(plan['covered'].values(),key=lambda f:(len(f['path']),f['path'])):
        try:
            ensure_path(entry['path'])
        except web_sync.SyncError as error:
            if error.code!='folder_batch_limit':raise
            folder_limit_hit=True
            stats['more_may_remain']=True
            break
    for photo in plan['photos']:
        folder = plan['covered'][int(photo['folder_id'])]
        # No work is done for unselected or trashed folders.
        src = Path(photo['path'])
        try:
            source_stat = src.stat()
        except OSError:
            stats['failed'] += 1
            if len(stats['examples']) < 8: stats['examples'].append('A selected photo is missing locally')
            continue
        if (src.suffix.lower() not in web_sync.SUPPORTED_MIMES or
            source_stat.st_size < 1 or source_stat.st_size > web_sync.MAX_UPLOAD):
            stats['skipped'] += 1
            continue  # Never let unsupported files block the next eligible batch.
        if folder['path'] not in resolved:
            stats['more_may_remain']=True
            continue
        remote_id = resolved[folder['path']]
        with db.connect(db_path) as con:
            web_sync.migrate(con)
            record = con.execute('''SELECT state,size_bytes,mtime_ns FROM web_sync_jobs
               WHERE photo_id=? AND server_url=? AND folder_id=?''',
               (photo['id'],client.endpoint,remote_id)).fetchone()
        if record and record['state'] in ('done','conflict') and \
           record['size_bytes']==source_stat.st_size and record['mtime_ns']==source_stat.st_mtime_ns:
            stats['previously_completed' if record['state']=='done' else 'previous_conflicts'] += 1
            continue
        if stats['attempted'] >= limit:
            stats['more_may_remain'] = True
            break
        if progress:
            progress(f'Selected folders: uploading {stats["attempted"]+1}/{limit} — {"/".join(folder["path"])}')
        batch = web_sync.upload_batch(db_path,client,selected_ids=[int(photo['id'])],
                                       folder_id=remote_id,limit=1)
        stats['attempted'] += 1
        for name in ('uploaded','already_on_web','conflicts','failed','skipped'):
            stats[name] += batch[name]
        for example in batch['examples']:
            if len(stats['examples'])<8: stats['examples'].append(example)
        if batch['failed'] and any('access denied' in e.lower() for e in batch['examples']):
            break
    stats['remote_folders_created'] = remote_created
    stats['folder_limit_hit']=folder_limit_hit
    return stats


def _safe_windows_name(name: str) -> str:
    """Reject hostile server filenames; don't trust a remote user-controlled path."""
    if not isinstance(name,str) or len(name)>220 or not name or name in ('.','..'):
        raise ValueError('Unsupported remote photo filename')
    if any(ord(ch)<32 or ch in '/\\<>:"|?*' for ch in name):
        raise ValueError('Unsafe remote photo filename')
    if name[-1] in (' ','.') or name.split('.')[0].upper() in {'CON','PRN','AUX','NUL'}:
        raise ValueError('Unsupported Windows filename')
    if Path(name).suffix.lower() not in web_sync.SUPPORTED_MIMES:
        raise ValueError('Unsupported web image format')
    return name


def _safe_windows_dir(name: str) -> str:
    if not isinstance(name,str) or not (1 <= len(name) <= 190):
        raise ValueError('Unsupported remote folder name')
    if name in ('.','..') or name[-1] in (' ','.') or any(
            ord(ch)<32 or ch in '/\\<>:"|?*' for ch in name):
        raise ValueError('Unsafe remote folder name')
    if name.split('.')[0].upper() in {'CON','PRN','AUX','NUL'}:
        raise ValueError('Unsupported Windows folder name')
    return name


def download_selected_folders(db_path: Path, client: web_sync.ApiClient, *,
                              selected_ids: list[int], remote_parent_id: int=0,
                              limit: int=BATCH_LIMIT,
                              progress: Callable[[str],None] | None=None) -> dict:
    """Download web-only originals within selected local folder trees.

    A remote folder outside the matched selected roots can never be traversed.
    Downloads are new files in app-managed storage and never overwrite a local
    original. The web server is never asked to modify or delete anything.
    """
    import hashlib
    from .metadata import read_image
    plan=folder_selection(db_path,selected_ids)
    limit=max(1,min(BATCH_LIMIT,int(limit)))
    local_by_path={f['path']:f['id'] for f in available_folders(db_path)}
    web_base=Path(db_path).parent/'web_sync_downloads'/hashlib.sha256(
        client.endpoint.encode('utf-8')).hexdigest()[:16]
    result={'downloaded':0,'download_attempts':0,'remote_already_local':0,'download_conflicts':0,
            'download_failed':0,'download_skipped':0,'scan_limit_hit':False,'examples':[]}
    with db.connect(db_path) as con:web_sync.migrate(con)

    def remote_path(path: tuple[str,...]) -> int:
        """Resolve without creating remotely; upload phase creates matched folders."""
        parent=remote_parent_id
        for name in path:
            matches=[f for f in client.list_folders(parent) if f['name']==name]
            if len(matches)!=1:
                raise web_sync.SyncError('Selected web folder missing or ambiguous; upload folder paths first','folder_missing')
            parent=int(matches[0]['id'])
        return parent

    def ensure_local_path(path: tuple[str,...]) -> int:
        if path in local_by_path:
            return local_by_path[path]
        parent_id=ensure_local_path(path[:-1])
        name=_safe_windows_dir(path[-1])
        with db.connect(db_path) as con:
            existing=con.execute('''SELECT id FROM desktop_folders WHERE parent_id IS ?
                AND name=? COLLATE NOCASE AND deleted_at IS NULL LIMIT 1''',
                (parent_id,name)).fetchone()
            local_id=int(existing['id']) if existing else drive.create_folder(con,name,parent_id)
        local_by_path[path]=local_id
        return local_id

    # Restrict traversal to each explicitly chosen root. Photo lists are scoped
    # by remote folder ID; no global server photo listing is performed.
    roots=plan['roots']
    remote_calls=0
    for root in roots:
        if result['download_attempts']>=limit:break
        current=remote_path(root['path'])
        queue=[(current,root['path'])]
        seen=set()
        while queue and result['download_attempts']<limit:
            fid,path=queue.pop(0)
            if fid in seen:continue
            seen.add(fid)
            if remote_calls>=75:
                result['scan_limit_hit']=True;break
            # This can discover web-only child folders, but only beneath a
            # selected subtree; no sibling or ancestor photos are listed.
            children=client.list_folders(fid);remote_calls+=1
            for child in children:
                if len(seen)+len(queue)>=75:
                    result['scan_limit_hit']=True;break
                from_name=str(child['name'])
                try: _safe_windows_dir(from_name)
                except ValueError:
                    result['download_skipped']+=1;continue
                child_path=(*path,from_name)
                ensure_local_path(child_path)  # preserve empty web subfolders too
                queue.append((int(child['id']), child_path))
            with db.connect(db_path) as con:
                row=con.execute('''SELECT next_page FROM web_sync_scan_pages WHERE
                    server_url=? AND remote_folder_id=?''',(client.endpoint,fid)).fetchone()
                start_page=int(row[0]) if row else 1
            # Rotate the page cursor after each page so huge folders eventually
            # reach later photos without scanning thousands of rows per click.
            page=start_page
            for _ in range(5):
                if remote_calls>=75:
                    result['scan_limit_hit']=True;break
                payload=client.list_photos(fid,page);remote_calls+=1
                photos=payload['data'];pages=int(payload.get('meta',{}).get('pages',1))
                if page>pages:page=1;continue
                # Save next page even if quota interrupts mid-page; the cycle
                # returns to this page after its last page is reached.
                next_page=1 if page>=pages else page+1
                with db.connect(db_path) as con:
                    con.execute('''INSERT INTO web_sync_scan_pages(server_url,remote_folder_id,next_page)
                        VALUES(?,?,?) ON CONFLICT(server_url,remote_folder_id)
                        DO UPDATE SET next_page=excluded.next_page''',
                        (client.endpoint,fid,next_page))
                for photo in photos:
                    if result['download_attempts']>=limit:break
                    try:
                        remote_id=int(photo['id']);sha=str(photo['sha256']);size=int(photo['file_size'])
                        name=_safe_windows_name(str(photo['original_name']))
                        if not (0<size<=web_sync.MAX_UPLOAD and len(sha)==64):
                            result['download_skipped']+=1;continue
                        with db.connect(db_path) as con:
                            received=con.execute('''SELECT 1 FROM web_sync_downloads
                                WHERE server_url=? AND remote_photo_id=?''',(client.endpoint,remote_id)).fetchone()
                            uploaded=con.execute('''SELECT 1 FROM web_sync_jobs WHERE
                                server_url=? AND remote_id=? AND state='done' ''',
                                (client.endpoint,remote_id)).fetchone()
                            if received or uploaded:
                                result['remote_already_local']+=1;continue
                            local_folder_id=local_by_path.get(path)
                            if local_folder_id is not None:
                                existing=con.execute('''SELECT path,display_name FROM photos
                                    WHERE folder_id=? AND deleted_at IS NULL''',
                                    (local_folder_id,)).fetchall()
                                if any(str(row['display_name']).casefold()==name.casefold() or
                                       Path(row['path']).name.casefold()==name.casefold()
                                       for row in existing):
                                    result['download_conflicts']+=1
                                    continue
                        # Remote-created subfolders are materialized as virtual
                        # children only within a user-selected local subtree.
                        if local_folder_id is None:
                            local_folder_id=ensure_local_path(path)
                        relative=tuple(_safe_windows_dir(part) for part in path)
                        destination=web_base.joinpath(*relative,name)
                        if destination.exists():
                            result['download_conflicts']+=1;continue
                        if progress:progress(f'Selected folders: downloading {name} to Windows')
                        result['download_attempts']+=1
                        client.download_photo(remote_id,destination,sha)
                        try:
                            with db.connect(db_path) as con:
                                db.upsert(con,read_image(destination))
                                local_id=int(con.execute('SELECT id FROM photos WHERE path=?',
                                    (str(destination.resolve()),)).fetchone()[0])
                                con.execute('UPDATE photos SET folder_id=?,display_name=? WHERE id=?',
                                            (local_folder_id,name,local_id))
                                con.execute('''INSERT OR REPLACE INTO web_sync_downloads
                                    (server_url,remote_photo_id,local_photo_id,sha256)
                                    VALUES(?,?,?,?)''',(client.endpoint,remote_id,local_id,sha))
                        except Exception:
                            # Nothing committed in SQLite if import fails.
                            destination.unlink(missing_ok=True)
                            raise
                        # A downloaded web original is already present on the
                        # server: record its checkpoint so the next upload phase
                        # never re-uploads it.
                        local_stat=destination.stat()
                        with db.connect(db_path) as con:
                            con.execute('''INSERT INTO web_sync_jobs
                                (photo_id,server_url,folder_id,sha256,size_bytes,mtime_ns,state,remote_id)
                                VALUES(?,?,?,?,?,?,'done',?)
                                ON CONFLICT(photo_id,server_url,folder_id) DO UPDATE SET
                                    sha256=excluded.sha256,size_bytes=excluded.size_bytes,
                                    mtime_ns=excluded.mtime_ns,state='done',remote_id=excluded.remote_id''',
                                (local_id,client.endpoint,fid,sha,local_stat.st_size,
                                 local_stat.st_mtime_ns,remote_id))
                        result['downloaded']+=1
                    except (ValueError,OSError,web_sync.SyncError) as exc:
                        result['download_failed']+=1
                        if len(result['examples'])<8:
                            result['examples'].append(f'Web photo {photo.get("id", "?")}: review this download')
                if result['download_attempts']>=limit or page>=pages:break
                page+=1
    return result


def sync_selected_folder_trees(db_path: Path, client: web_sync.ApiClient, *,
                               selected_ids: list[int], remote_parent_id: int=0,
                               limit: int=BATCH_LIMIT,
                               progress: Callable[[str],None] | None=None) -> dict:
    """Explicit two-way *additive* transfer inside chosen folder trees.

    No filesystem watcher, metadata merge, delete propagation or overwrites.
    Entire batch is capped to 20 upload/download attempts for shared hosting.
    """
    limit=max(1,min(BATCH_LIMIT,int(limit)))
    sent=sync_selected_folders(db_path,client,selected_ids=selected_ids,
                               remote_parent_id=remote_parent_id,limit=limit,progress=progress)
    remaining=limit-sent['attempted']
    received={'downloaded':0,'download_attempts':0,'remote_already_local':0,'download_conflicts':0,
              'download_failed':0,'download_skipped':0,'scan_limit_hit':False,'examples':[]}
    if remaining>0:
        received=download_selected_folders(db_path,client,selected_ids=selected_ids,
                                           remote_parent_id=remote_parent_id,
                                           limit=remaining,progress=progress)
    # Metadata has its own bounded round-robin queue, so a large selected tree
    # does not starve the later photos indefinitely. No unselected photo is eligible.
    from .metadata_sync import sync_selected_metadata
    metadata=sync_selected_metadata(db_path,client,selected_ids=selected_ids,
                                        remote_parent_id=remote_parent_id,limit=10,progress=progress)
    return {**sent,**received,**metadata,
            'examples':(sent['examples']+received['examples']+metadata['metadata_examples'])[:8],
            'more_may_remain':sent['more_may_remain'] or received['scan_limit_hit'] or remaining==0 or
                              received['download_attempts']>=remaining or metadata['metadata_more']}
