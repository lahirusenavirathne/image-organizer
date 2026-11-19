import json
from pathlib import Path
from unittest.mock import patch

from PIL import Image
from app import db, recognition


def test_top_candidates_available_when_all_tags_rejected():
    result = recognition.suggest_tags(
        ['Wildlife safari', 'Elephant watching'],
        ['Nine Arch Bridge', 'Ramboda Falls'],
        [0.12, 0.09, 0.17, 0.15])
    assert result['activities'] == []
    assert result['attraction'] == ''
    assert result['activity_candidates'][0] == {'name': 'Wildlife safari', 'similarity': 0.12}
    assert result['attraction_candidates'][0]['name'] == 'Nine Arch Bridge'
    assert 'threshold' in result['activity_reason']
    assert 'margin' in result['attraction_reason']


def test_reports_distinguish_cached_empty_protected_and_refreshed(tmp_path):
    photos = tmp_path / 'input'
    photos.mkdir()
    for name in ['empty.jpg', 'manual.jpg']:
        Image.new('RGB', (25, 25), 'purple').save(photos / name)
    db_path = tmp_path / 'photos.db'
    db.init(db_path)
    db.scan_folder(db_path, photos)
    with db.connect(db_path) as con:
        ids = {Path(row['path']).name: row['id'] for row in con.execute('SELECT * FROM photos')}
        db.update_metadata(con, ids['manual.jpg'], location='Ella', activity_text='Trekking',
                           attraction='', source_url='', artist='', copyright='', license='')

    class StubRecognizer:
        calls = 0
        def __init__(self, progress=None):
            pass
        def predict(self, path):
            StubRecognizer.calls += 1
            return recognition.suggest_tags(['Wildlife safari'], ['Ramboda Falls'], [0.12, 0.17])

    selected = list(ids.values())
    with patch.object(recognition, 'LocalRecognizer', StubRecognizer):
        first = recognition.run_local(db_path, selected)
        assert first['tagged'] == 1 and first['unmatched'] == 1 and first['skipped'] == 1
        assert StubRecognizer.calls == 1
        summary = recognition.format_local_report(first)
        assert 'No accepted tags' in summary
        assert 'Skipped: manually reviewed' in summary
        assert 'Wildlife safari (0.120)' in summary
        second = recognition.run_local(db_path, selected)
        assert second['cached'] == 1 and StubRecognizer.calls == 1
        assert '(cached)' in recognition.format_local_report(second)
        third = recognition.run_local(db_path, selected, force=True)
        assert third['cached'] == 0 and StubRecognizer.calls == 2
    with db.connect(db_path) as con:
        manual = db.photo_by_id(con, ids['manual.jpg'])
        assert manual['location'] == 'Ella'
        assert json.loads(manual['activities']) == ['Trekking']
