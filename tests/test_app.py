import csv
import json
import sqlite3
from pathlib import Path
from PIL import Image
import numpy as np
import pytest
from app import db
from app.catalog import gps_hint
from app.metadata import read_image
from app.operations import safe_part, preview_moves, execute_moves, undo_last_batch, export_photos, unique_path

@pytest.fixture
def library(tmp_path):
    src=tmp_path/'import'
    src.mkdir()
    one=src/'sigiriya.jpg'
    two=src/'random.jpg'
    Image.new('RGB',(160,90),(230,180,100)).save(one)
    Image.new('RGB',(90,160),(30,40,100)).save(two)
    catalog=tmp_path/'appdata'/'photos.db'
    db.init(catalog)
    stats=db.scan_folder(catalog,src)
    assert stats['indexed']==2
    return catalog,src,one,two

def test_catalog_import_rescan_and_provenance(library):
    database,folder,one,two=library
    with db.connect(database) as con:
        rows=con.execute('SELECT * FROM photos').fetchall()
        assert len(rows)==2
        assert rows[0]['width']>0
        pid=rows[0]['id']
        db.update_metadata(con,pid,location='Sigiriya',activity_text='Hiking / trekking, Temple visit',
            attraction='Sigiriya Rock Fortress',source_url='https://example.com/photo',
            artist='Example Person',copyright='All rights reserved',license='Editorial only')
    again=db.scan_folder(database,folder)
    assert again['unchanged']==2
    with db.connect(database) as con:
        row=db.photo_by_id(con,pid)
        assert json.loads(row['activities'])==['Hiking / trekking','Temple visit']
        assert row['source_url']=='https://example.com/photo'
        assert row['artist']=='Example Person'
        assert row['ai_source']=='Manual'
        results,total=db.query_photos(con,search='Sigiriya')
        assert total>=1
        results,total=db.query_photos(con,activity='Temple visit')
        assert total==1

def test_move_preview_protected_undo_and_collision(library,tmp_path):
    database,folder,one,two=library
    with db.connect(database) as con:
        ids=[r['id'] for r in con.execute('SELECT id FROM photos ORDER BY id')]
        db.update_metadata(con,ids[0],location='Sigiriya',activity_text='Temple visit',
            attraction='',source_url='',artist='',copyright='',license='')
    dest=tmp_path/'organized';dest.mkdir()
    plan=preview_moves(database,ids,dest)
    assert len(plan)==2
    assert one.exists() and two.exists(), 'Preview must be read-only'
    assert any('Sigiriya' in p['destination'] for p in plan)
    result=execute_moves(database,plan)
    assert result['moved']==2
    assert not one.exists() and not two.exists()
    assert all(Path(p['destination']).exists() for p in plan)
    with db.connect(database) as con:
        assert con.execute('SELECT COUNT(*) FROM moves').fetchone()[0]==2
    undo=undo_last_batch(database)
    assert undo['restored']==2
    assert one.exists() and two.exists()
    assert undo_last_batch(database)['restored']==0
    collision=tmp_path/'collision.jpg';collision.write_bytes(b'existing')
    new=unique_path(collision)
    assert new.name=='collision_2.jpg' and collision.read_bytes()==b'existing'

def test_exports_are_exact_size_manifest_and_preserve_source(library,tmp_path):
    database,folder,one,two=library
    out=tmp_path/'web'
    with db.connect(database) as con:
        photo=con.execute('SELECT id FROM photos WHERE path=?',(str(one.resolve()),)).fetchone()['id']
        db.update_metadata(con,photo,location='Sigiriya',activity_text='Hiking / trekking',
            attraction='Sigiriya Rock Fortress',source_url='https://example.org/original',
            artist='Photographer',copyright='Copyright 2026',license='Licensed')
    result=export_photos(database,[photo],out,width=272,height=300,mode='Crop to fill',fmt='WEBP',quality=82)
    assert result['exported']==1
    images=list(out.glob('*.webp'))
    assert len(images)==1
    assert Image.open(images[0]).size==(272,300)
    assert one.exists(), 'Export must not move or overwrite originals'
    with open(result['manifest'],encoding='utf-8-sig') as f:
        entry=list(csv.DictReader(f))[0]
        assert entry['copyright']=='Copyright 2026'
        assert entry['photographer']=='Photographer'
        assert entry['source_url']=='https://example.org/original'
    result2=export_photos(database,[photo],out,width=300,height=300,mode='Pad to fit',fmt='JPEG',quality=75)
    assert result2['exported']==1
    assert Image.open(list(out.glob('*.jpg'))[0]).size==(300,300)
    result3=export_photos(database,[photo],out,width=400,height=0,mode='Crop to fill',fmt='PNG',quality=80)
    assert Image.open(list(out.glob('*.png'))[0]).size==(400,225)

def test_sanitizer_and_gps_hints():
    assert safe_part('../../..') not in ('','..','.')
    assert '/' not in safe_part('.. / unsafe / ..')
    assert safe_part('CON')=='_CON'
    assert gps_hint(7.957,80.760)=='Sigiriya'
    assert gps_hint(None,0)==''
    assert gps_hint(51.50,-0.12)==''

def test_changed_file_resets_automatic_tags_and_faces(library):
    database,folder,one,two=library
    with db.connect(database) as con:
        row=con.execute('SELECT * FROM photos WHERE path=?',(str(one.resolve()),)).fetchone()
        pid=row['id']
        vec=np.zeros((128,),dtype=np.float32);vec[0]=1
        gid=con.execute('INSERT INTO face_groups (centroid,n) VALUES (?,1)',(vec.tobytes(),)).lastrowid
        con.execute('INSERT INTO faces (photo_id,group_id,feature) VALUES (?,?,?)',(pid,gid,vec.tobytes()))
        con.execute("UPDATE photos SET ai_source='OpenCLIP',activities='[\"Wildlife safari\"]',face_processed=1,face_count=1 WHERE id=?",(pid,))
        con.commit()
    Image.new('RGB',(220,120),'red').save(one)
    result=db.scan_folder(database,folder)
    assert result['indexed']==1
    with db.connect(database) as con:
        updated=db.photo_by_id(con,pid)
        assert updated['face_processed']==0 and updated['face_count']==0
        assert updated['ai_source']=='' and updated['activities']=='[]'
        assert con.execute('SELECT COUNT(*) FROM faces').fetchone()[0]==0
        assert con.execute('SELECT COUNT(*) FROM face_groups').fetchone()[0]==0


def test_batch_filename_collision_is_resolved_before_move(tmp_path):
    photos=tmp_path/'photos'
    for sub in ('a','b'):
        (photos/sub).mkdir(parents=True)
        Image.new('RGB',(30,20),'blue').save(photos/sub/'same.jpg')
    data=tmp_path/'db.sqlite';db.init(data)
    assert db.scan_folder(data,photos)['indexed']==2
    with db.connect(data) as con:
        ids=[r['id'] for r in con.execute('SELECT id FROM photos')]
        for pid in ids:
            db.update_metadata(con,pid,location='Kandy',activity_text='Temple visit',
                attraction='',source_url='',artist='',copyright='',license='')
    dest=tmp_path/'organized';dest.mkdir()
    plan=preview_moves(data,ids,dest)
    assert len({p['destination'] for p in plan})==2
    assert {Path(p['destination']).name for p in plan}=={'same.jpg','same_2.jpg'}
    result=execute_moves(data,plan)
    assert result['moved']==2
    assert not result['errors']
