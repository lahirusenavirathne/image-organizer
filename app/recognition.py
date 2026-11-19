"""Opt-in, local Sri Lanka photo tagging and explicit cloud analysis.

OpenCLIP is optional: importing the photo manager never requires its dependencies.
All local output is a suggestion to be reviewed; no faces or metadata are uploaded.
"""
from __future__ import annotations
import base64
import importlib.util
import io
import json
import urllib.error
import urllib.request
from pathlib import Path
from PIL import Image, ImageOps
from .catalog import ACTIVITIES, ATTRACTIONS
from .db import connect, photo_by_id
from . import ai_cache

MODEL = 'ViT-B-32'
WEIGHTS = 'laion2b_s34b_b79k'


def local_ai_missing() -> list[str]:
    """Cheap preflight for UI; this does not load the large PyTorch libraries."""
    return [display for module, display in (
        ('torch', 'PyTorch'), ('torchvision', 'torchvision'), ('open_clip', 'OpenCLIP'))
        if importlib.util.find_spec(module) is None]


def suggest_tags(activity_names, attraction_names, scores) -> dict:
    """Translate non-calibrated CLIP similarities into reviewable suggestions.

    The best plausible activity is shown rather than silently tagging no photos
    because an arbitrary high global similarity threshold was not met.
    Exact landmarks remain deliberately conservative because e.g. national
    parks and generic Buddha statues are difficult to tell apart visually.
    """
    n = len(activity_names)
    if len(scores) != n + len(attraction_names):
        raise ValueError('Image and text features had incompatible dimensions')
    acts = sorted(zip(activity_names, scores[:n]), key=lambda x: -x[1])
    places = sorted(zip(attraction_names, scores[n:]), key=lambda x: -x[1])
    selected = []
    if acts:
        peak = float(acts[0][1])
        if peak >= 0.18:
            selected = [acts[0][0]]
            selected.extend(name for name, score in acts[1:]
                            if score >= 0.23 and score >= peak - 0.025)
            selected = selected[:3]
    attraction = ''
    landmark_score = 0.0
    if places:
        attraction, landmark_score = places[0]
        next_score = places[1][1] if len(places) > 1 else 0.0
        if landmark_score < 0.30 or landmark_score - next_score < 0.02:
            attraction = ''
    # Raw CLIP cosine similarities are NOT calibrated confidence percentages.
    # Show candidates even when strict automatic-tag thresholds reject them.
    activity_candidates = [
        {'name': name, 'similarity': round(float(score), 4)}
        for name, score in acts[:3]
    ]
    attraction_candidates = [
        {'name': name, 'similarity': round(float(score), 4)}
        for name, score in places[:3]
    ]
    activity_reason = ('Suggested' if selected else
                       'No activity candidate passed the automatic-tag threshold (0.18)')
    attraction_reason = ('Tentative landmark suggestion' if attraction else
                         'Landmark withheld: similarity below 0.30 or margin below 0.02')
    return {'activities': selected, 'attraction': attraction,
            'score': round(float(landmark_score), 3),
            'activity_score': round(float(acts[0][1]), 3) if acts else 0.0,
            'activity_candidates': activity_candidates,
            'attraction_candidates': attraction_candidates,
            'activity_reason': activity_reason,
            'attraction_reason': attraction_reason}


class LocalRecognizer:
    def __init__(self, progress=None):
        missing = local_ai_missing()
        if missing:
            raise RuntimeError('Local AI is not installed: ' + ', '.join(missing) +
                               '. Close the app and run INSTALL_AI_WINDOWS.bat in its folder, '
                               'then restart the app.')
        if progress:
            progress('Loading PyTorch and OpenCLIP. Initial setup may take a minute...')
        try:
            import torch
            import open_clip
        except Exception as exc:
            raise RuntimeError(
                'The AI libraries are installed but cannot load together. '
                'Run DIAGNOSE_AI_WINDOWS.bat, then rerun INSTALL_AI_WINDOWS.bat. '
                f'Original error: {type(exc).__name__}: {exc}') from exc
        self.torch, self.clip = torch, open_clip
        if progress:
            progress('Loading visual model. First use requires internet to download model weights; '
                     'later uses are offline...')
        try:
            self.model, _, self.preprocess = open_clip.create_model_and_transforms(
                MODEL, pretrained=WEIGHTS, device='cpu')
            self.model.eval()
            tokenizer = open_clip.get_tokenizer(MODEL)
            self.activity_names = list(ACTIVITIES)
            self.attraction_names = list(ATTRACTIONS)
            prompts = ([f'A travel photograph of {v}.' for v in ACTIVITIES.values()]
                       + [f'A photograph of {v}.' for v in ATTRACTIONS.values()])
            if progress:
                progress('Preparing Sri Lanka activities and attractions...')
            with torch.inference_mode():
                features = self.model.encode_text(tokenizer(prompts))
                self.text_features = features / features.norm(dim=-1, keepdim=True)
        except Exception as exc:
            raise RuntimeError(
                'Unable to initialize the OpenCLIP visual model. For first use, '
                'verify internet access, then try again. If the model was already downloaded, '
                'run DIAGNOSE_AI_WINDOWS.bat. '
                f'Original error: {type(exc).__name__}: {exc}') from exc

    def predict(self, path: str) -> dict:
        with Image.open(path) as src:
            image = self.preprocess(ImageOps.exif_transpose(src).convert('RGB')).unsqueeze(0)
        with self.torch.inference_mode():
            image_features = self.model.encode_image(image)
            image_features /= image_features.norm(dim=-1, keepdim=True)
            scores = (image_features @ self.text_features.T).flatten().tolist()
        return suggest_tags(self.activity_names, self.attraction_names, scores)


def test_local_model(progress=None) -> str:
    """Full end-to-end smoke test with a temporary synthetic image (no user files)."""
    import tempfile
    model = LocalRecognizer(progress)
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / 'ai_test.jpg'
        Image.new('RGB', (224, 224), (76, 133, 100)).save(path)
        output = model.predict(str(path))
    if not isinstance(output.get('activities'), list):
        raise RuntimeError('Local AI returned an unexpected classification result')
    return 'Local AI works. OpenCLIP loaded, model weights are ready, and image classification completed successfully.'


def run_local(db_path: Path, ids: list[int], progress=None, *, force=False):
    """Classify locally and return a human-readable audit of each selected photo.

    Re-analysis bypasses cached scores, but never replaces manually approved tags.
    Candidate scores are uncalibrated cosine similarities, not probabilities.
    """
    if progress:
        progress('Checking previous results (offline; no image upload)...')
    pending = []
    completed = skipped = matched = places = unmatched = cached = 0
    errors = []
    processed_ids = []
    reports = []
    max_reports = 100
    engine = 'openclip'
    model_name = MODEL + ':' + WEIGHTS
    with connect(db_path) as con:
        for pid in dict.fromkeys(ids):
            row = photo_by_id(con, pid)
            if row is None:
                skipped += 1
                if len(reports) < max_reports:
                    reports.append({'filename': f'Photo #{pid}', 'status': 'Skipped: no longer indexed'})
                continue
            name = Path(row['path']).name
            if row['ai_source'] == 'Manual' or row['ai_review'] == 'approved':
                skipped += 1
                if len(reports) < max_reports:
                    reports.append({'filename': name, 'status': 'Skipped: manually reviewed; protected'})
                continue
            try:
                file_sig = ai_cache.signature(row['path'])
                result = None if force else ai_cache.get(con, pid, engine, model_name, file_sig)
                pending.append((pid, name, file_sig, result))
            except Exception as exc:
                message = f'{name}: {type(exc).__name__}: {exc}'
                errors.append(message)
                if len(reports) < max_reports:
                    reports.append({'filename': name, 'status': 'Error: ' + str(exc)})
        recognizer = LocalRecognizer(progress) if any(item[3] is None for item in pending) else None
        for index, (pid, name, file_sig, result) in enumerate(pending, 1):
            was_cached = result is not None
            try:
                if result is None:
                    result = recognizer.predict(photo_by_id(con, pid)['path'])
                    ai_cache.store(con, pid, engine, model_name, file_sig, result)
                else:
                    cached += 1
                if ai_cache.apply(con, pid, result, 'OpenCLIP suggestion'):
                    completed += 1
                    processed_ids.append(pid)
                    has_activity = bool(result.get('activities'))
                    has_attraction = bool(result.get('attraction'))
                    matched += has_activity
                    places += has_attraction
                    unmatched += not (has_activity or has_attraction)
                    status = ('Tagged' if has_activity or has_attraction else 'No accepted tags')
                    if was_cached:
                        status += ' (cached)'
                    if len(reports) < max_reports:
                        reports.append({
                            'filename': name, 'status': status,
                            'activities': result.get('activities', []),
                            'attraction': result.get('attraction', ''),
                            'activity_candidates': result.get('activity_candidates', []),
                            'attraction_candidates': result.get('attraction_candidates', []),
                            'activity_reason': result.get('activity_reason', ''),
                            'attraction_reason': result.get('attraction_reason', ''),
                            'was_cached': was_cached,
                        })
                if index % 10 == 0:
                    con.commit()
            except Exception as exc:
                message = f'{name}: {type(exc).__name__}: {exc}'
                errors.append(message)
                if len(reports) < max_reports:
                    reports.append({'filename': name, 'status': 'Error: ' + str(exc)})
            if progress and (index <= 3 or index % 10 == 0 or index == len(pending)):
                progress(f'Local AI {index}/{len(pending)} | {matched} with activity, '
                         f'{unmatched} without tags, {cached} cached')
        con.commit()
    return {'tagged': completed, 'skipped': skipped, 'cached': cached,
            'with_activity': matched, 'with_attraction': places,
            'unmatched': unmatched, 'processed_ids': processed_ids, 'errors': errors,
            'reports': reports, 'report_limit': max_reports,
            'total_selected': len(dict.fromkeys(ids)), 'forced': force}


def format_local_report(result: dict) -> str:
    """Explain outcomes without mistaking CLIP similarities for accuracy scores."""
    lines = [
        f"Selected: {result.get('total_selected', 0)} | analyzed: {result.get('tagged', 0)} "
        f"| with activity: {result.get('with_activity', 0)} "
        f"| tentative landmark: {result.get('with_attraction', 0)}",
        f"No accepted tags: {result.get('unmatched', 0)} | cached: {result.get('cached', 0)} "
        f"| protected/skipped: {result.get('skipped', 0)} | errors: {len(result.get('errors', []))}",
        'Similarity values below are raw CLIP cosine similarities, not percentages or calibrated confidence.',
        'Candidates are suggestions for human review; do not use uncertain landmarks as verified locations.',
    ]
    for item in result.get('reports', []):
        lines.append('')
        lines.append(f"{item['filename']} - {item['status']}")
        if item.get('activities'):
            lines.append('  Accepted activities: ' + ', '.join(item['activities']))
        if item.get('attraction'):
            lines.append('  Tentative landmark: ' + item['attraction'])
        for kind in ('activity', 'attraction'):
            candidates = item.get(kind + '_candidates', [])
            if candidates:
                display = ', '.join(f"{c['name']} ({c['similarity']:.3f})" for c in candidates)
                lines.append(f'  Top {kind} candidates: {display}')
            elif item.get('was_cached'):
                lines.append(f'  No {kind} scores stored in older cache: select Refresh AI selected.')
        for kind in ('activity', 'attraction'):
            if item.get(kind + '_reason'):
                lines.append('  ' + item[kind + '_reason'])
    if result.get('total_selected', 0) > result.get('report_limit', 100):
        lines.extend(['', 'Per-photo report limited to the first 100 outcomes.'])
    lines.extend(['', 'Next: inspect incorrect candidates and manually review tags; '
                  'use Refresh AI selected to bypass previous cached predictions.'])
    return '\n'.join(lines)


def _image_b64(path):
    with Image.open(path) as im:
        image = ImageOps.exif_transpose(im).convert('RGB')
        image.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
        bio = io.BytesIO()
        image.save(bio, format='JPEG', quality=75)
        return base64.b64encode(bio.getvalue()).decode('ascii')


def cloud_predict(path, api_key, model='gpt-4.1-mini'):
    if not api_key.strip():
        raise ValueError('An OpenAI API key is required')
    prompt = (
        'Classify this Sri Lanka travel photo. The result is tentative: do not claim precise identity '
        'without distinctive evidence. Return ONLY a JSON object with fields activities (array of '
        'strings), attraction (string), location (string). Allowed activities: '
        + ', '.join(ACTIVITIES) + '. Allowed attractions: ' + ', '.join(ATTRACTIONS)
        + '. The location must be a recognizable Sri Lankan city or area, or empty string. '
        'Do NOT infer photographer, licensing, copyright, web source, individual identity, or personal attributes. '
        'If unsure, leave an empty string/array. Prefer false negatives over mistaken exact landmarks.'
    )
    payload = {'model': model, 'input': [{'role': 'user', 'content': [
        {'type': 'input_text', 'text': prompt},
        {'type': 'input_image', 'image_url': 'data:image/jpeg;base64,' + _image_b64(path)}
    ]}], 'max_output_tokens': 350}
    request = urllib.request.Request('https://api.openai.com/v1/responses',
        data=json.dumps(payload).encode('utf-8'),
        headers={'Authorization': 'Bearer ' + api_key, 'Content-Type': 'application/json'}, method='POST')
    try:
        with urllib.request.urlopen(request, timeout=75) as reply:
            data = json.load(reply)
    except urllib.error.HTTPError as exc:
        detail = exc.read(500).decode('utf-8', errors='replace')
        raise RuntimeError(f'Cloud AI HTTP {exc.code}: {detail}') from exc
    texts = []
    for item in data.get('output', []):
        for part in item.get('content', []):
            if part.get('type') == 'output_text':
                texts.append(part.get('text', ''))
    text = '\n'.join(texts).strip()
    if text.startswith('```'):
        text = text.strip('`').removeprefix('json').strip()
    predicted = json.loads(text)
    if not isinstance(predicted, dict):
        raise ValueError('Cloud AI did not return a JSON object')
    activities = [x for x in predicted.get('activities', []) if isinstance(x, str) and x in ACTIVITIES][:4]
    attraction = predicted.get('attraction', '')
    if attraction not in ATTRACTIONS:
        attraction = ''
    location = predicted.get('location', '')
    if not isinstance(location, str) or len(location) > 90:
        location = ''
    return {'activities': activities, 'attraction': attraction, 'location': location}


def run_cloud(db_path, ids, api_key, model, progress=None, *, force=False,
              max_requests=50):
    """Cloud recognition is explicit and capped, not a silent background upload."""
    unique_ids=list(dict.fromkeys(ids))
    if len(unique_ids)>max_requests:
        raise ValueError(f'Cloud batch limited to {max_requests} images; choose fewer photos')
    done=skipped=matched=places=unmatched=cached=0
    errors=[];processed_ids=[]
    with connect(db_path) as con:
        for n,pid in enumerate(unique_ids,1):
            row=photo_by_id(con,pid)
            if not row or row['ai_source']=='Manual' or row['ai_review']=='approved':
                skipped+=1;continue
            try:
                file_sig=ai_cache.signature(row['path'])
                result=None if force else ai_cache.get(con,pid,'openai',model,file_sig)
                if result is None:
                    result=cloud_predict(row['path'],api_key,model)
                    ai_cache.store(con,pid,'openai',model,file_sig,result)
                else: cached+=1
                if ai_cache.apply(con,pid,result,'Cloud AI suggestion',allow_location=True):
                    done+=1;processed_ids.append(pid)
                    matched+=bool(result.get('activities'))
                    places+=bool(result.get('attraction'))
                    unmatched+=not(result.get('activities') or result.get('attraction'))
                con.commit()
            except Exception as exc:
                if len(errors)<12: errors.append(f'{Path(row["path"]).name}: {exc}')
            if progress:progress(f'Cloud AI: {n}/{len(unique_ids)} ({cached} reused; no extra API charge)')
    return {'tagged':done,'skipped':skipped,'cached':cached,
            'with_activity':matched,'with_attraction':places,'unmatched':unmatched,
            'processed_ids':processed_ids,'errors':errors}
