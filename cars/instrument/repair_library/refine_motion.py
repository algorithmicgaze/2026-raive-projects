# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy", "scipy", "opencv-python"]
# ///
"""Continue each source track through its actual exit using optical flow.

Writes motion.json separately from image jobs so generation can run concurrently.
"""
import json,sys,hashlib
from pathlib import Path
import cv2
import numpy as np
from scipy.ndimage import gaussian_filter1d
from pipeline import atomic_json,trajectory

def points(gray,b):
    x,y,w,h=b;mask=np.zeros_like(gray)
    l=max(0,int(x+.13*w));r=min(1920,int(x+.87*w));t=max(0,int(y+.07*h));bottom=min(1080,int(y+.92*h))
    if l>=r or t>=bottom:return None
    mask[t:bottom,l:r]=255
    return cv2.goodFeaturesToTrack(gray,maxCorners=160,qualityLevel=.008,minDistance=4,mask=mask,blockSize=5)

def refine(root,p):
    j=json.loads(p.read_text());meta=json.loads(Path(j['source_meta']).read_text())
    start=j.get('source_start_frame',meta['start_frame']-(100 if j['id']=='lane2_f1284_0488' else 0))
    files=sorted((root.parent/'media/clips-stab'/meta['source']).glob('*.jpg'))
    track=j.get('motion_track',j['track'])
    base,full=trajectory(track,len(j['clip']['boxes']))
    # Start while the whole target is still inside the camera.
    anchor=full[-2];i=anchor['frame'];b=np.array(base[i],float)
    gray=cv2.imread(str(files[start+i]),cv2.IMREAD_GRAYSCALE);pts=points(gray,b)
    out=base[:i+1];history=[];flow_frames=0
    initial=np.median(np.diff(np.array(base[max(0,i-15):i+1]),axis=0),axis=0)
    minimum_motion=max(.12,min(.8,float(initial[1])*.25))
    while i+2+start<len(files) and i<len(base)+400 and b[1]<1082 and b[0]<1922 and b[0]+b[2]>-2:
        step=2;next_gray=cv2.imread(str(files[start+i+step]),cv2.IMREAD_GRAYSCALE)
        if pts is None or len(pts)<6:break
        q,st,err=cv2.calcOpticalFlowPyrLK(gray,next_gray,pts,None,winSize=(31,31),maxLevel=3,
          criteria=(cv2.TERM_CRITERIA_EPS|cv2.TERM_CRITERIA_COUNT,30,.01))
        back,st2,_=cv2.calcOpticalFlowPyrLK(next_gray,gray,q,None,winSize=(31,31),maxLevel=3)
        movement=np.linalg.norm(q-pts,axis=2).ravel()/step
        # Road markings can dominate RANSAC once a trailer leaves the image.
        # Static points are never evidence that the vehicle has stopped.
        good=(st.ravel()>0)&(st2.ravel()>0)&(np.linalg.norm(back-pts,axis=2).ravel()<1.2)&(movement>minimum_motion)
        a=pts[good].reshape(-1,2);z=q[good].reshape(-1,2)
        if len(a)<6:break
        matrix,inliers=cv2.estimateAffinePartial2D(a,z,method=cv2.RANSAC,ransacReprojThreshold=1.8,maxIters=500)
        if matrix is None or inliers.sum()<6:break
        scale=float(np.clip(np.hypot(matrix[0,0],matrix[0,1]),.985,1.04))
        center=b[:2]+b[2:]/2
        moved=matrix[:,:2]@center+matrix[:,2]
        size=b[2:]*scale;nb=np.r_[moved-size/2,size]
        if np.linalg.norm(nb[:2]-b[:2])>45:break
        if (nb[1]-b[1])/step<minimum_motion:break
        for k in range(1,step+1):out.append((b+(nb-b)*k/step).tolist())
        history.append((nb-b)/step);history=history[-12:]
        b=nb;i+=step;gray=next_gray;pts=z[inliers.ravel()>0].reshape(-1,1,2).astype(np.float32);flow_frames+=step
        if len(pts)<35:
            fresh=points(gray,b)
            if fresh is not None:pts=fresh
    # Only the last few off-screen pixels normally need extrapolation. Source
    # footage can also end early; retain the last measured velocity in that case.
    if history:velocity=np.median(history,axis=0)
    else:
        a=np.array(base[max(0,i-15):i+1]);velocity=np.median(np.diff(a,axis=0),axis=0)
    velocity[1]=max(.5,velocity[1]);velocity[2:]=np.maximum(0,velocity[2:])
    extrapolated=0
    while b[1]<1082 and b[0]<1922 and b[0]+b[2]>-2 and extrapolated<1200:
        b=b+velocity;out.append(b.tolist());extrapolated+=1
    arr=np.array(out);arr=gaussian_filter1d(arr,1.25,axis=0,mode='nearest')
    atomic_json(p.with_name('motion.json'),{'boxes':arr.tolist(),'version':2,'track_sha256':hashlib.sha256(json.dumps(track).encode()).hexdigest(),'method':'smoothed detection track + source optical-flow exit','anchor_frame':anchor['frame'],'tracked_exit_frames':flow_frames,'extrapolated_exit_frames':extrapolated})
    print(json.dumps({'id':j['id'],'frames':len(out),'flow':flow_frames,'extrapolated':extrapolated}),flush=True)

if __name__=='__main__':
    root=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else Path(__file__).resolve().parents[2]/'output-figment'
    for p in sorted((root/'repaired/jobs').glob('*/job.json')):
        if p.with_name('motion.json').exists():
            old=json.loads(p.with_name('motion.json').read_text());job=json.loads(p.read_text())
            if old.get('version')==2 and old.get('track_sha256')==hashlib.sha256(json.dumps(job.get('motion_track',job['track'])).encode()).hexdigest():continue
        try:refine(root,p)
        except Exception as e:print(json.dumps({'id':p.parent.name,'error':str(e)}),flush=True)
