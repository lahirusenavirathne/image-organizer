"""On-device YuNet detection + SFace embeddings. No names or embeddings sent to cloud."""
from __future__ import annotations
import os
import urllib.request
from pathlib import Path
from .db import connect, ids_unprocessed, photo_by_id

MODEL_NAMES = {
    'yunet.onnx': ('https://github.com/opencv/opencv_zoo/raw/refs/heads/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx', 100_000),
    'sface.onnx': ('https://github.com/opencv/opencv_zoo/raw/refs/heads/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx', 5_000_000),
}

def download_models(directory: Path, progress=None):
    directory.mkdir(parents=True,exist_ok=True)
    for filename, (url,minimum) in MODEL_NAMES.items():
        target=directory / filename
        if target.exists() and target.stat().st_size>=minimum: continue
        if progress: progress('Downloading face model: '+filename)
        tmp=target.with_suffix('.tmp')
        try:
            with urllib.request.urlopen(url,timeout=120) as response, open(tmp,'wb') as output:
                while True:
                    block=response.read(1024*1024)
                    if not block: break
                    output.write(block)
            if tmp.stat().st_size < minimum: raise RuntimeError(f'{filename}: unexpected model size; check source URL')
            os.replace(tmp,target)
        finally:
            tmp.unlink(missing_ok=True)
    return 'Face models downloaded. Face groups are created entirely on this computer.'

class FaceEngine:
    def __init__(self, model_dir):
        try:
            import cv2 as cv
            import numpy as np
        except ImportError as exc:
            raise RuntimeError('Face grouping needs OpenCV and NumPy installed') from exc
        self.cv,self.np=cv,np
        det=Path(model_dir) / 'yunet.onnx'
        rec=Path(model_dir) / 'sface.onnx'
        if not det.exists() or not rec.exists():
            raise RuntimeError('Face models are missing. Click Download Face Models first.')
        self.detector=cv.FaceDetectorYN.create(str(det),'',(320,320),0.85,0.3,500)
        self.recognizer=cv.FaceRecognizerSF.create(str(rec),'')

    def features(self,path):
        cv,np=self.cv,self.np
        arr=np.fromfile(path,dtype=np.uint8)
        frame=cv.imdecode(arr,cv.IMREAD_COLOR)
        if frame is None: raise ValueError('Cannot decode this image')
        height,width=frame.shape[:2]
        max_edge=max(height,width)
        if max_edge>1280:
            scale=1280/max_edge
            frame=cv.resize(frame,(round(width*scale),round(height*scale)))
        h,w=frame.shape[:2]
        self.detector.setInputSize((w,h))
        _,detections=self.detector.detect(frame)
        ret=[]
        if detections is None: return ret
        for face in detections:
            aligned=self.recognizer.alignCrop(frame,face)
            feature=self.recognizer.feature(aligned).astype(np.float32).reshape(-1)
            norm=np.linalg.norm(feature)
            if norm>0: ret.append(feature/norm)
        return ret

def group_faces(db_path, model_dir, progress=None):
    import numpy as np
    engine=FaceEngine(model_dir)
    total=processed=found=0
    errors=[]
    with connect(db_path) as con:
        todo=ids_unprocessed(con)
        total=len(todo)
        rows=con.execute('SELECT id,centroid,n FROM face_groups').fetchall()
        groups={r['id']:[np.frombuffer(r['centroid'],dtype=np.float32).copy(),r['n']] for r in rows}
        for i,pid in enumerate(todo,1):
            row=photo_by_id(con,pid)
            if not row: continue
            try:
                embeddings=engine.features(row['path'])
                for feat in embeddings:
                    best_id=None; best_score=-1.
                    for gid,(centroid,count) in groups.items():
                        score=float(np.dot(feat,centroid))
                        if score>best_score: best_id,best_score=gid,score
                    # Conservative grouping; not proof of identity; may split or merge incorrectly.
                    if best_id is not None and best_score>=0.50:
                        old,n=groups[best_id]
                        centroid=(old*n+feat)/(n+1)
                        centroid/=max(float(np.linalg.norm(centroid)),1e-8)
                        groups[best_id]=[centroid,n+1]
                        con.execute('UPDATE face_groups SET centroid=?,n=? WHERE id=?',
                                    (centroid.astype(np.float32).tobytes(),n+1,best_id))
                        group_id=best_id
                    else:
                        cur=con.execute('INSERT INTO face_groups (centroid,n) VALUES (?,1)',(feat.tobytes(),))
                        group_id=cur.lastrowid
                        groups[group_id]=[feat,1]
                    con.execute('INSERT INTO faces (photo_id,group_id,feature) VALUES (?,?,?)',
                                (pid,group_id,feat.tobytes()))
                    found+=1
                con.execute('UPDATE photos SET face_processed=1,face_count=? WHERE id=?',(len(embeddings),pid))
                con.commit() # one image atomic with face records
                processed+=1
            except Exception as exc:
                con.rollback()
                # Reset in-memory centroids to match rolled-back database changes.
                rows=con.execute('SELECT id,centroid,n FROM face_groups').fetchall()
                groups={r['id']:[np.frombuffer(r['centroid'],dtype=np.float32).copy(),r['n']] for r in rows}
                if len(errors)<10: errors.append(f"{Path(row['path']).name}: {exc}")
            if progress and i%10==0: progress(f'Faces: {i}/{total} images analyzed, {found} faces')
    return {'scanned':processed,'faces':found,'groups':len(groups),'errors':errors}
