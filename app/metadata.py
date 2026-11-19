"""Local extraction of EXIF, image dimensions, selected XMP provenance fields."""
from __future__ import annotations
import os
import re
from pathlib import Path
from PIL import Image, ExifTags
from .catalog import gps_hint

SUPPORTED = {'.jpg', '.jpeg', '.png', '.webp', '.tif', '.tiff', '.bmp', '.heic', '.heif'}
try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
except ImportError:
    SUPPORTED.difference_update({'.heic', '.heif'})

def _str(value):
    if value is None: return ""
    if isinstance(value, bytes): return value.decode('utf-8', errors='replace').strip('\x00 ')
    return str(value).strip('\x00 ')

def _fraction(x):
    try: return float(x)
    except (TypeError, ValueError, ZeroDivisionError): return 0.

def _gps(gps):
    if not gps: return (None, None)
    named = {ExifTags.GPSTAGS.get(k, k): v for k, v in gps.items()}
    def coord(key, ref):
        vals = named.get(key)
        if not vals or len(vals) != 3: return None
        v = _fraction(vals[0]) + _fraction(vals[1])/60 + _fraction(vals[2])/3600
        if _str(named.get(ref, '')).upper() in ('S', 'W'): v = -v
        return v
    lat, lon = coord('GPSLatitude', 'GPSLatitudeRef'), coord('GPSLongitude', 'GPSLongitudeRef')
    if lat is not None and not -90 <= lat <= 90: lat = None
    if lon is not None and not -180 <= lon <= 180: lon = None
    return (lat, lon)

def _xmp_field(content: bytes, key: str) -> str:
    # Only extract explicit embedded metadata; NEVER infer the original website from pixels.
    try:
        body = content.decode('utf-8', errors='replace')
        patterns = [rf'<(?:\w+:)?{key}[^>]*>([^<]{{1,400}})</', rf'(?:\w+:)?{key}=["\']([^"\']{{1,400}})["\']']
        for pattern in patterns:
            match = re.search(pattern, body, re.IGNORECASE)
            if match: return match.group(1).strip()
    except Exception: pass
    return ''

def read_image(path: Path, source_url: str = '') -> dict:
    path = Path(path)
    stat = path.stat()
    with Image.open(path) as im:
        width, height = im.size
        exif = im.getexif()
        gps = exif.get_ifd(34853) if exif else {}
        lat, lon = _gps(gps)
        raw_xmp = im.info.get('XML:com.adobe.xmp') or im.info.get('xmp') or b''
        if isinstance(raw_xmp, str): raw_xmp = raw_xmp.encode('utf-8')
        camera = ' '.join(s for s in [_str(exif.get(271)), _str(exif.get(272))] if s).strip()
        artist = _str(exif.get(315)) or _xmp_field(raw_xmp, 'creator')
        copyright_info = _str(exif.get(33432)) or _xmp_field(raw_xmp, 'rights')
        license_info = _xmp_field(raw_xmp, 'license')
        provenance = source_url.strip() or _xmp_field(raw_xmp, 'WebStatement') or _xmp_field(raw_xmp, 'source')
    return {
        'path': str(path.resolve()), 'original_path': str(path.resolve()),
        'source_folder': str(path.parent.resolve()), 'source_url': provenance,
        'width': width, 'height': height, 'mtime': stat.st_mtime, 'file_size': stat.st_size,
        'camera': camera, 'artist': artist, 'copyright': copyright_info, 'license': license_info,
        'gps_lat': lat, 'gps_lon': lon, 'location': gps_hint(lat, lon),
        'location_source': 'GPS area hint' if gps_hint(lat, lon) else '',
        'taken_at': _str(exif.get(36867)) if exif else '',
    }

def image_paths(folder: Path):
    folder = Path(folder).resolve()
    for root, dirs, names in os.walk(folder, followlinks=False):
        dirs[:] = [d for d in dirs if not (Path(root) / d).is_symlink()]
        for name in names:
            candidate = Path(root) / name
            if candidate.suffix.lower() in SUPPORTED and not candidate.is_symlink():
                yield candidate
