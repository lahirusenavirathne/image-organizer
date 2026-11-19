"""SQLite catalog; one connection per worker/thread. No network or image files stored in DB."""
from __future__ import annotations
import json
import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS photos (
 id INTEGER PRIMARY KEY, path TEXT NOT NULL UNIQUE, original_path TEXT NOT NULL,
 source_folder TEXT NOT NULL DEFAULT '', source_url TEXT NOT NULL DEFAULT '',
 width INTEGER, height INTEGER, mtime REAL, file_size INTEGER, camera TEXT DEFAULT '',
 artist TEXT DEFAULT '', copyright TEXT DEFAULT '', license TEXT DEFAULT '',
 gps_lat REAL, gps_lon REAL, taken_at TEXT DEFAULT '', location TEXT DEFAULT '',
 location_source TEXT DEFAULT '', activities TEXT NOT NULL DEFAULT '[]',
 attraction TEXT DEFAULT '', ai_source TEXT DEFAULT '', face_processed INTEGER DEFAULT 0,
 face_count INTEGER DEFAULT 0, added_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS face_groups (
 id INTEGER PRIMARY KEY, label TEXT NOT NULL DEFAULT '', centroid BLOB NOT NULL, n INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS faces (
 id INTEGER PRIMARY KEY, photo_id INTEGER NOT NULL REFERENCES photos(id) ON DELETE CASCADE,
 group_id INTEGER NOT NULL REFERENCES face_groups(id), feature BLOB NOT NULL
);
CREATE TABLE IF NOT EXISTS moves (
 id INTEGER PRIMARY KEY, photo_id INTEGER NOT NULL, previous_path TEXT NOT NULL,
 new_path TEXT NOT NULL, batch_id TEXT NOT NULL DEFAULT '', undone_at TEXT,
 moved_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_photos_location ON photos(location);
CREATE INDEX IF NOT EXISTS idx_photos_source_folder ON photos(source_folder);
CREATE INDEX IF NOT EXISTS idx_faces_group ON faces(group_id);
"""

def connect(path: Path) -> sqlite3.Connection:
    db = sqlite3.connect(str(path), timeout=30)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA journal_mode=WAL')
    db.execute('PRAGMA foreign_keys=ON')
    db.execute('PRAGMA busy_timeout=30000')
    return db

def init(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with connect(path) as con:
        con.executescript(SCHEMA)
        from .ai_cache import migrate
        migrate(con)
        from .library_tools import migrate as migrate_library
        migrate_library(con)

def upsert(con: sqlite3.Connection, meta: dict):
    # Retain manually adjusted categories, source and license on re-scan.
    cols = ('path','original_path','source_folder','source_url','width','height','mtime',
            'file_size','camera','artist','copyright','license','gps_lat','gps_lon',
            'taken_at','location','location_source')
    updates = ['width=excluded.width','height=excluded.height','mtime=excluded.mtime',
               'file_size=excluded.file_size','camera=excluded.camera','gps_lat=excluded.gps_lat',
               'gps_lon=excluded.gps_lon','taken_at=excluded.taken_at',
               "location=CASE WHEN photos.location_source='Manual' THEN photos.location ELSE excluded.location END",
               "location_source=CASE WHEN photos.location_source='Manual' THEN photos.location_source ELSE excluded.location_source END",
               "activities=CASE WHEN photos.ai_source='Manual' THEN photos.activities ELSE '[]' END",
               "attraction=CASE WHEN photos.ai_source='Manual' THEN photos.attraction ELSE '' END",
               "ai_source=CASE WHEN photos.ai_source='Manual' THEN photos.ai_source ELSE '' END",
               'face_processed=0','face_count=0']
    sql = f"INSERT INTO photos ({','.join(cols)}) VALUES ({','.join('?' for _ in cols)}) " \
          f"ON CONFLICT(path) DO UPDATE SET {','.join(updates)}"
    con.execute(sql, [meta.get(k) for k in cols])

def invalidate_faces(con: sqlite3.Connection, photo_id: int):
    """After a file changes, keep people groups consistent with remaining embeddings."""
    import numpy as np
    related=[r[0] for r in con.execute('SELECT DISTINCT group_id FROM faces WHERE photo_id=?',(photo_id,))]
    con.execute('DELETE FROM faces WHERE photo_id=?',(photo_id,))
    for gid in related:
        rows=con.execute('SELECT feature FROM faces WHERE group_id=?',(gid,)).fetchall()
        if not rows:
            con.execute('DELETE FROM face_groups WHERE id=?',(gid,))
            continue
        vectors=np.stack([np.frombuffer(r[0],dtype=np.float32) for r in rows])
        vector=vectors.mean(axis=0)
        vector/=max(float(np.linalg.norm(vector)),1e-8)
        con.execute('UPDATE face_groups SET centroid=?,n=? WHERE id=?',
                    (vector.astype(np.float32).tobytes(),len(rows),gid))


def scan_folder(db_path: Path, folder: Path, source_url: str = '', progress=None):
    from .metadata import image_paths, read_image
    found = done = failed = unchanged = 0
    failures = []
    with connect(db_path) as con:
        for path in image_paths(folder):
            found += 1
            try:
                rp = str(path.resolve())
                row = con.execute('SELECT id,mtime,file_size FROM photos WHERE path=?', (rp,)).fetchone()
                stat = path.stat()
                if row and row['mtime'] == stat.st_mtime and row['file_size'] == stat.st_size:
                    unchanged += 1
                    continue
                meta=read_image(path, source_url)
                if row: invalidate_faces(con, row['id'])
                upsert(con, meta)
                done += 1
                if done % 30 == 0: con.commit()
            except Exception as exc:
                failed += 1
                if len(failures) < 8: failures.append(f'{path.name}: {exc}')
            if progress and found % 25 == 0: progress(f'Scanned {found:,} files ({done:,} indexed)')
        con.commit()
    return {'found': found, 'indexed': done, 'unchanged': unchanged, 'failed': failed, 'examples': failures}

def photo_by_id(con, photo_id: int):
    return con.execute('SELECT * FROM photos WHERE id=?', (photo_id,)).fetchone()

def query_photos(con, search='', location='', activity='', group_id=None, offset=0, limit=120):
    where, args = ['1=1'], []
    if search:
        like = '%' + search.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'
        where.append("(path LIKE ? ESCAPE '\\' OR attraction LIKE ? ESCAPE '\\' OR activities LIKE ? ESCAPE '\\' OR source_url LIKE ? ESCAPE '\\' OR copyright LIKE ? ESCAPE '\\')")
        args += [like]*5
    if location: where.append('location=?'); args.append(location)
    if activity: where.append('activities LIKE ?'); args.append('%"'+activity+'"%')
    if group_id is not None:
        where.append('EXISTS (SELECT 1 FROM faces WHERE faces.photo_id=photos.id AND faces.group_id=?)')
        args.append(group_id)
    clause = ' AND '.join(where)
    total = con.execute('SELECT COUNT(*) FROM photos WHERE ' + clause, args).fetchone()[0]
    rows = con.execute('SELECT * FROM photos WHERE ' + clause + ' ORDER BY id DESC LIMIT ? OFFSET ?', args+[limit,offset]).fetchall()
    return rows, total

def update_metadata(con, photo_id, *, location, activity_text, attraction, source_url, artist, copyright, license):
    activities = [s.strip() for s in activity_text.split(',') if s.strip()]
    con.execute('''UPDATE photos SET location=?,location_source='Manual',activities=?,attraction=?,
               source_url=?,artist=?,copyright=?,license=?,ai_source='Manual' WHERE id=?''',
               (location.strip(), json.dumps(activities),attraction.strip(),source_url.strip(),
                artist.strip(),copyright.strip(),license.strip(),photo_id))
    con.commit()

def groups(con):
    return con.execute('''SELECT g.id,g.label,COUNT(DISTINCT f.photo_id) AS photos,g.n AS faces
                          FROM face_groups g JOIN faces f ON f.group_id=g.id
                          GROUP BY g.id ORDER BY photos DESC,g.id''').fetchall()

def ids_unprocessed(con):
    return [r[0] for r in con.execute('SELECT id FROM photos WHERE face_processed=0 ORDER BY id')]
