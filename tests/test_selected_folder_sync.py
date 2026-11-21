"""Folder-scoped desktop-to-web transfers. No DreamHost access needed."""
from __future__ import annotations
from pathlib import Path
import pytest
from app import db, drive, web_sync, folder_sync
from test_web_sync import FakeWeb, add_image


@pytest.fixture
def remote():
    fake=FakeWeb()
    yield fake
    fake.close()


class FolderClient(web_sync.ApiClient):
    """Folder API stand-in; photo uploads exercise the actual HTTP protocol."""
    def __init__(self, remote):
        super().__init__(remote.url, remote.token)
        self.remote=remote
        self.folders={}
        self.last_id=300

    def list_folders(self, parent_id=0):
        if parent_id and parent_id not in self.folders:
            raise web_sync.SyncError('Remote parent does not exist','missing')
        return [v for v in self.folders.values() if v['parent_id']==(parent_id or None)]

    def create_folder(self, name, parent_id=0):
        assert not any(x['name']==name and x['parent_id']==(parent_id or None)
                       for x in self.folders.values())
        self.last_id+=1
        row={'id':self.last_id,'name':name,'parent_id':parent_id or None}
        self.folders[self.last_id]=row
        return row


    def list_photos(self, folder_id, page=1):
        rows=[{'id':item['id'],'sha256':item['sha256'],
               'original_name':item['name'],'file_size':len(item.get('content',b'x'))}
              for item in self.remote.files.values() if item['folder_id']==folder_id]
        rows.sort(key=lambda r:r['id'],reverse=True)
        pages=max(1,(len(rows)+99)//100)
        page=min(page,pages)
        return {'data':rows[(page-1)*100:page*100],'meta':{'pages':pages}}

    def download_photo(self, remote_id, destination, expected_sha):
        import hashlib
        item=self.remote.files[remote_id]
        payload=item['content']
        assert hashlib.sha256(payload).hexdigest()==expected_sha
        assert not destination.exists()
        destination.parent.mkdir(parents=True,exist_ok=True)
        destination.write_bytes(payload)


def build(db_file, tmp_path):
    db.init(db_file)
    with db.connect(db_file) as con:
        travel=drive.create_folder(con,'Travel')
        yala=drive.create_folder(con,'Yala',travel)
        ella=drive.create_folder(con,'Ella',travel)
        misc=drive.create_folder(con,'Misc')
    ids={}
    for name,color,fid in [('yala.jpg',(220,10,20),yala),('ella.jpg',(10,220,20),ella),
                           ('misc.jpg',(10,20,220),misc),('root.jpg',(80,80,80),None)]:
        pid=add_image(tmp_path/name,color,db_file)
        ids[name]=pid
        if fid:
            with db.connect(db_file) as con:drive.move_photos(con,[pid],fid)
    return travel,yala,ella,misc,ids


def test_only_selected_folder_and_descendants_are_uploaded(remote,tmp_path):
    path=tmp_path/'catalog.db';travel,yala,ella,misc,ids=build(path,tmp_path)
    client=FolderClient(remote)
    a=folder_sync.sync_selected_folders(path,client,selected_ids=[travel])
    assert a['uploaded']==2 and a['in_scope_photos']==2
    assert remote.posts==2 and len(remote.files)==2
    remote_paths={c['id']:c['name'] for c in client.folders.values()}
    assert {row['name'] for row in remote.files.values()}=={'yala.jpg','ella.jpg'}
    for row in remote.files.values():
        assert remote_paths[row['folder_id']] in ('Yala','Ella')
    b=folder_sync.sync_selected_folders(path,client,selected_ids=[travel])
    assert b['uploaded']==0 and b['previously_completed']==2 and remote.posts==2
    # Selecting Misc later cannot cause previously unselected root images to sync.
    c=folder_sync.sync_selected_folders(path,client,selected_ids=[misc])
    assert c['uploaded']==1 and len(remote.files)==3
    assert 'root.jpg' not in {v['name'] for v in remote.files.values()}


def test_child_only_creates_ancestor_shell_not_ancestor_photos(remote,tmp_path):
    path=tmp_path/'catalog.db';travel,yala,ella,misc,ids=build(path,tmp_path)
    client=FolderClient(remote)
    a=folder_sync.sync_selected_folders(path,client,selected_ids=[yala])
    assert a['in_scope_photos']==1 and a['uploaded']==1
    assert [f['name'] for f in sorted(client.folders.values(),key=lambda x:x['id'])]==['Travel','Yala']
    assert remote.posts==1


def test_overlap_and_trash_never_expand_scope(remote,tmp_path):
    path=tmp_path/'catalog.db';travel,yala,ella,misc,ids=build(path,tmp_path)
    client=FolderClient(remote)
    with db.connect(path) as con:drive.trash_photos(con,[ids['ella.jpg']])
    plan=folder_sync.folder_selection(path,[travel,yala])
    assert len(plan['roots'])==1 and plan['photo_count']==1
    result=folder_sync.sync_selected_folders(path,client,selected_ids=[travel,yala])
    assert result['uploaded']==1
    with db.connect(path) as con:drive.trash_folder(con,misc)
    with pytest.raises(ValueError):folder_sync.sync_selected_folders(path,client,selected_ids=[misc])
    with pytest.raises(ValueError):folder_sync.folder_selection(path,[])
    assert remote.posts==1


def test_explicit_batches_continue_and_skip_successes(remote,tmp_path):
    path=tmp_path/'catalog.db';db.init(path)
    with db.connect(path) as con: fid=drive.create_folder(con,'Batch')
    for index in range(24):
        pid=add_image(tmp_path/f'{index:02d}.jpg',((index*10+1)%255,(index*27+3)%255,(index*13+5)%255),path)
        with db.connect(path) as con:drive.move_photos(con,[pid],fid)
    client=FolderClient(remote)
    first=folder_sync.sync_selected_folders(path,client,selected_ids=[fid])
    assert first['uploaded']==20 and first['more_may_remain'] and remote.posts==20
    second=folder_sync.sync_selected_folders(path,client,selected_ids=[fid])
    assert second['uploaded']==4 and second['previously_completed']==20 and remote.posts==24
    third=folder_sync.sync_selected_folders(path,client,selected_ids=[fid])
    assert third['uploaded']==0 and third['previously_completed']==24 and remote.posts==24


def test_remote_folder_collisions_and_invalid_selections_do_not_upload(remote,tmp_path):
    path=tmp_path/'catalog.db';travel,yala,ella,misc,ids=build(path,tmp_path)
    client=FolderClient(remote)
    client.folders[301]={'id':301,'name':'Travel','parent_id':None}
    client.folders[302]={'id':302,'name':'Travel','parent_id':None}
    with pytest.raises(web_sync.SyncError):folder_sync.sync_selected_folders(path,client,selected_ids=[travel])
    assert remote.posts==0
    for ids_ in ([True],[0],[99999]):
        with pytest.raises(ValueError):folder_sync.folder_selection(path,ids_)


def test_web_only_photo_downloads_into_selected_tree(remote,tmp_path):
    import hashlib
    from PIL import Image
    path=tmp_path/'catalog.db';travel,yala,ella,misc,ids=build(path,tmp_path)
    client=FolderClient(remote)
    folder_sync.sync_selected_folders(path,client,selected_ids=[yala])
    remote_yala=next(x['id'] for x in client.folders.values() if x['name']=='Yala')
    source=tmp_path/'web_only.jpg';Image.new('RGB',(37,36),(30,80,165)).save(source)
    raw=source.read_bytes()
    remote.files[999]={'id':999,'sha256':hashlib.sha256(raw).hexdigest(),
                       'name':'from-web.jpg','folder_id':remote_yala,'content':raw}
    downloaded=folder_sync.download_selected_folders(path,client,selected_ids=[yala])
    assert downloaded['downloaded']==1
    assert downloaded['remote_already_local']>=1  # original yala photo uploaded earlier
    with db.connect(path) as con:
        photos=con.execute('SELECT * FROM photos WHERE display_name=?',('from-web.jpg',)).fetchall()
        assert len(photos)==1 and photos[0]['folder_id']==yala
        assert Path(photos[0]['path']).read_bytes()==raw
    again=folder_sync.download_selected_folders(path,client,selected_ids=[yala])
    assert again['downloaded']==0 and again['remote_already_local']>=1
    assert 'misc.jpg' not in {x['name'] for x in remote.files.values()}


def test_remote_added_descendant_stays_under_selected_root(remote,tmp_path):
    import hashlib
    from PIL import Image
    path=tmp_path/'catalog.db';travel,yala,ella,misc,ids=build(path,tmp_path)
    client=FolderClient(remote)
    folder_sync.sync_selected_folders(path,client,selected_ids=[yala])
    remote_yala=next(x['id'] for x in client.folders.values() if x['name']=='Yala')
    sub=client.create_folder('Web added',remote_yala)
    source=tmp_path/'cloud.jpg';Image.new('RGB',(20,22),(90,78,65)).save(source)
    raw=source.read_bytes()
    remote.files[998]={'id':998,'sha256':hashlib.sha256(raw).hexdigest(),
                       'name':'cloud.jpg','folder_id':sub['id'],'content':raw}
    x=folder_sync.download_selected_folders(path,client,selected_ids=[yala])
    assert x['downloaded']==1
    with db.connect(path) as con:
        subrow=con.execute("SELECT * FROM desktop_folders WHERE name='Web added'").fetchone()
        assert subrow['parent_id']==yala
        image=con.execute("SELECT * FROM photos WHERE display_name='cloud.jpg'").fetchone()
        assert image['folder_id']==subrow['id']


def test_no_remote_downloads_from_unselected_siblings(remote,tmp_path):
    import hashlib
    from PIL import Image
    path=tmp_path/'catalog.db';travel,yala,ella,misc,ids=build(path,tmp_path)
    client=FolderClient(remote)
    folder_sync.sync_selected_folders(path,client,selected_ids=[yala])
    other=client.create_folder('Misc')
    source=tmp_path/'remote_sibling.jpg';Image.new('RGB',(22,28),(33,33,66)).save(source)
    raw=source.read_bytes()
    remote.files[997]={'id':997,'sha256':hashlib.sha256(raw).hexdigest(),
                       'name':'remote-sibling.jpg','folder_id':other['id'],'content':raw}
    result=folder_sync.download_selected_folders(path,client,selected_ids=[yala])
    assert result['downloaded']==0
    with db.connect(path) as con:
        assert not con.execute("SELECT * FROM photos WHERE display_name='remote-sibling.jpg'").fetchone()


def test_combined_two_way_transfer_only_selected_folders(remote,tmp_path):
    import hashlib
    from PIL import Image
    path=tmp_path/'catalog.db';travel,yala,ella,misc,ids=build(path,tmp_path)
    client=FolderClient(remote)
    # An explicitly chosen local child is the sole transfer boundary.
    a=folder_sync.sync_selected_folder_trees(path,client,selected_ids=[yala])
    assert a['uploaded']==1 and a['downloaded']==0
    yala_remote=next(f['id'] for f in client.folders.values() if f['name']=='Yala')
    cloud=tmp_path/'new_cloud.jpg';Image.new('RGB',(41,47),(66,77,88)).save(cloud)
    raw=cloud.read_bytes()
    remote.files[777]={'id':777,'name':'cloud-added.jpg',
                       'sha256':hashlib.sha256(raw).hexdigest(),
                       'folder_id':yala_remote,'content':raw}
    b=folder_sync.sync_selected_folder_trees(path,client,selected_ids=[yala])
    assert b['uploaded']==0 and b['downloaded']==1
    c=folder_sync.sync_selected_folder_trees(path,client,selected_ids=[yala])
    assert c['downloaded']==0 and c['uploaded']==0
    assert {f['name'] for f in remote.files.values()}=={'yala.jpg','cloud-added.jpg'}
    with db.connect(path) as con:
        assert con.execute("SELECT COUNT(*) FROM web_sync_jobs WHERE state='done'").fetchone()[0]==2
        assert con.execute("SELECT COUNT(*) FROM web_sync_downloads").fetchone()[0]==1
        assert con.execute("SELECT COUNT(*) FROM photos WHERE folder_id=? AND deleted_at IS NULL",(misc,)).fetchone()[0]==1


def test_api_download_verifies_sha_and_refuses_overwrite(tmp_path):
    import hashlib
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from PIL import Image
    source=tmp_path/'remote.jpg'
    Image.new('RGB',(35,45),(70,90,160)).save(source)
    content=source.read_bytes()
    token='glpm_v1_'+'b'*64
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_GET(self):
            if self.headers.get('Authorization')!='Bearer '+token:
                self.send_response(401);self.end_headers();return
            self.send_response(200);self.send_header('Content-Type','image/jpeg')
            self.send_header('Content-Length',str(len(content)));self.end_headers()
            self.wfile.write(content)
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    runner=threading.Thread(target=server.serve_forever,daemon=True);runner.start()
    try:
        client=web_sync.ApiClient(f'http://127.0.0.1:{server.server_port}',token)
        target=tmp_path/'saved'/'remote.jpg'
        client.download_photo(35,target,hashlib.sha256(content).hexdigest())
        assert target.read_bytes()==content
        with pytest.raises(web_sync.SyncError):
            client.download_photo(35,target,hashlib.sha256(content).hexdigest())
        assert target.read_bytes()==content
        target.unlink()
        with pytest.raises(web_sync.SyncError):
            client.download_photo(35,target,'f'*64)
        assert not target.exists()
    finally:
        server.shutdown();server.server_close();runner.join(timeout=3)
