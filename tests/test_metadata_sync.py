"""Selected-folder metadata and hierarchy regressions (mock HTTP + SQLite)."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
from PIL import Image
from app import db, drive, folder_sync, web_sync, metadata_sync
from test_selected_folder_sync import FakeWeb, FolderClient, build

class MetadataClient(FolderClient):
    def get_photo(self, photo_id):
        item=self.remote.files[photo_id]
        return {'id':photo_id,'sha256':item['sha256'],'folder_id':item['folder_id'],
                'ai_status':item.get('ai_status','suggested'),
                **{field:item.get(field,('Unknown' if field=='rights_status' else ''))
                   for field in metadata_sync.SAFE_FIELDS}}

    def fill_metadata(self, photo_id, sha256, fields):
        item=self.remote.files[photo_id]
        assert item['sha256']==sha256
        updated=[];ignored=[]
        for field,value in fields.items():
            old=item.get(field,'Unknown' if field=='rights_status' else '')
            blank=not old or (field=='rights_status' and old=='Unknown')
            reviewed=item.get('ai_status')=='reviewed' and field in {'location','attraction','activities','rights_status'}
            if blank and not reviewed:
                item[field]=value;updated.append(field)
            else:ignored.append(field)
        return {'updated':updated,'ignored':ignored}


def remote_client():
    remote=FakeWeb()
    return remote,MetadataClient(remote)


def test_empty_local_subfolders_are_created_remotely(tmp_path):
    remote,client=remote_client()
    try:
        dbpath=tmp_path/'photo.db';db.init(dbpath)
        with db.connect(dbpath) as con:
            parent=drive.create_folder(con,'Yala');sub=drive.create_folder(con,'Empty child',parent)
        stats=folder_sync.sync_selected_folders(dbpath,client,selected_ids=[parent])
        assert stats['uploaded']==0 and stats['remote_folders_created']==2
        assert [(f['name'],f['parent_id']) for f in client.folders.values()]==[
            ('Yala',None),('Empty child',301)]
    finally:remote.close()


def test_empty_web_subfolders_are_imported_only_beneath_selected_root(tmp_path):
    remote,client=remote_client()
    try:
        dbpath=tmp_path/'photo.db';db.init(dbpath)
        with db.connect(dbpath) as con:
            yala=drive.create_folder(con,'Yala');other=drive.create_folder(con,'Other')
        folder_sync.sync_selected_folders(dbpath,client,selected_ids=[yala])
        remote_id=next(f['id'] for f in client.folders.values() if f['name']=='Yala')
        client.create_folder('Web empty',remote_id)
        client.create_folder('Not selected')
        folder_sync.download_selected_folders(dbpath,client,selected_ids=[yala])
        with db.connect(dbpath) as con:
            row=con.execute("SELECT parent_id FROM desktop_folders WHERE name='Web empty'").fetchone()
            assert row and row['parent_id']==yala
            assert con.execute("SELECT id FROM desktop_folders WHERE name='Not selected'").fetchone() is None
    finally:remote.close()


def test_upload_fills_empty_web_metadata_without_paths(tmp_path):
    remote,client=remote_client()
    try:
        dbpath=tmp_path/'photo.db';travel,yala,ella,misc,ids=build(dbpath,tmp_path)
        with db.connect(dbpath) as con:
            con.execute('''UPDATE photos SET location='Yala',activities=?,artist='Local photographer',
                rights_status='Verified',source_url='https://example.org/rights' WHERE id=?''',
                (json.dumps(['Safari','Nature walk']),ids['yala.jpg']))
        stats=folder_sync.sync_selected_folder_trees(dbpath,client,selected_ids=[yala])
        assert stats['uploaded']==1 and stats['metadata_web_updated']>=4
        remote_photo=next(x for x in remote.files.values() if x['name']=='yala.jpg')
        assert remote_photo['location']=='Yala'
        assert remote_photo['activities']=='Safari, Nature walk'
        assert remote_photo['photographer']=='Local photographer'
        assert remote_photo['rights_status']=='Verified'
        assert 'source_folder' not in remote_photo
        assert remote_photo['source_url']=='https://example.org/rights'
    finally:remote.close()


def test_web_metadata_imports_only_missing_local_values(tmp_path):
    remote,client=remote_client()
    try:
        dbpath=tmp_path/'photo.db';travel,yala,ella,misc,ids=build(dbpath,tmp_path)
        folder_sync.sync_selected_folders(dbpath,client,selected_ids=[yala])
        r=next(x for x in remote.files.values() if x['name']=='yala.jpg')
        r.update({'location':'Yala NP','photographer':'Remote author','rights_status':'Verified'})
        # The local photo has intentionally blank/nonmanual metadata.
        stats=metadata_sync.sync_selected_metadata(dbpath,client,selected_ids=[yala])
        assert stats['metadata_local_updated']==3 and stats['metadata_conflicts']==0
        with db.connect(dbpath) as con:
            p=con.execute('SELECT * FROM photos WHERE id=?',(ids['yala.jpg'],)).fetchone()
            assert p['location']=='Yala NP' and p['artist']=='Remote author' and p['rights_status']=='Verified'
            assert p['location_source']=='Web Sync'
    finally:remote.close()


def test_conflicts_remain_unmodified_and_reviewed_remains_protected(tmp_path):
    remote,client=remote_client()
    try:
        dbpath=tmp_path/'photo.db';travel,yala,ella,misc,ids=build(dbpath,tmp_path)
        folder_sync.sync_selected_folders(dbpath,client,selected_ids=[yala])
        r=next(x for x in remote.files.values() if x['name']=='yala.jpg')
        r.update({'location':'Remote location','attraction':'Remote attraction','ai_status':'reviewed'})
        with db.connect(dbpath) as con:
            con.execute("UPDATE photos SET location='Manual location',location_source='Manual', ai_source='Manual' WHERE id=?",(ids['yala.jpg'],))
        result=metadata_sync.sync_selected_metadata(dbpath,client,selected_ids=[yala])
        assert result['metadata_conflicts']>=2
        assert r['location']=='Remote location'
        with db.connect(dbpath) as con:
            row=con.execute('SELECT location,attraction FROM photos WHERE id=?',(ids['yala.jpg'],)).fetchone()
            assert row['location']=='Manual location' and not row['attraction']
    finally:remote.close()


def test_move_out_of_selected_scope_does_not_edit_unselected_remote_metadata(tmp_path):
    remote,client=remote_client()
    try:
        dbpath=tmp_path/'photo.db';travel,yala,ella,misc,ids=build(dbpath,tmp_path)
        folder_sync.sync_selected_folders(dbpath,client,selected_ids=[misc])
        remote_photo=next(x for x in remote.files.values() if x['name']=='misc.jpg')
        with db.connect(dbpath) as con:
            drive.move_photos(con,[ids['misc.jpg']],yala)
            con.execute("UPDATE photos SET location='Changed later' WHERE id=?",(ids['misc.jpg'],))
        result=metadata_sync.sync_selected_metadata(dbpath,client,selected_ids=[yala])
        assert result['metadata_conflicts']>=1 or result['metadata_failed']>=1
        assert 'location' not in remote_photo
    finally:remote.close()


def test_unselected_photo_never_gets_metadata_update(tmp_path):
    remote,client=remote_client()
    try:
        dbpath=tmp_path/'photo.db';travel,yala,ella,misc,ids=build(dbpath,tmp_path)
        folder_sync.sync_selected_folders(dbpath,client,selected_ids=[misc])
        remote_photo=next(x for x in remote.files.values() if x['name']=='misc.jpg')
        with db.connect(dbpath) as con:
            con.execute("UPDATE photos SET location='Not selected' WHERE id=?",(ids['misc.jpg'],))
        stats=metadata_sync.sync_selected_metadata(dbpath,client,selected_ids=[yala])
        assert stats['metadata_pairs']==0 and 'location' not in remote_photo
    finally:remote.close()


def test_unsafe_urls_and_existing_values_never_propagate():
    local={'source_url':'file:///C:/Private', 'location':'Yala','rights_status':'Unknown'}
    remote={'source_url':'','location':'Kandy','rights_status':'Verified'}
    result=metadata_sync.merge_plan(local,remote)
    assert result['conflicts']==['location']
    assert 'source_url' not in result['to_web']
    assert result['to_local']=={'rights_status':'Verified'}


def test_web_only_photo_metadata_is_restored_after_download(tmp_path):
    remote,client=remote_client()
    try:
        dbpath=tmp_path/'photo.db';travel,yala,ella,misc,ids=build(dbpath,tmp_path)
        folder_sync.sync_selected_folders(dbpath,client,selected_ids=[yala])
        remote_yala=next(x['id'] for x in client.folders.values() if x['name']=='Yala')
        source=tmp_path/'cloud-source.jpg';Image.new('RGB',(37,36),(30,80,165)).save(source)
        raw=source.read_bytes()
        remote.files[999]={'id':999,'sha256':hashlib.sha256(raw).hexdigest(),
                           'name':'cloud-metadata.jpg','folder_id':remote_yala,'content':raw,
                           'attraction':'Nine Arch Bridge','photographer':'Cloud photographer'}
        first=folder_sync.download_selected_folders(dbpath,client,selected_ids=[yala])
        assert first['downloaded']==1
        result=metadata_sync.sync_selected_metadata(dbpath,client,selected_ids=[yala],limit=10)
        assert result['metadata_local_updated']>=2
        with db.connect(dbpath) as con:
            row=con.execute("SELECT * FROM photos WHERE display_name='cloud-metadata.jpg'").fetchone()
            assert row['attraction']=='Nine Arch Bridge'
            assert row['artist']=='Cloud photographer'
            assert row['ai_source']=='Web Sync'
    finally:remote.close()


def test_web_metadata_survives_local_rescan(tmp_path):
    remote,client=remote_client()
    try:
        dbpath=tmp_path/'photo.db';travel,yala,ella,misc,ids=build(dbpath,tmp_path)
        folder_sync.sync_selected_folders(dbpath,client,selected_ids=[yala])
        record=next(x for x in remote.files.values() if x['name']=='yala.jpg')
        record['location']='Remote Yala'
        record['attraction']='Verified destination'
        metadata_sync.sync_selected_metadata(dbpath,client,selected_ids=[yala])
        with db.connect(dbpath) as con:
            original=con.execute('SELECT * FROM photos WHERE id=?',(ids['yala.jpg'],)).fetchone()
            assert original['location_source']=='Web Sync'
            assert original['ai_source']=='Web Sync'
            from app.metadata import read_image
            db.upsert(con,read_image(Path(original['path'])))
            after=con.execute('SELECT location,attraction FROM photos WHERE id=?',(ids['yala.jpg'],)).fetchone()
            assert after['location']=='Remote Yala' and after['attraction']=='Verified destination'
    finally:remote.close()
