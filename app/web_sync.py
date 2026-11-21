"""Explicit, one-way desktop -> DreamHost transfer, safe for private photo libraries.

Uses only HTTPS JSON/multipart API v1. Each photo is a retryable checkpoint;
there is no background polling, server-to-desktop deletion, or live mirroring.
Secrets are never written to SQLite, debug logs, or configuration files.
"""
from __future__ import annotations
import hashlib
import json
import mimetypes
import re
import ssl
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Callable

MAX_UPLOAD = 25 * 1024 * 1024
TOKEN_RE = re.compile(r'^glpm_v1_[0-9a-f]{64}$')
SUPPORTED_MIMES = {'.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png', '.webp': 'image/webp'}
SERVICE_PREFIX = 'GuiaLankaPhotoManager:WebAPI:'


class SyncError(Exception):
    def __init__(self, message: str, code: str = 'error', status: int = 0):
        super().__init__(message)
        self.code, self.status = code, status


def api_url(text: str) -> str:
    """Normalize origin to the fixed API endpoint; don't follow untrusted paths."""
    url = (text or '').strip()
    parts = urllib.parse.urlsplit(url)
    if not parts.hostname or parts.username or parts.password or parts.query or parts.fragment:
        raise ValueError('Enter a website origin, such as https://photos.guialankatours.com')
    if parts.scheme != 'https' and not (parts.scheme == 'http' and parts.hostname in ('localhost', '127.0.0.1')):
        raise ValueError('HTTPS is required for the photo web API')
    if parts.path.rstrip('/') not in ('', '/api/v1/index.php'):
        raise ValueError('Use the website origin or its /api/v1/index.php endpoint')
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc.lower(), '/api/v1/index.php', '', ''))


def host_origin(endpoint: str) -> str:
    p = urllib.parse.urlsplit(api_url(endpoint))
    return f'{p.scheme}://{p.netloc}'


def validate_token(token: str) -> str:
    if not isinstance(token, str) or not TOKEN_RE.fullmatch(token.strip()):
        raise ValueError('API token format is invalid. Create a write token in the web Account page.')
    return token.strip()


def credential_service(endpoint: str) -> str:
    return SERVICE_PREFIX + host_origin(endpoint)


def _keyring():
    try:
        import keyring
        return keyring
    except ImportError as exc:
        raise SyncError('Secure credential storage is unavailable. Run INSTALL_WINDOWS.bat to install keyring.', 'keyring_missing') from exc


def remember_token(endpoint: str, token: str) -> None:
    # On Windows keyring uses the Windows Credential Manager, not plaintext files.
    try:
        _keyring().set_password(credential_service(endpoint), 'api-token', validate_token(token))
    except Exception as exc:
        raise SyncError('Could not save the API token in secure storage.', 'keyring_failed') from exc


def saved_token(endpoint: str) -> str:
    try:
        return _keyring().get_password(credential_service(endpoint), 'api-token') or ''
    except Exception:
        return ''


def forget_token(endpoint: str) -> None:
    try:
        _keyring().delete_password(credential_service(endpoint), 'api-token')
    except Exception:
        pass


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never allow Authorization to be forwarded to a redirected host.
        return None


class ApiClient:
    def __init__(self, endpoint: str, token: str, timeout: int = 45):
        self.endpoint = api_url(endpoint)
        self.token = validate_token(token)
        self.timeout = timeout
        self.opener = urllib.request.build_opener(
            _NoRedirect(), urllib.request.HTTPSHandler(context=ssl.create_default_context()))

    def request(self, method: str, *, resource: str = 'me', action: str = '',
                values: dict | None = None, body: dict | None = None,
                payload: bytes | None = None, content_type: str = 'application/json') -> dict:
        query = {'resource': resource}
        if action: query['action'] = action
        if values: query.update(values)
        url = self.endpoint + '?' + urllib.parse.urlencode(query)
        if body is not None:
            payload = json.dumps(body, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
        headers = {'Authorization': 'Bearer '+self.token, 'Accept': 'application/json'}
        if payload is not None: headers['Content-Type'] = content_type
        req = urllib.request.Request(url, data=payload, headers=headers, method=method)
        try:
            with self.opener.open(req, timeout=self.timeout) as response:
                if int(response.status) not in (200, 201):
                    raise SyncError(f'API returned HTTP {response.status}', 'http', response.status)
                data = response.read(160 * 1024)
        except urllib.error.HTTPError as exc:
            try:
                obj = json.loads(exc.read(8192).decode('utf-8', 'replace'))
                detail = obj.get('error') or {}
                code = str(detail.get('code') or 'http_error')
                if exc.code in (401,403): message = 'Web API access denied: check token scope, account and expiry.'
                elif exc.code == 429: message = 'Web API request limit reached. Try resuming later.'
                elif exc.code == 409: message = 'Remote filename conflict; photo was not overwritten.'
                else: message = str(detail.get('message') or f'HTTP {exc.code}')[:180]
            except Exception:
                code, message = 'http_error', f'Web server returned HTTP {exc.code}'
            raise SyncError(message, code, exc.code) from None
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as exc:
            # Never put exception objects or token-bearing request details in logs.
            raise SyncError('Connection interrupted or server unavailable. Pending photos can be retried.', 'network') from None
        try:
            return json.loads(data)
        except (ValueError, UnicodeDecodeError):
            raise SyncError('Server returned an invalid JSON response.', 'response') from None

    def me(self) -> dict:
        return self.request('GET',resource='me')['data']

    def preflight(self, name: str, sha256: str, size: int, folder_id: int = 0) -> dict:
        return self.request('POST',resource='sync',action='preflight',body={
            'name': name, 'sha256': sha256, 'file_size': size,
            'folder_id': folder_id if folder_id else None})['data']

    def upload(self, path: Path, name: str, sha256: str, folder_id: int = 0) -> dict:
        """Single-photo transfer. Upload retries are idempotent on the server."""
        ext = path.suffix.lower()
        if ext not in SUPPORTED_MIMES:
            raise SyncError('Web edition accepts only JPEG, PNG or WebP.', 'unsupported')
        if path.stat().st_size > MAX_UPLOAD:
            raise SyncError('Web edition accepts files up to 25 MiB.', 'too_large')
        if '\r' in name or '\n' in name or '"' in name or '/' in name or '\\' in name:
            raise SyncError('Filename contains unsupported characters.', 'filename')
        boundary = 'glpm-' + uuid.uuid4().hex
        def field(key: str, value: str) -> bytes:
            return (f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n').encode('utf-8')
        prefix = field('folder_id', str(folder_id) if folder_id else 'root') + field('sha256', sha256)
        prefix += (f'--{boundary}\r\nContent-Disposition: form-data; name="photo"; filename="{name}"\r\n'
                   f'Content-Type: {SUPPORTED_MIMES[ext]}\r\n\r\n').encode('utf-8')
        # At most 25MiB, bounded by the server's existing validated upload limit.
        body = prefix + path.read_bytes() + f'\r\n--{boundary}--\r\n'.encode('ascii')
        return self.request('POST',resource='photos',payload=body,
                            content_type=f'multipart/form-data; boundary={boundary}')['data']


def file_hash(path: Path) -> str:
    digest=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024),b''): digest.update(chunk)
    return digest.hexdigest()


def migrate(con):
    con.execute('''CREATE TABLE IF NOT EXISTS web_sync_jobs (
        photo_id INTEGER NOT NULL,
        server_url TEXT NOT NULL,
        folder_id INTEGER NOT NULL DEFAULT 0,
        sha256 TEXT NOT NULL,
        size_bytes INTEGER NOT NULL,
        mtime_ns INTEGER NOT NULL,
        state TEXT NOT NULL DEFAULT 'queued',
        remote_id INTEGER,
        last_error TEXT NOT NULL DEFAULT '',
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY(photo_id,server_url,folder_id)
    )''')
    con.execute('CREATE INDEX IF NOT EXISTS idx_web_sync_state ON web_sync_jobs(server_url,folder_id,state)')


def jobs_pending(con, endpoint: str, folder_id: int, limit: int = 20) -> list[int]:
    migrate(con)
    return [int(row[0]) for row in con.execute('''SELECT photo_id FROM web_sync_jobs
        WHERE server_url=? AND folder_id=? AND state IN ('queued','failed','uploading')
        ORDER BY updated_at ASC LIMIT ?''', (api_url(endpoint),folder_id,limit))]


def _upsert(con, photo_id: int, endpoint: str, folder_id: int, sha: str, size: int, modified: int):
    con.execute('''INSERT INTO web_sync_jobs(photo_id,server_url,folder_id,sha256,size_bytes,mtime_ns,state)
        VALUES(?,?,?,?,?,?,'queued')
        ON CONFLICT(photo_id,server_url,folder_id) DO UPDATE SET
        state=CASE WHEN web_sync_jobs.sha256<>excluded.sha256 OR web_sync_jobs.size_bytes<>excluded.size_bytes
            THEN 'queued' ELSE web_sync_jobs.state END,
        sha256=excluded.sha256,size_bytes=excluded.size_bytes,mtime_ns=excluded.mtime_ns,
        updated_at=CURRENT_TIMESTAMP''',(photo_id, endpoint, folder_id, sha,size,modified))


def _set_status(con,pid,endpoint,folder_id,state,remote_id=None,error=''):
    con.execute('''UPDATE web_sync_jobs SET state=?, remote_id=?, last_error=?,updated_at=CURRENT_TIMESTAMP
        WHERE photo_id=? AND server_url=? AND folder_id=?''',
        (state,remote_id,error[:240],pid,endpoint,folder_id))
    con.commit()


def upload_batch(db_path: Path, client: ApiClient, *, selected_ids: list[int] | None = None,
                 folder_id: int = 0, progress: Callable[[str],None] | None = None,
                 limit: int = 20) -> dict:
    """Upload up to 20 photos per explicit user action; leave failures in SQLite.

    No cloud-side delete, overwrite, metadata overwrite, or remote-to-local download.
    'Resume pending' retries whole photos (not byte chunks) after interruption.
    """
    from . import db
    if folder_id < 0:raise ValueError('Remote folder id cannot be negative')
    limit=max(1,min(20,int(limit)))
    if selected_ids is not None:
        ids=list(dict.fromkeys(int(i) for i in selected_ids))[:limit]
    else:
        with db.connect(db_path) as con: ids=jobs_pending(con,client.endpoint,folder_id,limit)
    result={'requested':len(ids),'uploaded':0,'already_on_web':0,'conflicts':0,
            'failed':0,'skipped':0,'examples':[]}
    for n,pid in enumerate(ids,1):
        if progress: progress(f'Web transfer {n}/{len(ids)} — no original files will be moved')
        with db.connect(db_path) as con:
            migrate(con)
            row=con.execute('''SELECT id,path,display_name,deleted_at FROM photos WHERE id=?''',(pid,)).fetchone()
            if row is None or row['deleted_at'] is not None:
                result['skipped']+=1
                continue
            path=Path(row['path']); name=(row['display_name'] or path.name)
            name=str(name).strip()
            if not name.lower().endswith(('.jpg','.jpeg','.png','.webp')):
                name=path.name
            if not path.is_file():
                result['failed']+=1
                if len(result['examples'])<8:result['examples'].append(f'Photo {pid}: source no longer exists')
                continue
            size=path.stat().st_size
            if size<1 or size>MAX_UPLOAD or path.suffix.lower() not in SUPPORTED_MIMES:
                result['skipped']+=1
                if len(result['examples'])<8:result['examples'].append(f'{path.name}: unsupported file or over 25 MiB')
                continue
            sha=file_hash(path); stat=path.stat()
            _upsert(con,pid,client.endpoint,folder_id,sha,size,stat.st_mtime_ns)
            con.commit()
            previous=con.execute('''SELECT state,sha256,size_bytes FROM web_sync_jobs
                WHERE photo_id=? AND server_url=? AND folder_id=?''',
                (pid,client.endpoint,folder_id)).fetchone()
            if previous['state']=='done' and selected_ids is None:
                result['already_on_web']+=1;continue
            _set_status(con,pid,client.endpoint,folder_id,'uploading')
        try:
            status=client.preflight(name,sha,size,folder_id)
            decision=status.get('decision')
            if decision=='duplicate':
                result['already_on_web']+=1
                state='done'
                remote_id=int(status['remote_id'])
            elif decision=='conflict':
                result['conflicts']+=1
                state='conflict';remote_id=int(status['remote_id'])
            elif decision=='upload':
                # Catch modifications occurring between hash/preflight and upload.
                if path.stat().st_size != size or file_hash(path) != sha:
                    raise SyncError('Local photo changed during transfer; retry it.', 'changed')
                uploaded=client.upload(path,name,sha,folder_id)
                remote_id=int(uploaded['id'])
                state='done'
                if uploaded.get('decision')=='duplicate':result['already_on_web']+=1
                else:result['uploaded']+=1
            else:
                raise SyncError('Unexpected preflight response.', 'response')
            with db.connect(db_path) as con:_set_status(con,pid,client.endpoint,folder_id,state,remote_id)
            if state=='conflict' and len(result['examples'])<8:
                result['examples'].append(f'{name}: name already used by a different image; no overwrite')
        except (SyncError,ValueError,OSError) as exc:
            result['failed']+=1
            code=getattr(exc,'code','local')
            message=str(exc) if isinstance(exc,SyncError) else 'Local file changed or could not be read.'
            with db.connect(db_path) as con:_set_status(con,pid,client.endpoint,folder_id,'failed',error=message)
            if len(result['examples'])<8:result['examples'].append(f'{name}: {message}')
            # Authorization and rate limits should not generate N duplicate failures.
            if code in ('unauthorized','forbidden','rate_limit') or getattr(exc,'status',0) in (401,403,429):
                break
    return result
