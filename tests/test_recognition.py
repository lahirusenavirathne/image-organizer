"""AI workflow tests without downloading heavy ML models."""
import json
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from app import db, recognition


def test_tag_suggestions_include_plausible_activity_and_not_unjustified_landmark():
    found = recognition.suggest_tags(
        ['Beach leisure', 'Temple visit', 'Wildlife safari'],
        ['Sigiriya Rock Fortress', 'Yala National Park'],
        [0.225, 0.16, 0.14, 0.28, 0.275])
    assert found['activities'] == ['Beach leisure']
    assert found['attraction'] == ''  # very close landmark scores


def test_distinctive_landmark_suggestion():
    found = recognition.suggest_tags(
        ['Temple visit', 'Surfing'],
        ['Nine Arch Bridge', 'Galle Fort'],
        [0.24, 0.17, 0.36, 0.29])
    assert found['attraction'] == 'Nine Arch Bridge'
    assert found['activities'] == ['Temple visit']


def test_low_similarity_remains_uncertain():
    found = recognition.suggest_tags(['Wildlife safari'], ['Yala National Park'], [0.08, 0.12])
    assert found['activities'] == []
    assert found['attraction'] == ''


def test_local_classification_persists_and_keeps_manual_tags(tmp_path):
    folder = tmp_path / 'pics'
    folder.mkdir()
    for name in ('one.jpg','two.jpg','bad.jpg'):
        Image.new('RGB', (60, 60), 'orange').save(folder / name)
    dbfile=tmp_path/'db.sqlite'
    db.init(dbfile)
    assert db.scan_folder(dbfile, folder)['indexed']==3
    with db.connect(dbfile) as con:
        manual = con.execute("SELECT id FROM photos WHERE path LIKE '%two.jpg'").fetchone()['id']
        db.update_metadata(con,manual,location='Galle',activity_text='Surfing',attraction='',source_url='',artist='',copyright='',license='')
        ids = [x[0] for x in con.execute('SELECT id FROM photos ORDER BY id')]

    class StubRecognizer:
        def __init__(self, progress=None):
            if progress: progress('Stub loaded')
        def predict(self, path):
            if Path(path).name == 'bad.jpg':
                raise ValueError('file deliberately failed')
            return {'activities': ['Temple visit'], 'attraction':'Sigiriya Rock Fortress'}

    with patch.object(recognition, 'LocalRecognizer', StubRecognizer):
        result = recognition.run_local(dbfile, ids)
    assert result['tagged']==1
    assert result['skipped']==1
    assert result['with_activity']==1
    assert len(result['errors'])==1
    assert 'bad.jpg' in result['errors'][0]
    with db.connect(dbfile) as con:
        one=con.execute("SELECT * FROM photos WHERE path LIKE '%one.jpg'").fetchone()
        two=con.execute('SELECT * FROM photos WHERE id=?',(manual,)).fetchone()
        assert json.loads(one['activities'])==['Temple visit']
        assert one['attraction']=='Sigiriya Rock Fortress'
        assert one['ai_source']=='OpenCLIP suggestion'
        assert json.loads(two['activities'])==['Surfing']
        assert two['ai_source']=='Manual'


def test_ai_dependencies_missing_reported_clearly():
    with patch.object(recognition, 'local_ai_missing', return_value=['OpenCLIP']):
        try:
            recognition.LocalRecognizer()
        except RuntimeError as e:
            assert 'INSTALL_AI_WINDOWS.bat' in str(e)
        else:
            assert False, 'A missing AI runtime must fail with setup instructions'
