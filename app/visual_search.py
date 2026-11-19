"""Local visual similarity and user-curated reference examples.

Three distinct signals are reported without conflating their meaning:
  * SHA-256: exact, byte-for-byte duplicate;
  * 64-bit dHash: likely same image after resizing/recompression (verify visually);
  * OpenCLIP cosine similarity: related visual content, not proof of identity.

No files are moved/deleted, and image pixels never leave the computer.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

from . import ai_cache
from .db import connect
from .recognition import MODEL, WEIGHTS, local_ai_missing
from .library_tools import color_distance

VISUAL_MODEL = f"{MODEL}:{WEIGHTS}:image-embedding-v1"
REFERENCE_KINDS = ('Attraction', 'Activity', 'Location')


def migrate(con):
    con.executescript('''
        CREATE TABLE IF NOT EXISTS visual_embeddings (
          photo_id INTEGER PRIMARY KEY REFERENCES photos(id) ON DELETE CASCADE,
          model TEXT NOT NULL,
          signature TEXT NOT NULL,
          dimensions INTEGER NOT NULL,
          vector BLOB NOT NULL,
          updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_visual_embeddings_model ON visual_embeddings(model);
        CREATE TABLE IF NOT EXISTS visual_references (
          photo_id INTEGER PRIMARY KEY REFERENCES photos(id) ON DELETE CASCADE,
          kind TEXT NOT NULL,
          label TEXT NOT NULL,
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
    ''')


class VisualEmbedder:
    """OpenCLIP loads only when the user starts indexing visual images."""

    def __init__(self, progress=None):
        missing = local_ai_missing()
        if missing:
            raise RuntimeError('Local AI missing: ' + ', '.join(missing)
                               + '. Run INSTALL_AI_WINDOWS.bat first.')
        if progress:
            progress('Loading local OpenCLIP model for image similarity...')
        try:
            import torch
            import open_clip
            self.torch = torch
            self.model, _, self.preprocess = open_clip.create_model_and_transforms(
                MODEL, pretrained=WEIGHTS, device='cpu')
            self.model.eval()
        except Exception as exc:
            raise RuntimeError('Cannot load visual similarity model: '
                               f'{type(exc).__name__}: {exc}') from exc

    def encode(self, path: str | Path) -> np.ndarray:
        with Image.open(path) as src:
            tensor = self.preprocess(ImageOps.exif_transpose(src).convert('RGB')).unsqueeze(0)
        with self.torch.inference_mode():
            result = self.model.encode_image(tensor)
            result = result / result.norm(dim=-1, keepdim=True).clamp(min=1e-8)
        return result[0].cpu().numpy().astype(np.float32, copy=False)


def _normalized_vector(vec) -> np.ndarray:
    arr = np.asarray(vec, dtype=np.float32).reshape(-1)
    if arr.size < 2 or arr.size > 8192 or not np.all(np.isfinite(arr)):
        raise ValueError('Invalid or non-finite visual embedding')
    norm = float(np.linalg.norm(arr))
    if norm < 1e-8:
        raise ValueError('Cannot store zero visual embedding')
    return np.ascontiguousarray(arr / norm, dtype=np.float32)


def store_embedding(con, photo_id: int, path: str | Path, vector,
                    model: str = VISUAL_MODEL):
    arr = _normalized_vector(vector)
    signature = ai_cache.signature(path)
    con.execute('''INSERT INTO visual_embeddings(photo_id,model,signature,dimensions,vector)
        VALUES(?,?,?,?,?) ON CONFLICT(photo_id) DO UPDATE SET
        model=excluded.model,signature=excluded.signature,
        dimensions=excluded.dimensions,vector=excluded.vector,
        updated_at=CURRENT_TIMESTAMP''',
        (photo_id, model, signature, arr.size, arr.tobytes()))


def indexed_count(con, model: str = VISUAL_MODEL):
    return con.execute('SELECT COUNT(*) FROM visual_embeddings WHERE model=?',
                       (model,)).fetchone()[0]


def index_visuals(db_path: Path, ids=None, progress=None, *, force=False,
                  embedder_factory=None):
    """Resumeable index; recomputes only changed/unindexed images by default."""
    indexed = cached = 0
    errors = []
    embedder_factory = embedder_factory or VisualEmbedder
    # Compute and cache exact hashes and perceptual hashes at the same time.
    # This separates pixel-level duplicates from semantic OpenCLIP matches.
    from .library_tools import analyze_library
    hash_report = analyze_library(db_path, ids=ids, progress=progress)
    with connect(db_path) as con:
        if ids is None:
            rows = con.execute('''SELECT p.id,p.path,e.signature,e.model
                FROM photos p LEFT JOIN visual_embeddings e ON e.photo_id=p.id
                ORDER BY p.id''').fetchall()
        else:
            unique = list(dict.fromkeys(ids))
            rows = [con.execute('''SELECT p.id,p.path,e.signature,e.model FROM photos p
                LEFT JOIN visual_embeddings e ON e.photo_id=p.id WHERE p.id=?''',
                (pid,)).fetchone() for pid in unique]
            rows = [row for row in rows if row]
        pending = []
        for row in rows:
            try:
                signature = ai_cache.signature(row['path'])
                if not force and row['model'] == VISUAL_MODEL and row['signature'] == signature:
                    cached += 1
                    continue
                pending.append(row)
            except Exception as exc:
                if len(errors) < 20:
                    errors.append(f'{Path(row["path"]).name}: {exc}')
        if progress:
            progress(f'Visual index: {cached} existing, {len(pending)} photos to analyze')
        model = embedder_factory(progress) if pending else None
        for n, row in enumerate(pending, 1):
            try:
                store_embedding(con, row['id'], row['path'], model.encode(row['path']))
                indexed += 1
            except Exception as exc:
                if len(errors) < 20:
                    errors.append(f'{Path(row["path"]).name}: {type(exc).__name__}: {exc}')
            if n % 20 == 0:
                con.commit()
            if progress and (n <= 3 or n % 25 == 0 or n == len(pending)):
                progress(f'Visual index {n}/{len(pending)} | {indexed} new, {cached} reused')
        con.commit()
    return {'indexed': indexed, 'cached': cached,
            'hashed': hash_report['analyzed'], 'hash_cached': hash_report['cached'],
            'failed': len(errors) + len(hash_report['errors']),
            'errors': hash_report['errors'] + errors, 'total': len(rows)}


def _vector_from_row(row):
    if not row or not row['vector']:
        return None
    dim = row['dimensions']
    if not 2 <= dim <= 8192 or len(row['vector']) != 4 * dim:
        return None
    vector = np.frombuffer(row['vector'], dtype=np.float32)
    if not np.all(np.isfinite(vector)):
        return None
    return vector


def set_reference(con, photo_id: int, kind: str, label: str):
    if kind not in REFERENCE_KINDS:
        raise ValueError('Reference kind must be Attraction, Activity or Location')
    label = label.strip()
    if not label or len(label) > 120:
        raise ValueError('Reference label must contain 1-120 characters')
    if not con.execute('SELECT 1 FROM photos WHERE id=?', (photo_id,)).fetchone():
        raise ValueError('Reference photo does not exist')
    con.execute('''INSERT INTO visual_references(photo_id,kind,label)
        VALUES(?,?,?) ON CONFLICT(photo_id) DO UPDATE SET kind=excluded.kind,label=excluded.label''',
        (photo_id, kind, label))
    con.commit()


def find_similar(con, photo_id: int, *, limit=30,
                 visual_threshold=0.60, max_hash_distance=5,
                 references_only=False):
    """Rank exact copies, likely edits, and visually related images.

    Cosine scores are *not* recognition probabilities, and visual lookalikes
    must never be automatically given an attraction or copyright label.
    """
    if not 1 <= limit <= 100:
        raise ValueError('limit must be between 1 and 100')
    original = con.execute('''SELECT p.*,e.vector,e.dimensions,e.model,e.signature
        FROM photos p LEFT JOIN visual_embeddings e ON e.photo_id=p.id
        WHERE p.id=?''', (photo_id,)).fetchone()
    if original is None:
        raise ValueError('Selected image was not found in the library')
    query_vector = _vector_from_row(original) if original['model'] == VISUAL_MODEL else None
    if query_vector is not None:
        try:
            if original['signature'] != ai_cache.signature(original['path']):
                query_vector = None
        except OSError:
            query_vector = None
    sql = '''SELECT p.id,p.path,p.dhash,p.checksum,p.location,p.attraction,
        e.vector,e.dimensions,e.model,e.signature,p.color_mean,
        r.kind AS reference_kind,r.label AS reference_label
        FROM photos p
        LEFT JOIN visual_embeddings e ON e.photo_id=p.id
        LEFT JOIN visual_references r ON r.photo_id=p.id
        WHERE p.id!=?'''
    if references_only:
        sql += ' AND r.photo_id IS NOT NULL'
    rows = con.execute(sql, (photo_id,)).fetchall()
    results = []
    left_hash = int(original['dhash'], 16) if original['dhash'] else None
    for row in rows:
        exact = bool(original['checksum'] and row['checksum']
                     and original['checksum'] == row['checksum'])
        distance = None
        if original['dhash'] and row['dhash']:
            try:
                distance = (left_hash ^ int(row['dhash'], 16)).bit_count()
            except ValueError:
                pass
        cosine = None
        if (query_vector is not None and row['model'] == VISUAL_MODEL
                and row['dimensions'] == len(query_vector)):
            candidate = _vector_from_row(row)
            if candidate is not None:
                cosine = max(-1.0, min(1.0, float(np.dot(query_vector, candidate))))
        likely_edit = (distance is not None and distance <= max_hash_distance
                       and (not original['color_mean'] or not row['color_mean']
                            or color_distance(original['color_mean'],row['color_mean']) <= 80))
        if exact:
            relationship = 'Exact duplicate'
            tier = 0
        elif likely_edit:
            relationship = 'Likely edited copy (verify)'
            tier = 1
        elif cosine is not None and cosine >= visual_threshold:
            relationship = 'Visually similar (verify)'
            tier = 2
        else:
            continue
        results.append({
            'id': row['id'], 'path': row['path'],
            'relationship': relationship, 'cosine': cosine,
            'hash_distance': distance, 'reference_kind': row['reference_kind'],
            'reference_label': row['reference_label'],
            'location': row['location'], 'attraction': row['attraction'],
            '_tier': tier,
        })
    results.sort(key=lambda x: (x['_tier'], -(x['cosine'] if x['cosine'] is not None else -2),
                                x['hash_distance'] if x['hash_distance'] is not None else 100, x['id']))
    for row in results:
        row.pop('_tier')
    return results[:limit]


def match_reference_examples(con, photo_id: int, *, limit=20):
    """Return nearest manually curated reference images, even if uncertain.

    No threshold means users can inspect nearest examples and reject them;
    never persist a guessed tag without explicit confirmation.
    """
    query = con.execute('''SELECT p.path,e.vector,e.dimensions,e.model,e.signature
        FROM photos p JOIN visual_embeddings e ON p.id=e.photo_id WHERE p.id=?''',
        (photo_id,)).fetchone()
    if not query or query['model'] != VISUAL_MODEL:
        raise RuntimeError('Index the selected photo before matching references.')
    if query['signature'] != ai_cache.signature(query['path']):
        raise RuntimeError('Selected photo changed. Rebuild its visual index.')
    v = _vector_from_row(query)
    if v is None:
        raise RuntimeError('Selected photo has an invalid visual embedding.')
    rows = con.execute('''SELECT p.id,p.path,r.kind,r.label,e.vector,e.dimensions,e.model
        FROM visual_references r JOIN photos p ON p.id=r.photo_id
        JOIN visual_embeddings e ON e.photo_id=p.id WHERE p.id!=?''', (photo_id,)).fetchall()
    result = []
    for row in rows:
        if row['model'] != VISUAL_MODEL or row['dimensions'] != v.size:
            continue
        other = _vector_from_row(row)
        if other is None:
            continue
        result.append({'id': row['id'], 'path': row['path'],
                       'relationship': 'Reference example (review)',
                       'cosine': float(np.clip(np.dot(v, other), -1.0, 1.0)),
                       'hash_distance': None, 'reference_kind': row['kind'],
                       'reference_label': row['label']})
    return sorted(result, key=lambda row: -row['cosine'])[:limit]


def apply_reference(con, photo_id: int, reference_id: int):
    """User-confirmed label transfer only; never automatic."""
    ref = con.execute('SELECT kind,label FROM visual_references WHERE photo_id=?',
                      (reference_id,)).fetchone()
    if not ref:
        raise ValueError('Reference no longer exists')
    row = con.execute('SELECT id,activities FROM photos WHERE id=?', (photo_id,)).fetchone()
    if not row:
        raise ValueError('Target photo no longer exists')
    kind, label = ref['kind'], ref['label']
    if kind == 'Attraction':
        con.execute("UPDATE photos SET attraction=?,ai_source='Manual',ai_review='approved' WHERE id=?",
                    (label, photo_id))
    elif kind == 'Activity':
        import json
        activities = json.loads(row['activities'] or '[]')
        if label not in activities:
            activities.append(label)
        con.execute("UPDATE photos SET activities=?,ai_source='Manual',ai_review='approved' WHERE id=?",
                    (json.dumps(activities), photo_id))
    elif kind == 'Location':
        con.execute("UPDATE photos SET location=?,location_source='Manual',ai_source='Manual',ai_review='approved' WHERE id=?",
                    (label, photo_id))
    else:
        raise ValueError('Unsupported reference kind')
    con.commit()
    return {'kind': kind, 'label': label}
