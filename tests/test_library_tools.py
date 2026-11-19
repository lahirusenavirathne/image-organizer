from PIL import Image
from app import db
from app.library_tools import analyze_library, exact_duplicates, similar_pairs, set_rights


def test_duplicates_and_rights(tmp_path):
    folder=tmp_path/'photos';folder.mkdir()
    for name,color in [('a.jpg','red'),('b.jpg','red'),('c.jpg','blue')]:
        Image.new('RGB',(80,60),color).save(folder/name)
    database=tmp_path/'db.sqlite';db.init(database)
    assert db.scan_folder(database,folder)['indexed']==3
    assert analyze_library(database)['analyzed']==3
    assert analyze_library(database)['cached']==3
    with db.connect(database) as con:
        groups=exact_duplicates(con)
        assert len(groups)==1 and len(groups[0])==2
        assert similar_pairs(con,max_distance=0)
        row=con.execute('SELECT id FROM photos LIMIT 1').fetchone()
        set_rights(con,row['id'],'Verified')
        assert db.photo_by_id(con,row['id'])['rights_status']=='Verified'


def test_rights_invalid(tmp_path):
    database=tmp_path/'db.sqlite';db.init(database)
    with db.connect(database) as con:
        try: set_rights(con,1,'Public domain inferred by AI')
        except ValueError: pass
        else: raise AssertionError('Unsupported status accepted')
