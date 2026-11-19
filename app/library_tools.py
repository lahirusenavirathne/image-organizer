"""Local duplicate detection, image quality signals and copyright review.

No file is deleted or moved as a consequence of similarity detection. Results
are advisory; visual perceptual hashes can match different-looking photographs.
"""
from __future__ import annotations
import hashlib
from collections import defaultdict
from pathlib import Path
from PIL import Image, ImageOps, ImageFilter, ImageStat
from .db import connect


def migrate(con):
    existing={r[1] for r in con.execute('PRAGMA table_info(photos)')}
    for key,definition in {
        'checksum':'TEXT NOT NULL DEFAULT \'\'',
        'dhash':'TEXT NOT NULL DEFAULT \'\'',
        'quality_score':'REAL',
        'analysis_signature':'TEXT NOT NULL DEFAULT \'\'',
        'rights_status':"TEXT NOT NULL DEFAULT 'Unknown'",
    }.items():
        if key not in existing:
            con.execute(f'ALTER TABLE photos ADD COLUMN {key} {definition}')
    con.execute('CREATE INDEX IF NOT EXISTS idx_photos_checksum ON photos(checksum)')
    con.execute('CREATE INDEX IF NOT EXISTS idx_photos_rights ON photos(rights_status)')


def hash_file(path: Path) -> str:
    digest=hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda:handle.read(1024*1024),b''):
            digest.update(block)
    return digest.hexdigest()


def image_signals(path: Path):
    with Image.open(path) as opened:
        image=ImageOps.exif_transpose(opened).convert('RGB')
        gray=ImageOps.grayscale(image)
        small=gray.resize((9,8),Image.Resampling.LANCZOS)
        pixels=list(small.getdata())
        flags=[pixels[y*9+x] > pixels[y*9+x+1] for y in range(8) for x in range(8)]
        bitset=sum(int(bit) << i for i,bit in enumerate(flags))
        # Sharpness proxy: variance of edges, normalized to an approximate 0-100 score.
        reduced=gray.copy();reduced.thumbnail((800,800))
        v=ImageStat.Stat(reduced.filter(ImageFilter.FIND_EDGES)).var[0]
        quality=round(min(100.,max(0.,v/15.)),1)
    return f'{bitset:016x}', quality


def analyze_library(db_path, ids=None, progress=None):
    done=skipped=0;errors=[]
    with connect(db_path) as con:
        if ids is None:
            photos=con.execute('SELECT id,path,analysis_signature FROM photos ORDER BY id').fetchall()
        else:
            photos=[]
            for pid in dict.fromkeys(ids):
                row=con.execute('SELECT id,path,analysis_signature FROM photos WHERE id=?',(pid,)).fetchone()
                if row:photos.append(row)
        for n,row in enumerate(photos,1):
            src=Path(row['path'])
            try:
                stat=src.stat();sig=f'{stat.st_size}:{stat.st_mtime_ns}'
                if row['analysis_signature']==sig:
                    skipped+=1;continue
                checksum=hash_file(src)
                dhash,quality=image_signals(src)
                con.execute('''UPDATE photos SET checksum=?,dhash=?,quality_score=?,
                               analysis_signature=? WHERE id=?''',(checksum,dhash,quality,sig,row['id']))
                done+=1
                if done%25==0:con.commit()
            except Exception as exc:
                if len(errors)<12:errors.append(f'{src.name}: {exc}')
            if progress and (n%25==0 or n==len(photos)):
                progress(f'Quality/duplicate scan {n}/{len(photos)}; {done} analyzed')
        con.commit()
    return {'analyzed':done,'cached':skipped,'errors':errors}


def exact_duplicates(con):
    groups=con.execute('''SELECT checksum,COUNT(*) count FROM photos
             WHERE checksum!='' GROUP BY checksum HAVING COUNT(*)>1 ORDER BY count DESC''').fetchall()
    return [[dict(row) for row in con.execute('SELECT id,path FROM photos WHERE checksum=? ORDER BY id',
                    (item['checksum'],)).fetchall()] for item in groups]


def similar_pairs(con, max_distance=4, limit=300):
    """Locality-sensitive buckets avoid comparing every pair in a large library.

    With eight 8-bit segments, photos <= 4 bits apart must share a segment.
    """
    rows=con.execute("SELECT id,path,dhash FROM photos WHERE dhash!='' ORDER BY id").fetchall()
    buckets=defaultdict(list)
    for row in rows:
        value=int(row['dhash'],16)
        for segment in range(8):
            buckets[(segment,(value>>(segment*8)) & 0xff)].append((row['id'],row['path'],value))
    seen=set();pairs=[]
    for choices in buckets.values():
        for i,(left_id,left_path,left_hash) in enumerate(choices):
            for right_id,right_path,right_hash in choices[i+1:]:
                key=(left_id,right_id)
                if key in seen:continue
                seen.add(key)
                distance=(left_hash^right_hash).bit_count()
                if distance<=max_distance:
                    pairs.append({'photo_1':left_path,'photo_2':right_path,'distance':distance})
                    if len(pairs)>=limit:return pairs
    return pairs


def set_rights(con, photo_id: int, status: str):
    if status not in ('Unknown','Verified','Permission required'):
        raise ValueError('Invalid copyright verification status')
    con.execute('UPDATE photos SET rights_status=? WHERE id=?',(status,photo_id))
    con.commit()
