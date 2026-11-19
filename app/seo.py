"""Deterministic bilingual metadata for travel-photo exports (not AI fiction)."""
from __future__ import annotations
import json
import re
import unicodedata
from pathlib import Path

ES_LABELS = {
    'Safari':'safari','Elephant':'elefante','Leopard':'leopardo',
    'Temple visit':'visita a un templo','Trekking':'senderismo',
    'Beach':'playa','Waterfall':'cascada','Whale watching':'avistamiento de ballenas',
    'Birdwatching':'observación de aves','Cycling':'ciclismo',
    'Surfing':'surf','Cooking class':'clase de cocina',
}


def slug(value: str) -> str:
    ascii_text=unicodedata.normalize('NFKD',value or '').encode('ascii','ignore').decode('ascii').lower()
    return re.sub(r'[^a-z0-9]+','-',ascii_text).strip('-')[:90]


def alt_text(row) -> tuple[str,str]:
    """Suggest alt texts only from catalog evidence; do not invent exact scene details."""
    location=(row['attraction'] or row['location'] or '').strip()
    try:activities=json.loads(row['activities'] or '[]')
    except (ValueError,TypeError):activities=[]
    activity=activities[0] if activities else ''
    if not location and not activity:
        stem=Path(row['path']).stem.replace('_',' ').replace('-',' ')[:75]
        return f'Travel photo: {stem}',f'Foto de viaje: {stem}'
    parts=[v for v in (activity,location) if v]
    english='Travel photography: '+', '.join(parts)
    spanish='Fotografía de viaje: '+', '.join([ES_LABELS.get(activity,activity),location] if activity else [location])
    return english[:160],spanish[:160]


def export_basename(row, original_stem: str) -> str:
    try:acts=json.loads(row['activities'] or '[]')
    except (TypeError,ValueError):acts=[]
    meaningful=[row['attraction'] or row['location'],acts[0] if acts else '',original_stem]
    return slug(' '.join(v for v in meaningful if v)) or 'travel-photo'
