# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy", "opencv-python"]
# ///
"""Write alpha contact sheets and a compact motion/library audit."""
import json,sys
from pathlib import Path
import cv2
import numpy as np

root=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else Path(__file__).resolve().parents[2]/'output-figment'
review=root/'repaired/review';review.mkdir(parents=True,exist_ok=True)
jobs=[json.loads(p.read_text()) for p in sorted((root/'repaired/jobs').glob('*/job.json'))]
ready=[j for j in jobs if j['status']=='ingested'];report=[]
for page in range((len(ready)+11)//12):
    canvas=np.full((1200,1280,3),220,np.uint8)
    for slot,j in enumerate(ready[page*12:page*12+12]):
        y0=(slot//2)*200;x0=(slot%2)*640
        cv2.putText(canvas,j['id'],(x0+8,y0+20),0,.55,(30,30,30),1,cv2.LINE_AA)
        im=cv2.imread(j['asset'],cv2.IMREAD_UNCHANGED)
        for k,p in enumerate(j['poses']):
            crop=im[p['y']:p['y']+p['h'],p['x']:p['x']+p['w']]
            scale=min(148/p['w'],168/p['h']);crop=cv2.resize(crop,None,fx=scale,fy=scale,interpolation=cv2.INTER_AREA)
            h,w=crop.shape[:2];y=y0+28+(168-h)//2;x=x0+160*k+(160-w)//2
            yy,xx=np.indices((h,w));bg=np.where(((xx//8+yy//8)%2)[...,None],185,220)
            a=crop[:,:,3:4]/255;canvas[y:y+h,x:x+w]=(crop[:,:,:3]*a+bg*(1-a)).astype(np.uint8)
    cv2.imwrite(str(review/f'alpha-page-{page+1}.jpg'),canvas)
for j in jobs:
    p=root/'repaired/jobs'/j['id']/'motion.json'
    if not p.exists():continue
    m=json.loads(p.read_text());b=np.array(m['boxes']);v=np.diff(b,axis=0)
    report.append({'id':j['id'],'status':j['status'],'frames':len(b),'poses':len(j.get('poses',[])),
      'last_top':float(b[-1,1]),'max_size':b[:,2:].max(axis=0).tolist(),
      'max_xy_step':float(np.linalg.norm(v[:,:2],axis=1).max()),
      'extrapolated_exit_frames':m['extrapolated_exit_frames'],'excluded_poses':j.get('excluded_poses',[])})
(review/'library-audit.json').write_text(json.dumps(report,indent=2))
print(json.dumps({'jobs':len(jobs),'ready':len(ready),'pages':(len(ready)+11)//12,'pending':[j['id'] for j in jobs if j['status']!='ingested']}))
