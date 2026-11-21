"""Drive-compatible local catalog tests; source photos are never modified by Trash."""
from pathlib import Path
from PIL import Image
import pytest
from app import db, drive


def prepare(tmp_path):
    sources=tmp_path/'source_photos';sources.mkdir()
    (sources/'Ella').mkdir()
    Image.new('RGB',(48,35),(12,20,100)).save(sources/'sigiriya.jpg')
    Image.new('RGB',(40,51),(120,50,20)).save(sources/'Ella'/'nine_arch.jpg')
    appdata=tmp_path/'appdata'; database=appdata/'photos.db';db.init(database)
    return database,sources,appdata


def test_virtual_folders_import_and_search(tmp_path):
    database,sources,_=prepare(tmp_path)
    result=drive.import_tree(database,sources)
    assert result['indexed']==2 and result['failed']==0
    with db.connect(database) as con:
        root=con.execute('SELECT id FROM desktop_folders WHERE name=?',('source_photos',)).fetchone()['id']
        ella=drive.children(con,root)[0]
        assert ella['name']=='Ella'
        rows,total=drive.query_photos(con,view='folder',folder_id=ella['id'])
        assert total==1 and rows[0]['path'].endswith('nine_arch.jpg')
        rows,total=drive.query_photos(con,view='drive')
        assert total==0 # imported into a virtual source folder
        rows,total=drive.query_photos(con,search='nine_arch')
        assert total==1
    assert (sources/'sigiriya.jpg').exists()
    assert (sources/'Ella'/'nine_arch.jpg').exists()


def test_safe_move_rename_star_trash_restore_and_purge(tmp_path):
    database,sources,_=prepare(tmp_path)
    db.scan_folder(database,sources)
    with db.connect(database) as con:
        fid=drive.create_folder(con,'Wildlife')
        fid2=drive.create_folder(con,'Yala',fid)
        pid=con.execute('SELECT id FROM photos ORDER BY id LIMIT 1').fetchone()['id']
        original=Path(db.photo_by_id(con,pid)['path'])
        drive.move_photos(con,[pid],fid2)
        drive.set_photo_name(con,pid,'Yala elephant.jpg')
        drive.set_star(con,[pid],True)
        assert drive.query_photos(con,view='starred')[1]==1
        assert drive.query_photos(con,view='folder',folder_id=fid2)[1]==1
        assert db.photo_by_id(con,pid)['display_name']=='Yala elephant.jpg'
        assert db.photo_by_id(con,pid)['path']==str(original)
        drive.trash_photos(con,[pid]);con.commit()
    with db.connect(database) as con:
        assert drive.query_photos(con)[1]==1
        assert drive.query_photos(con,view='trash')[1]==1
        assert db.query_photos(con)[1]==1
        drive.restore_photos(con,[pid])
        assert drive.query_photos(con,view='trash')[1]==0
        drive.trash_photos(con,[pid]);drive.remove_catalog_records(con,[pid]);con.commit()
        assert db.photo_by_id(con,pid) is None
        assert original.exists() # Permanent catalog deletion DOES NOT delete source photograph.


def test_folder_cycle_and_duplicates_blocked(tmp_path):
    database,sources,_=prepare(tmp_path)
    with db.connect(database) as con:
        a=drive.create_folder(con,'A');b=drive.create_folder(con,'B',a)
        with pytest.raises(ValueError,match='inside itself'):drive.move_folder(con,a,b)
        with pytest.raises(ValueError,match='already exists'):drive.create_folder(con,'B',a)
        with pytest.raises(ValueError):drive.create_folder(con,'C/unsafe')
        drive.move_folder(con,b,None)
        assert drive.folder(con,b)['parent_id'] is None


def test_folder_trash_recovers_only_its_own_batch(tmp_path):
    database,sources,_=prepare(tmp_path)
    db.scan_folder(database,sources)
    with db.connect(database) as con:
        a=drive.create_folder(con,'Wildlife')
        b=drive.create_folder(con,'Yala',a)
        pids=[r['id'] for r in con.execute('SELECT id FROM photos ORDER BY id')]
        drive.move_photos(con,pids,a)
        drive.move_photos(con,[pids[-1]],b)
        drive.trash_photos(con,[pids[0]]) # Already in Trash before folder operation.
        drive.trash_folder(con,a)
        assert drive.query_photos(con,view='trash')[1]==2
        assert len(drive.all_folders(con,include_trashed=True))==2
        drive.restore_folder(con,a)
        # Previously trashed photo stays in Trash.
        assert drive.query_photos(con,view='trash')[1]==1
        assert drive.query_photos(con)[1]==1
        assert len(drive.all_folders(con,include_trashed=True))==0


def test_copy_is_managed_local_clone_preserving_original(tmp_path):
    database,sources,app_dir=prepare(tmp_path)
    db.scan_folder(database,sources)
    with db.connect(database) as con:
        pid=con.execute('SELECT id FROM photos ORDER BY id LIMIT 1').fetchone()['id']
        original=Path(db.photo_by_id(con,pid)['path'])
        dest=drive.create_folder(con,'Copies')
    result=drive.copy_photos(database,[pid],app_dir,dest)
    assert result['copied']==1 and not result['errors']
    with db.connect(database) as con:
        row=con.execute('SELECT * FROM photos WHERE copied_from_id=?',(pid,)).fetchone()
        assert row is not None and row['folder_id']==dest
        target=Path(row['path'])
        assert target.is_file() and target.parent==app_dir/'managed_copies'
        assert target.read_bytes()==original.read_bytes()
        assert row['display_name'].startswith('Copy of ')
    assert original.exists()


def test_restore_photo_whose_parent_is_still_trashed_goes_to_root(tmp_path):
    database,sources,_=prepare(tmp_path)
    db.scan_folder(database,sources)
    with db.connect(database) as con:
        a=drive.create_folder(con,'A')
        pid=con.execute('SELECT id FROM photos LIMIT 1').fetchone()['id']
        drive.move_photos(con,[pid],a)
        drive.trash_photos(con,[pid]);drive.trash_folder(con,a)
        drive.restore_photos(con,[pid])
        assert db.photo_by_id(con,pid)['folder_id'] is None


def test_trashed_child_remains_trashed_when_restoring_parent(tmp_path):
    database,_,_=prepare(tmp_path)
    with db.connect(database) as con:
        root=drive.create_folder(con,'Root')
        child=drive.create_folder(con,'Child',root)
        drive.trash_folder(con,child)
        drive.trash_folder(con,root)
        drive.restore_folder(con,root)
        assert drive.folder(con,root)['deleted_at'] is None
        with pytest.raises(ValueError):drive.folder(con,child)
        assert drive.folder(con,child,include_trash=True)['deleted_at'] is not None


def test_purge_folder_catalog_only_and_save_originals(tmp_path):
    database,sources,app_dir=prepare(tmp_path)
    db.scan_folder(database,sources)
    with db.connect(database) as con:
        root=drive.create_folder(con,'Root')
        pid=con.execute('SELECT id FROM photos ORDER BY id LIMIT 1').fetchone()['id']
        source=Path(db.photo_by_id(con,pid)['path'])
        drive.move_photos(con,[pid],root)
    result=drive.save_originals(database,[pid],app_dir/'exports')
    assert result['copied']==1
    with db.connect(database) as con:
        drive.trash_folder(con,root)
        result=drive.purge_folder(con,root)
        assert result['folders']==1 and result['catalog_records']==1
        assert db.photo_by_id(con,pid) is None
    assert source.exists()
    assert next((app_dir/'exports').iterdir()).read_bytes()==source.read_bytes()
