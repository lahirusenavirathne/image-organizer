"""HTTP integration with a local fake web API; no DreamHost or API key required."""
from __future__ import annotations
import hashlib
import json
import sqlite3
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit, parse_qs
from PIL import Image
import pytest
from app import db
from app import web_sync


class FakeWeb:
    def __init__(self):
        self.files = {}
        self.next_id = 1
        self.posts = 0
        self.drop_first_response = False
        self.dropped = False
        state = self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):pass
            def send(self,status,obj):
                raw=json.dumps({'data':obj}).encode()
                self.send_response(status);self.send_header('Content-Type','application/json')
                self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
            def do_GET(self):
                if self.headers.get('Authorization') != 'Bearer '+state.token:
                    self.send(401,{'error':{'code':'unauthorized'}});return
                self.send(200,{'scope':'write','role':'admin','email':'test@example.invalid'})
            def do_POST(self):
                if self.headers.get('Authorization') != 'Bearer '+state.token:
                    self.send(401,{'error':{'code':'unauthorized'}});return
                args=parse_qs(urlsplit(self.path).query)
                data=self.rfile.read(int(self.headers.get('Content-Length',0)))
                if args.get('resource') == ['sync']:
                    obj=json.loads(data)
                    key=int(obj.get('folder_id') or 0)
                    candidates=[row for row in state.files.values() if row['folder_id']==key]
                    exact=next((row for row in candidates if row['sha256']==obj['sha256']),None)
                    conflict=next((row for row in candidates if row['name']==obj['name']),None)
                    row=exact or conflict
                    self.send(200,{'decision':'duplicate' if exact else 'conflict' if conflict else 'upload',
                                   'remote_id':row['id'] if row else None, 'remote_sha256':row['sha256'] if row else None})
                    return
                if args.get('resource') == ['photos']:
                    state.posts+=1
                    # extract fields by boundary and minimal MIME parsing for tests only
                    import re
                    chunks=data.split(b'Content-Disposition: form-data;')
                    sha=re.search(rb'name="sha256"\s*\r\n\r\n([a-f0-9]{64})',data).group(1).decode()
                    name=re.search(rb'name="photo"; filename="([^"]+)"',data).group(1).decode()
                    folder=re.search(rb'name="folder_id"\s*\r\n\r\n(root|\d+)',data).group(1).decode()
                    fid=int(folder) if folder!='root' else 0
                    end_boundary=data.split(b'Content-Type: image/',1)[1]
                    payload=end_boundary.split(b'\r\n\r\n',1)[1].split(b'\r\n--glpm-',1)[0]
                    assert hashlib.sha256(payload).hexdigest()==sha
                    # server would detect same hash even if client response lost
                    exact=next((row for row in state.files.values() if row['sha256']==sha and row['folder_id']==fid),None)
                    if exact: self.send(200,{'id':exact['id'],'decision':'duplicate'});return
                    row={'id':state.next_id,'sha256':sha,'name':name,'folder_id':fid}
                    state.files[state.next_id]=row;state.next_id+=1
                    if state.drop_first_response and not state.dropped:
                        state.dropped=True;self.close_connection=True
                        return
                    self.send(201,{'id':row['id'],'decision':'uploaded'})
            def do_PATCH(self):self.send(405,{})
        self.token='glpm_v1_'+'a'*64
        self.http=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        self.thread=threading.Thread(target=self.http.serve_forever,daemon=True);self.thread.start()
        self.url=f'http://127.0.0.1:{self.http.server_address[1]}'
    def close(self):
        self.http.shutdown();self.http.server_close();self.thread.join(timeout=3)


@pytest.fixture
def fake_web():
    server=FakeWeb()
    yield server
    server.close()


def add_image(path: Path, color, db_path: Path):
    from app.metadata import read_image
    path.parent.mkdir(parents=True,exist_ok=True)
    Image.new('RGB',(40,40),color).save(path)
    with db.connect(db_path) as con:
        db.upsert(con,read_image(path))
        return con.execute('SELECT id FROM photos WHERE path=?',(str(path.resolve()),)).fetchone()[0]


def test_rejects_insecure_and_untrusted_endpoints():
    for bad in ['http://example.com','https://x.tld@other.com',
                'https://example.com/?token=bad','https://example.com/other',
                'https://example.com/#fragment','https://evil.example.com/a/b']:
        with pytest.raises(ValueError):web_sync.api_url(bad)
    assert web_sync.api_url('https://photos.guialankatours.com/')=='https://photos.guialankatours.com/api/v1/index.php'
    with pytest.raises(ValueError):web_sync.validate_token('not-a-token')


def test_upload_dedup_and_local_checkpoint(fake_web,tmp_path):
    database=tmp_path/'library.db';db.init(database)
    id1=add_image(tmp_path/'one.jpg',(200,10,20),database)
    client=web_sync.ApiClient(fake_web.url,fake_web.token)
    assert client.me()['scope']=='write'
    a=web_sync.upload_batch(database,client,selected_ids=[id1])
    assert a['uploaded']==1 and fake_web.posts==1
    b=web_sync.upload_batch(database,client,selected_ids=[id1])
    assert b['already_on_web']==1 and fake_web.posts==1
    with db.connect(database) as con:
        row=con.execute('SELECT * FROM web_sync_jobs').fetchone()
        assert row['state']=='done' and row['remote_id']==1
        assert fake_web.token not in str(dict(row))


def test_retry_after_lost_upload_response_is_idempotent(fake_web,tmp_path):
    database=tmp_path/'library.db';db.init(database)
    id1=add_image(tmp_path/'broken.jpg',(7,180,40),database)
    client=web_sync.ApiClient(fake_web.url,fake_web.token,timeout=5)
    fake_web.drop_first_response=True
    a=web_sync.upload_batch(database,client,selected_ids=[id1])
    assert a['failed']==1 and len(fake_web.files)==1
    b=web_sync.upload_batch(database,client,selected_ids=None)
    assert b['already_on_web']==1 and b['failed']==0 and len(fake_web.files)==1
    assert fake_web.posts==1


def test_same_name_new_pixels_reports_conflict(fake_web,tmp_path):
    database=tmp_path/'library.db';db.init(database)
    p1=add_image(tmp_path/'a'/'same.jpg',(2,3,4),database)
    p2=add_image(tmp_path/'b'/'same.jpg',(20,30,40),database)
    client=web_sync.ApiClient(fake_web.url,fake_web.token)
    assert web_sync.upload_batch(database,client,selected_ids=[p1])['uploaded']==1
    result=web_sync.upload_batch(database,client,selected_ids=[p2])
    assert result['conflicts']==1
    assert fake_web.posts==1 and len(fake_web.files)==1
    with db.connect(database) as con:
        assert con.execute('SELECT state FROM web_sync_jobs WHERE photo_id=?',(p2,)).fetchone()[0]=='conflict'


def test_non_image_and_deleted_photos_never_upload(fake_web,tmp_path):
    database=tmp_path/'library.db';db.init(database)
    pid=add_image(tmp_path/'photo.jpg',(120,40,40),database)
    with db.connect(database) as con:con.execute('UPDATE photos SET deleted_at=CURRENT_TIMESTAMP WHERE id=?',(pid,))
    result=web_sync.upload_batch(database,web_sync.ApiClient(fake_web.url,fake_web.token),selected_ids=[pid])
    assert result['skipped']==1 and fake_web.posts==0
