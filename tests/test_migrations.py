from PIL import Image
from app import db


def test_existing_db_schema_upgrades_idempotently(tmp_path):
    path=tmp_path/'photos.db';db.init(path);db.init(path)
    with db.connect(path) as con:
        columns={x[1] for x in con.execute('PRAGMA table_info(photos)')}
        assert {'ai_confidence','ai_review','checksum','dhash','rights_status','quality_score'} <= columns
        assert con.execute("SELECT name FROM sqlite_master WHERE name='ai_cache'").fetchone()


def test_rescan_does_not_change_rights(tmp_path):
    image=tmp_path/'a.jpg';Image.new('RGB',(60,60),'blue').save(image)
    path=tmp_path/'photos.db';db.init(path);db.scan_folder(path,tmp_path)
    with db.connect(path) as con:
        photo_id=con.execute('SELECT id FROM photos').fetchone()[0]
        con.execute("UPDATE photos SET rights_status='Verified' WHERE id=?",(photo_id,))
    db.scan_folder(path,tmp_path)
    with db.connect(path) as con:
        assert db.photo_by_id(con,photo_id)['rights_status']=='Verified'
