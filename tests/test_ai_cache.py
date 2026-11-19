import json
from PIL import Image
from app import db, ai_cache
from app.recognition import run_local, run_cloud
from unittest.mock import patch


def test_cache_and_manual_safety(tmp_path):
    image=tmp_path/'a.jpg';Image.new('RGB',(15,15),'green').save(image)
    database=tmp_path/'images.db';db.init(database);db.scan_folder(database,tmp_path)
    with db.connect(database) as con:
        row=con.execute('SELECT * FROM photos LIMIT 1').fetchone();pid=row['id']
        sig=ai_cache.signature(image)
        res={'activities':['Safari'],'attraction':'','activity_score':0.34}
        ai_cache.store(con,pid,'openclip','fake',sig,res)
        assert ai_cache.get(con,pid,'openclip','fake',sig)==res
        assert ai_cache.get(con,pid,'openclip','fake','changed') is None
        assert ai_cache.apply(con,pid,res,'OpenCLIP suggestion')
        assert json.loads(db.photo_by_id(con,pid)['activities']) == ['Safari']
        ai_cache.review(con,pid,True)
        assert not ai_cache.apply(con,pid,{'activities':[]},'OpenCLIP suggestion')


def test_local_reuses_cache_without_model(tmp_path):
    image=tmp_path/'a.jpg';Image.new('RGB',(15,15),'green').save(image)
    database=tmp_path/'images.db';db.init(database);db.scan_folder(database,tmp_path)
    with db.connect(database) as con:
        pid=con.execute('SELECT id FROM photos').fetchone()[0]
        ai_cache.store(con,pid,'openclip','ViT-B-32:laion2b_s34b_b79k',
                       ai_cache.signature(image),{'activities':['Safari'],'attraction':''})
    with patch('app.recognition.LocalRecognizer',side_effect=AssertionError('No model needed')):
        result=run_local(database,[pid])
    assert result['tagged']==1 and result['cached']==1


def test_cloud_reuses_cache_without_key_or_request(tmp_path):
    image=tmp_path/'a.jpg';Image.new('RGB',(15,15),'green').save(image)
    database=tmp_path/'images.db';db.init(database);db.scan_folder(database,tmp_path)
    with db.connect(database) as con:
        pid=con.execute('SELECT id FROM photos').fetchone()[0]
        ai_cache.store(con,pid,'openai','test-model',ai_cache.signature(image),
            {'activities':['Safari'],'attraction':'','location':''})
    with patch('app.recognition.cloud_predict',side_effect=AssertionError('No upload expected')):
        result=run_cloud(database,[pid],'','test-model')
    assert result['tagged']==1 and result['cached']==1
