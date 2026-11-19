"""Visual-match tests use deterministic fake embeddings, without cloud or model downloads."""
import json
import shutil

import numpy as np
import pytest
from PIL import Image

from app import db, visual_search


def build_library(tmp_path):
    folder = tmp_path / 'photographs'
    folder.mkdir()
    rng = np.random.default_rng(42)
    a = rng.integers(0, 256, size=(90, 120, 3), dtype=np.uint8)
    b = rng.integers(0, 256, size=(90, 120, 3), dtype=np.uint8)
    c = rng.integers(0, 256, size=(90, 120, 3), dtype=np.uint8)
    Image.fromarray(a).save(folder / 'sigiriya-a.png')
    shutil.copy2(folder / 'sigiriya-a.png', folder / 'sigiriya-exact.png')
    Image.fromarray(a).resize((60, 45)).save(folder / 'sigiriya-resized.png')
    Image.fromarray(b).save(folder / 'sigiriya-angle-b.png')
    Image.fromarray(c).save(folder / 'beach.png')
    database = tmp_path / 'photos.db'
    db.init(database)
    assert db.scan_folder(database, folder)['indexed'] == 5
    with db.connect(database) as con:
        ids = {row['path'].split('/')[-1]: row['id']
               for row in con.execute('SELECT id,path FROM photos')}
    return folder, database, ids


class StubEmbedder:
    calls = 0

    def __init__(self, progress=None):
        pass

    def encode(self, path):
        StubEmbedder.calls += 1
        name = str(path).split('/')[-1]
        if name == 'beach.png':
            return np.array([0, 1, 0], dtype=np.float32)
        if name == 'sigiriya-angle-b.png':
            return np.array([.90, .1, 0], dtype=np.float32)
        return np.array([1, 0, 0], dtype=np.float32)


def test_exact_resized_and_semantic_matches(tmp_path):
    folder, database, ids = build_library(tmp_path)
    StubEmbedder.calls = 0
    r = visual_search.index_visuals(database, embedder_factory=StubEmbedder)
    assert r['indexed'] == 5 and r['hashed'] == 5 and r['failed'] == 0
    assert StubEmbedder.calls == 5
    r2 = visual_search.index_visuals(database, embedder_factory=StubEmbedder)
    assert r2['cached'] == 5 and r2['hash_cached'] == 5
    assert StubEmbedder.calls == 5
    with db.connect(database) as con:
        assert visual_search.indexed_count(con) == 5
        matches = visual_search.find_similar(con, ids['sigiriya-a.png'], visual_threshold=0.6)
        by_name = {m['path'].split('/')[-1]: m for m in matches}
        assert by_name['sigiriya-exact.png']['relationship'] == 'Exact duplicate'
        assert by_name['sigiriya-resized.png']['relationship'] in (
            'Likely edited copy (verify)', 'Visually similar (verify)')
        assert by_name['sigiriya-angle-b.png']['cosine'] > .98
        assert 'beach.png' not in by_name
        assert matches[0]['relationship'] == 'Exact duplicate'


def test_changed_file_rebuilds_embedding(tmp_path):
    folder, database, ids = build_library(tmp_path)
    StubEmbedder.calls = 0
    visual_search.index_visuals(database, embedder_factory=StubEmbedder)
    # Reencode file with new size, so signature definitely changes.
    Image.new('RGB', (75, 75), 'yellow').save(folder / 'beach.png')
    r = visual_search.index_visuals(database, embedder_factory=StubEmbedder)
    assert r['indexed'] == 1 and r['cached'] == 4
    assert StubEmbedder.calls == 6


def test_references_are_manual_and_do_not_autotag(tmp_path):
    folder, database, ids = build_library(tmp_path)
    visual_search.index_visuals(database, embedder_factory=StubEmbedder)
    with db.connect(database) as con:
        visual_search.set_reference(con, ids['sigiriya-a.png'], 'Attraction', 'Sigiriya Rock Fortress')
        ranked = visual_search.match_reference_examples(con, ids['sigiriya-angle-b.png'])
        assert ranked and ranked[0]['reference_label'] == 'Sigiriya Rock Fortress'
        before = db.photo_by_id(con, ids['sigiriya-angle-b.png'])
        assert before['attraction'] != 'Sigiriya Rock Fortress'
        res = visual_search.apply_reference(con, ids['sigiriya-angle-b.png'], ranked[0]['id'])
        assert res == {'kind': 'Attraction', 'label': 'Sigiriya Rock Fortress'}
        after = db.photo_by_id(con, ids['sigiriya-angle-b.png'])
        assert after['attraction'] == 'Sigiriya Rock Fortress'
        assert after['ai_source'] == 'Manual'
        assert after['ai_review'] == 'approved'
        with pytest.raises(ValueError):
            visual_search.set_reference(con, ids['beach.png'], 'Copyright', 'Public domain')


def test_activity_reference_adds_tag_without_overwriting(tmp_path):
    folder, database, ids = build_library(tmp_path)
    with db.connect(database) as con:
        target=ids['beach.png']
        visual_search.set_reference(con, ids['sigiriya-a.png'], 'Activity', 'Hiking / trekking')
        con.execute('UPDATE photos SET activities=? WHERE id=?',(json.dumps(['Scenic train ride']), target))
        visual_search.apply_reference(con,target,ids['sigiriya-a.png'])
        tags=json.loads(db.photo_by_id(con,target)['activities'])
        assert tags == ['Scenic train ride','Hiking / trekking']


def test_ref_requires_usable_embedding(tmp_path):
    folder, database, ids = build_library(tmp_path)
    with db.connect(database) as con:
        visual_search.set_reference(con,ids['sigiriya-a.png'],'Location','Sigiriya')
        with pytest.raises(RuntimeError, match='Index'):
            visual_search.match_reference_examples(con,ids['beach.png'])


def test_cannot_store_bad_vectors(tmp_path):
    folder, database, ids=build_library(tmp_path)
    with db.connect(database) as con:
        with pytest.raises(ValueError):
            visual_search.store_embedding(con,ids['beach.png'],folder/'beach.png',[float('nan'),1])
        with pytest.raises(ValueError):
            visual_search.store_embedding(con,ids['beach.png'],folder/'beach.png',[0,0])


def test_perceptual_match_rejects_unrelated_flat_colors(tmp_path):
    folder = tmp_path / 'flat'
    folder.mkdir()
    Image.new('RGB', (90, 90), 'red').save(folder / 'red.png')
    Image.new('RGB', (90, 90), 'blue').save(folder / 'blue.png')
    database = tmp_path / 'photos.sqlite'
    db.init(database)
    db.scan_folder(database,folder)
    with db.connect(database) as con:
        red=con.execute("SELECT id FROM photos WHERE path LIKE '%red.png'").fetchone()[0]
    # dHash is identical for two solid colors, yet they should not be called
    # likely edited copies of each other.
    from app.library_tools import analyze_library
    analyze_library(database)
    with db.connect(database) as con:
        assert visual_search.find_similar(con,red) == []
