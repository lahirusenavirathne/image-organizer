"""Non-destructive, deliberately conservative photography adjustments.

The recipe is the only persistent edit. Export creates a *new* file with
exclusive creation: source bytes are never rewritten, moved, or deleted.
"""
from __future__ import annotations
import json
from pathlib import Path
from PIL import Image, ImageEnhance, ImageOps

RANGES = {
    'exposure': (-100, 100), 'contrast': (-100, 100),
    'highlights': (-100, 100), 'shadows': (-100, 100),
    'saturation': (-100, 100), 'warmth': (-100, 100),
    'sharpness': (0, 100),
}
CROPS = {'original': None, 'square': (1, 1), '4:3': (4, 3),
         '3:2': (3, 2), '16:9': (16, 9), '272:300': (272, 300)}
DEFAULT = {'rotate': 0, 'crop': 'original', **{k: 0 for k in RANGES}}


def normalize_recipe(candidate: dict | None) -> dict:
    if candidate is None:
        return dict(DEFAULT)
    if not isinstance(candidate, dict) or set(candidate) - set(DEFAULT):
        raise ValueError('Unsupported photo edit setting')
    result = dict(DEFAULT)
    result.update(candidate)
    if type(result['rotate']) is not int or result['rotate'] not in (0, 90, 180, 270):
        raise ValueError('Rotation must be 0, 90, 180 or 270 degrees')
    if not isinstance(result['crop'], str) or result['crop'] not in CROPS:
        raise ValueError('Unsupported crop ratio')
    for key, (minimum, maximum) in RANGES.items():
        v = result[key]
        if type(v) is not int or not minimum <= v <= maximum:
            raise ValueError(f'{key} must be an integer from {minimum} to {maximum}')
    return result


def migrate(con) -> None:
    con.execute('''CREATE TABLE IF NOT EXISTS photo_edit_recipes (
        photo_id INTEGER PRIMARY KEY REFERENCES photos(id) ON DELETE CASCADE,
        recipe_json TEXT NOT NULL,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )''')


def load_recipe(con, photo_id: int) -> dict:
    migrate(con)
    row = con.execute('SELECT recipe_json FROM photo_edit_recipes WHERE photo_id=?', (photo_id,)).fetchone()
    return normalize_recipe(json.loads(row[0])) if row else dict(DEFAULT)


def save_recipe(con, photo_id: int, candidate: dict) -> None:
    recipe = normalize_recipe(candidate)
    row = con.execute('SELECT id FROM photos WHERE id=? AND deleted_at IS NULL', (photo_id,)).fetchone()
    if row is None:
        raise ValueError('Photograph does not exist or is in Trash')
    migrate(con)
    con.execute('''INSERT INTO photo_edit_recipes (photo_id,recipe_json,updated_at)
        VALUES(?,?,CURRENT_TIMESTAMP)
        ON CONFLICT(photo_id) DO UPDATE SET recipe_json=excluded.recipe_json,
            updated_at=CURRENT_TIMESTAMP''', (photo_id, json.dumps(recipe, sort_keys=True)))


def center_crop(img: Image.Image, crop: str) -> Image.Image:
    ratio = CROPS[crop]
    if ratio is None:
        return img
    target = ratio[0] / ratio[1]
    w, h = img.size
    if w / h > target:
        desired = max(1, min(w, round(h * target)))
        left = (w - desired) // 2
        return img.crop((left, 0, left + desired, h))
    desired = max(1, min(h, round(w / target)))
    top = (h - desired) // 2
    return img.crop((0, top, w, top + desired))


def apply_recipe(source: Image.Image, candidate: dict | None, preview_max: int = 0) -> Image.Image:
    r = normalize_recipe(candidate)
    oriented = ImageOps.exif_transpose(source)
    if 'A' in oriented.getbands():
        rgba = oriented.convert('RGBA')
        im = Image.new('RGB', rgba.size, 'white')
        im.paste(rgba, mask=rgba.getchannel('A'))
    else:
        im = oriented.convert('RGB')
    if r['rotate']:
        im = im.rotate(-r['rotate'], expand=True)
    im = center_crop(im, r['crop'])
    if preview_max > 0:
        im.thumbnail((preview_max, preview_max), Image.Resampling.LANCZOS)
    if r['exposure']:
        im = ImageEnhance.Brightness(im).enhance(2.0 ** (r['exposure'] / 100))
    if r['contrast']:
        factor = 1 + r['contrast'] / 100
        table = [max(0, min(255, round((v - 128) * factor + 128))) for v in range(256)]
        im = im.point(table * 3)
    if r['saturation']:
        im = ImageEnhance.Color(im).enhance(1 + r['saturation'] / 100)
    if r['highlights'] or r['shadows']:
        # Tonal changes operate conservatively on channel values, not inferred scene detail.
        sh, hi = r['shadows'] / 100, r['highlights'] / 100
        lut = []
        for n in range(256):
            v = n / 255
            adjusted = n + sh * 76 * (1 - v) ** 2 + hi * 76 * v ** 2
            lut.append(max(0, min(255, round(adjusted))))
        im = im.point(lut * 3)
    if r['warmth']:
        shift = r['warmth'] * .24
        red, green, blue = im.split()
        red = red.point([max(0, min(255, round(v + shift))) for v in range(256)])
        blue = blue.point([max(0, min(255, round(v - shift))) for v in range(256)])
        im = Image.merge('RGB', (red, green, blue))
    if r['sharpness']:
        im = ImageEnhance.Sharpness(im).enhance(1 + r['sharpness'] / 100)
    return im


def export_copy(source: Path, destination: Path, recipe: dict, *,
                width: int = 0, height: int = 0, quality: int = 86) -> tuple[int, int]:
    source, destination = Path(source), Path(destination)
    if not source.is_file() or source.resolve() == destination.resolve():
        raise ValueError('Source file is unavailable or destination equals source')
    if destination.suffix.lower() not in ('.jpg', '.jpeg', '.png', '.webp'):
        raise ValueError('Choose a JPEG, PNG or WebP filename')
    if any(type(n) is not int or n < 0 or n > 8000 for n in (width, height)):
        raise ValueError('Invalid output dimensions')
    if (width and height and width * height > 32_000_000) or type(quality) is not int or not 40 <= quality <= 100:
        raise ValueError('Output dimensions or quality exceed limits')
    with Image.open(source) as opened:
        result = apply_recipe(opened, recipe)
    if width and height:
        result = ImageOps.fit(result, (width, height), method=Image.Resampling.LANCZOS)
    elif width or height:
        w, h = result.size
        dimensions = (width, max(1, round(h * width / w))) if width else (max(1, round(w * height / h)), height)
        if dimensions[0] * dimensions[1] > 32_000_000:
            raise ValueError('Output has too many pixels')
        result = result.resize(dimensions, Image.Resampling.LANCZOS)
    fmt = {'.jpg': 'JPEG', '.jpeg': 'JPEG', '.webp': 'WEBP', '.png': 'PNG'}[destination.suffix.lower()]
    destination.parent.mkdir(parents=True, exist_ok=True)
    created = False
    try:
        with destination.open('xb') as out:
            created = True
            opts = {'quality': quality} if fmt in ('WEBP', 'JPEG') else {}
            if fmt == 'WEBP':
                opts['method'] = 4
            result.save(out, format=fmt, **opts)
        return result.size
    except Exception:
        if created:
            destination.unlink(missing_ok=True)
        raise
