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
    return {'activities': selected, 'attraction': attraction,
            'score': round(float(landmark_score), 3),
            'activity_score': round(float(acts[0][1]), 3) if acts else 0.0}


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
    """Analyze selected photos locally, skipping already-cached images.

    Model loading is lazy: a repeat run using only cached results does not load
    PyTorch or re-download weights. To refresh predictions, pass force=True.
    """
    if progress: progress('Checking previously analyzed photos (no upload)...')
    pending=[]; completed=skipped=matched=places=unmatched=cached=0
    errors=[]; processed_ids=[]
    engine='openclip'; model_name=MODEL + ':' + WEIGHTS
    with connect(db_path) as con:
        for pid in dict.fromkeys(ids):
            row=photo_by_id(con,pid)
            if not row or row['ai_source']=='Manual' or row['ai_review']=='approved':
                skipped+=1;continue
            try:
                file_sig=ai_cache.signature(row['path'])
                result=None if force else ai_cache.get(con,pid,engine,model_name,file_sig)
                pending.append((pid,file_sig,result))
            except Exception as exc:
                errors.append(f'Photo {pid}: {exc}')
        recognizer=LocalRecognizer(progress) if any(item[2] is None for item in pending) else None
        for index,(pid,file_sig,result) in enumerate(pending,1):
            try:
                if result is None:
                    result=recognizer.predict(photo_by_id(con,pid)['path'])
                    ai_cache.store(con,pid,engine,model_name,file_sig,result)
                else: cached+=1
                if ai_cache.apply(con,pid,result,'OpenCLIP suggestion'):
                    completed+=1;processed_ids.append(pid)
                    matched+=bool(result.get('activities'))
                    places+=bool(result.get('attraction'))
                    unmatched+=not(result.get('activities') or result.get('attraction'))
                if index%10==0:con.commit()
            except Exception as exc:
                if len(errors)<12: errors.append(f'Photo {pid}: {type(exc).__name__}: {exc}')
            if progress and (index<=3 or index%10==0 or index==len(pending)):
                progress(f'Local AI {index}/{len(pending)} | {matched} tagged, {cached} cached')
        con.commit()
    return {'tagged':completed,'skipped':skipped,'cached':cached,
            'with_activity':matched,'with_attraction':places,'unmatched':unmatched,
            'processed_ids':processed_ids,'errors':errors}


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
