"""Durable AI result cache and review workflow.

Results are keyed by file metadata and model identity. Manually reviewed tags are
never overwritten by automation. Cache entries contain tags, not image pixels.
"""
from __future__ import annotations
import json
from pathlib import Path


def signature(path: str | Path) -> str:
    """Cheap change signature; full file checksums are handled by library_tools."""
    stat = Path(path).stat()
    return f'{stat.st_size}:{stat.st_mtime_ns}'


def migrate(con) -> None:
    con.executescript('''
        CREATE TABLE IF NOT EXISTS ai_cache (
            photo_id INTEGER NOT NULL REFERENCES photos(id) ON DELETE CASCADE,
            engine TEXT NOT NULL, model TEXT NOT NULL, signature TEXT NOT NULL,
            result_json TEXT NOT NULL, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(photo_id, engine, model)
        );
        CREATE INDEX IF NOT EXISTS idx_ai_cache_engine ON ai_cache(engine,model);
    ''')
    existing = {r[1] for r in con.execute('PRAGMA table_info(photos)')}
    for name, spec in {
        'ai_confidence': 'REAL',
        'ai_review': "TEXT NOT NULL DEFAULT 'unreviewed'",
        'ai_updated_at': 'TEXT',
        'ai_error': "TEXT NOT NULL DEFAULT ''",
    }.items():
        if name not in existing:
            con.execute(f'ALTER TABLE photos ADD COLUMN {name} {spec}')


def get(con, photo_id: int, engine: str, model: str, file_sig: str):
    row = con.execute('''SELECT result_json, signature FROM ai_cache
                         WHERE photo_id=? AND engine=? AND model=?''',
                      (photo_id, engine, model)).fetchone()
    if row and row['signature'] == file_sig:
        return json.loads(row['result_json'])
    return None


def store(con, photo_id: int, engine: str, model: str, file_sig: str, result: dict):
    con.execute('''INSERT INTO ai_cache(photo_id,engine,model,signature,result_json)
        VALUES(?,?,?,?,?) ON CONFLICT(photo_id,engine,model) DO UPDATE SET
        signature=excluded.signature,result_json=excluded.result_json,
        updated_at=CURRENT_TIMESTAMP''',
        (photo_id,engine,model,file_sig,json.dumps(result)))


def apply(con, photo_id: int, result: dict, engine_label: str, *, allow_location=False):
    row = con.execute('SELECT ai_source,ai_review,location_source,location FROM photos WHERE id=?',
                      (photo_id,)).fetchone()
    if not row or row['ai_source'] == 'Manual' or row['ai_review'] == 'approved':
        return False
    location = row['location']
    location_source = row['location_source']
    if allow_location and result.get('location') and location_source not in ('GPS area hint','Manual'):
        location, location_source = result['location'], 'Cloud AI suggestion'
    confidence = result.get('activity_score') or result.get('score') or None
    con.execute('''UPDATE photos SET activities=?,attraction=?,location=?,location_source=?,
        ai_source=?,ai_confidence=?,ai_review='unreviewed',ai_updated_at=CURRENT_TIMESTAMP,
        ai_error='' WHERE id=?''',
        (json.dumps(result.get('activities',[])),result.get('attraction',''),location,
         location_source,engine_label,confidence,photo_id))
    return True


def review(con, photo_id: int, accepted: bool):
    con.execute('''UPDATE photos SET ai_review=?,
        ai_source=CASE WHEN ? THEN 'Manual' ELSE ai_source END WHERE id=?''',
        ('approved' if accepted else 'rejected',int(accepted),photo_id))
    con.commit()


def review_pending(con, limit=1000):
    return con.execute('''SELECT id,path,activities,attraction,ai_confidence,ai_source
        FROM photos WHERE ai_source LIKE '%suggestion' AND ai_review='unreviewed'
        ORDER BY id DESC LIMIT ?''',(limit,)).fetchall()
