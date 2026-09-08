# /// script
# requires-python = ">=3.11"
# dependencies = ["ultralytics", "numpy", "scipy", "opencv-python"]
# ///
"""Resumable vehicle-library repair: prepare, ingest, build, inspect.

Image generation is deliberately external: each job has input.png and prompt.txt.
Pass the resulting image to `ingest JOB_ID IMAGE_PATH`; no API keys are used.
"""
import argparse, hashlib, json, math, shutil, time
from pathlib import Path
import cv2
import numpy as np
from scipy.interpolate import UnivariateSpline
from scipy.ndimage import gaussian_filter1d
cv2.setNumThreads(1)
DEFAULT=Path(__file__).resolve().parents[2]/'output-figment'
BOUNDS=np.array([[615,884],[942,950],[1285,1005],[1622,1060],[1960,1115]],float)

def atomic_json(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(value,indent=2));tmp.replace(path)

def bound(k,y):return BOUNDS[k,1]+(y-430)/650*(BOUNDS[k,0]-BOUNDS[k,1])

def unique_clips(root):
    manifest=json.loads((root/'manifest.json').read_text())
    return list({c['sheet']:c for c in manifest['clips']}.values())

def clip_meta(root,c):
    options=[root.parent/d/f"lane{c['lane']}"/c['id']/'meta.json' for d in ['output-clips-groups','output-clips']]
    for p in options:
        if p.exists():
            m=json.loads(p.read_text())
            if len(m['boxes'])==len(c['boxes']):return m,p
    raise RuntimeError(f"No matching source metadata for {c['sheet']}")

def smooth(t,y,noise):
    t=np.array(t,float);y=np.array(y,float);w=np.ones(len(t))
    for _ in range(4):
        f=UnivariateSpline(t,y,w=w,k=min(3,len(t)-1),s=len(t)*noise**2)
        w=np.minimum(1,2.5*noise/np.maximum(np.abs(y-f(t)),1e-6))
    # Cubic extrapolation can explode once the bumper leaves the camera.
    # Continue with a robust local velocity instead.
    count=min(6,len(t));left=np.polyfit(t[:count],f(t[:count]),1)[0];right=np.polyfit(t[-count:],f(t[-count:]),1)[0]
    def evaluate(x):
        return f(np.clip(x,t[0],t[-1]))+min(0,x-t[0])*left+max(0,x-t[-1])*right
    return evaluate

def trajectory(track,n):
    full=[r for r in track if r['box'][0]>2 and r['box'][1]>2 and r['box'][0]+r['box'][2]<1910 and r['box'][1]+r['box'][3]<1050]
    if len(full)<4:raise RuntimeError(f'Only {len(full)} complete observations; manual review required')
    ts=np.array([r['frame'] for r in full]);bb=np.array([r['box'] for r in full]);centers=bb[:,:2]+bb[:,2:]/2
    fx=smooth(ts,centers[:,0],2);fy=smooth(ts,bb[:,1],3)
    fw=smooth(ts,np.log(bb[:,2]),.025);fh=smooth(ts,np.log(bb[:,3]),.03)
    # Ignore boundary-clipped detections; keep perspective scale and continue
    # until the whole vehicle is outside the plate.
    end=max(n,int(ts[-1])+1);count=end+min(200,end)
    x=np.array([fx(i) for i in range(count)]);y=np.array([fy(i) for i in range(count)])
    y=gaussian_filter1d(np.maximum.accumulate(y),2,mode='nearest')
    w=np.exp(np.clip([fw(i) for i in range(count)],math.log(15),math.log(900)))
    h=np.exp(np.clip([fh(i) for i in range(count)],math.log(15),math.log(1400)))
    w=gaussian_filter1d(np.maximum.accumulate(w),2,mode='nearest')
    h=gaussian_filter1d(np.maximum.accumulate(h),2,mode='nearest')
    boxes=[]
    for i in range(count):
        if i>ts[-1] and (y[i]>=1080 or x[i]-w[i]/2>=1920 or x[i]+w[i]/2<=0):break
        boxes.append([float(x[i]-w[i]/2),float(y[i]),float(w[i]),float(h[i])])
    return boxes,full

def hist(im,b):
    x,y,w,h=np.round(b).astype(int)
    H,W=im.shape[:2];crop=im[max(0,y):min(H,y+h),max(0,x):min(W,x+w)]
    if not crop.size:return np.zeros(24)
    hsv=cv2.cvtColor(crop,cv2.COLOR_BGR2HSV)
    z=cv2.calcHist([hsv],[0,1],None,[8,3],[0,180,0,256]).ravel()
    return z/(np.linalg.norm(z)+1e-9)

def detect(model,im,box,lane):
    x,y,w,h=box;H,W=im.shape[:2]
    x0=max(0,int(x-80));y0=max(320,int(y-110));x1=min(W,int(x+w+80));y1=min(H,int(y+h+55))
    if x1<=x0 or y1<=y0:return []
    import torch
    device='mps' if torch.backends.mps.is_available() else 'cuda' if torch.cuda.is_available() else 'cpu'
    r=model.predict(im[y0:y1,x0:x1],imgsz=640,conf=.18,classes=[2,5,7],device=device,verbose=False)[0]
    out=[]
    for b,score,cls in zip(r.boxes.xyxy.cpu().numpy(),r.boxes.conf.cpu().numpy(),r.boxes.cls.cpu().numpy()):
        a,btop,c,d=b+[x0,y0,x0,y0];bw,bh=c-a,d-btop;cx=(a+c)/2
        inter=max(0,min(c,x+w)-max(a,x))*max(0,min(d,y+h)-max(btop,y))
        overlap=inter/max(1,bw*bh)
        lo,hi=bound(lane-1,d),bound(lane,d);margin=(hi-lo)*.22
        if overlap<.28 or not lo-margin<cx<hi+margin or bw<18 or bh<14:continue
        bb=[float(a),float(btop),float(bw),float(bh)]
        out.append({'box':bb,'confidence':float(score),'class':int(cls),'hist':hist(im,bb).tolist(),'overlap':float(overlap)})
    return out

def walk_track(samples,anchor=None):
    chosen=[];appearance=None;prev=None;velocity=np.zeros(2)
    for sample in samples:
        candidates=sample['detections'];i=sample['frame']
        if not candidates:continue
        if prev is None:
            inside=[c for c in candidates if c['overlap']>.8]
            c=anchor or max(inside or candidates,key=lambda c:c['box'][1]+c['box'][3]+10*c['confidence'])
        else:
            dt=i-prev['frame'];pb=np.array(prev['box']);pred=pb[:2]+pb[2:]/2+velocity*dt
            def score(c):
                b=np.array(c['box']);center=b[:2]+b[2:]/2
                similarity=float(np.dot(appearance,np.array(c['hist'])))
                distance=np.linalg.norm((center-pred)/np.maximum(pb[2:],[50,50]))
                return 1.4*similarity+c['confidence']+c['overlap']-.9*distance-.4*abs(math.log(max(1,b[2])/pb[2]))
            c=max(candidates,key=score)
            b=np.array(c['box'])
            # A follower appearing farther up the lane must not take over after exit.
            if dt>0 and pb[1]+pb[3]>1010 and b[1]+b[3]<pb[1]+pb[3]-80:break
            if np.dot(appearance,np.array(c['hist']))<.3:continue
            v=(b[:2]+b[2:]/2-(pb[:2]+pb[2:]/2))/dt
            velocity=.5*velocity+.5*v
        record={k:v for k,v in c.items() if k!='hist'};record['frame']=i
        chosen.append(record);prev=record
        appearance=np.array(c['hist']) if appearance is None else .85*appearance+.15*np.array(c['hist'])
        appearance/=np.linalg.norm(appearance)+1e-9
    return chosen

def choose_track(samples):
    # Start in the middle, where the target is larger and less occluded,
    # then follow that same identity in both temporal directions.
    valid=[i for i,s in enumerate(samples) if s['detections']]
    if not valid:return []
    mid=valid[len(valid)//2];cs=samples[mid]['detections'];inside=[c for c in cs if c['overlap']>.8]
    anchor=max(inside or cs,key=lambda c:c['box'][1]+c['box'][3]+10*c['confidence'])
    a=walk_track(samples[mid:],anchor);b=walk_track(samples[:mid+1][::-1],anchor)
    return sorted(b[1:]+a,key=lambda r:r['frame'])

PROMPT='''Precise photographic vehicle extraction and repair for animation.
The input is a 2-by-2 contact sheet of FOUR views of the SAME primary vehicle, in chronological order: top-left, top-right, bottom-left, bottom-right. Keep the large centered primary vehicle in each panel; REMOVE any following, leading or neighboring vehicles and all road/background pixels. These other vehicles are separate objects, never reconstruct them.
Return EXACTLY FOUR isolated views, one per panel in the same 2-by-2 layout. Preserve the primary vehicle identity, color, model, proportions, windows, mirrors, wheels, lights, roof details and each panel's camera angle. Repair accidental missing/occluded body pieces using the other views as references, completing the vehicle naturally. Keep its photographic texture, muted overcast lighting and softness. No redesign, no enhanced gloss, no stylization, no new text or people. Windshields should retain subdued reflections without inventing faces.
The vehicle should fill most of each panel with clear margin on all sides. Do not crop roofs, mirrors, wheels or bumpers. No road patches, lane markings, other objects, borders, labels or panel dividers. No ground shadows.
For subsequent alpha extraction, put the four isolated vehicles on a perfectly uniform vivid GREEN background #00FF00, RGB(0,255,0). Do not draw a checkerboard. Never paint green onto the vehicle or through a solid roof beneath a rack. Only actual empty backdrop is green. Keep all four views consistent with one another. Return only the 2-by-2 image, preferably 1792x2048 or larger.'''

def prepare(root,only=None,refresh=False):
    from ultralytics import YOLO
    work=root/'repaired';model=YOLO(str(work/'models/yolo11n.pt'))
    clips=unique_clips(root)
    for number,c in enumerate(clips):
        jid=Path(c['sheet']).stem
        if only and jid not in only:continue
        job=work/'jobs'/jid;job.mkdir(parents=True,exist_ok=True)
        old=json.loads((job/'job.json').read_text()) if (job/'job.json').exists() else None
        if old and (not refresh or old['status']=='ingested'):continue
        try:
            m,mp=clip_meta(root,c);files=sorted((root.parent/'media/clips-stab'/m['source']).glob('*.jpg'))
            if jid=='lane2_f1284_0488':
                # The packed clip starts with the Scania already cut off.
                # Recover its complete approach from the same source video.
                m={**m,'start_frame':m['start_frame']-100,'boxes':[[930,420,520,660]]*100+m['boxes']}
            n=len(m['boxes']);indices=np.unique(np.linspace(0,n-1,min(n,30)).astype(int))
            samples=[]
            if (job/'detections.json').exists():samples=json.loads((job/'detections.json').read_text())
            else:
                for i in indices:
                    file=files[m['start_frame']+int(i)];im=cv2.imread(str(file))
                    samples.append({'frame':int(i),'file':str(file),'detections':detect(model,im,m['boxes'][i],c['lane'])})
            atomic_json(job/'detections.json',samples)
            track=choose_track(samples)
            # Reviewed crowded approaches: the early detector boxes merge an
            # occluder with the target. Use the same vehicle's clear later track.
            minimum={'lane1_f1342_0005':45,'lane1_f795_0222':220,'lane1_f84_0077':85}.get(jid,0)
            track=[r for r in track if r['frame']>=minimum]
            boxes,full=trajectory(track,n)
            selected=[]
            for q in [.08,.38,.68,.94]:
                k=int(round(q*(len(full)-1)));r=full[k]
                if r not in selected:selected.append(r)
            while len(selected)<4:selected.append(full[-1])
            panels=[];pose_frames=[]
            for r in selected:
                frame=r['frame'];im=cv2.imread(str(files[m['start_frame']+frame]));x,y,w,h=r['box']
                pad=max(8,int(max(w,h)*.06));x0=max(0,int(x)-pad);y0=max(0,int(y)-pad);x1=min(1920,int(x+w)+pad);y1=min(1080,int(y+h)+pad)
                crop=im[y0:y1,x0:x1];scale=min(420/crop.shape[1],480/crop.shape[0]);crop=cv2.resize(crop,None,fx=scale,fy=scale)
                panel=np.full((512,448,3),110,np.uint8);xx=(448-crop.shape[1])//2;yy=(512-crop.shape[0])//2;panel[yy:yy+crop.shape[0],xx:xx+crop.shape[1]]=crop
                panels.append(panel);pose_frames.append(frame)
            contact=np.concatenate([np.concatenate(panels[:2],axis=1),np.concatenate(panels[2:],axis=1)])
            cv2.imwrite(str(job/'input.png'),contact)
            (job/'prompt.txt').write_text(PROMPT)
            entry={'id':jid,'clip':c,'source_meta':str(mp),'source_start_frame':m['start_frame'],'source_frames':len(files),'track':track,'pose_frames':pose_frames,'boxes':boxes,'status':'prepared','method':'four AI views + smooth source track','input_sha256':hashlib.sha256((job/'input.png').read_bytes()).hexdigest()}
            atomic_json(job/'job.json',entry)
            print(json.dumps({'prepared':jid,'number':number+1,'total':len(clips),'observations':len(track),'poses':pose_frames,'frames':len(boxes)}),flush=True)
        except Exception as e:
            atomic_json(job/'error.json',{'stage':'prepare','error':str(e)})
            print(json.dumps({'error':jid,'message':str(e)}),flush=True)

def ingest(root,jid,image_path):
    job=root/'repaired/jobs'/jid;entry=json.loads((job/'job.json').read_text())
    if len(set(entry.get('excluded_poses',[])))>2:raise RuntimeError('At least two reviewed poses are required')
    image_path=Path(image_path)
    if image_path.resolve()!=(job/'generated.png').resolve():shutil.copy2(image_path,job/'generated.png')
    im=cv2.imread(str(image_path),cv2.IMREAD_UNCHANGED)
    if im is None:raise RuntimeError('Cannot decode generated image')
    bgr=im[:,:,:3].astype(np.float32)/255
    excess=bgr[:,:,1]-np.maximum(bgr[:,:,0],bgr[:,:,2])
    hard_bg=((excess>.32)&(bgr[:,:,1]>.5)).astype(np.uint8)
    near_bg=cv2.dilate(hard_bg,np.ones((7,7),np.uint8)).astype(bool)
    # Dark green paint is foreground. Only key high-brightness green and
    # its immediate antialiased boundary; do not desaturate vehicle interiors.
    a=np.ones(excess.shape,np.float32)
    a[near_bg]=np.clip(1-(excess[near_bg]-.025)/.32,0,1)
    if im.shape[2]==4:a*=im[:,:,3]/255
    spill=near_bg&(excess>.06);bgr[:,:,1][spill]=np.maximum(bgr[:,:,0],bgr[:,:,2])[spill]
    rgba=np.dstack([np.round(bgr*255).astype(np.uint8),np.round(a*255).astype(np.uint8)])
    h,w=rgba.shape[:2];parts=[]
    for k in range(4):
        if k in entry.get('excluded_poses',[]):
            parts.append(np.zeros((1,1,4),np.uint8));continue
        y0=round(k//2*h/2);y1=round((k//2+1)*h/2);x0=round(k%2*w/2);x1=round((k%2+1)*w/2)
        part=rgba[y0:y1,x0:x1].copy();mask=(part[:,:,3]>80).astype(np.uint8)
        count,labels,stats,_=cv2.connectedComponentsWithStats(mask,8)
        if count<2:raise RuntimeError(f'Panel {k+1} is empty')
        main=1+np.argmax(stats[1:,cv2.CC_STAT_AREA]);main_area=stats[main,cv2.CC_STAT_AREA]
        if main_area<part.shape[0]*part.shape[1]*.025:raise RuntimeError(f'Panel {k+1} lacks a substantial vehicle')
        # Remove detached keying noise, keeping near-body detail and mirrors.
        component=(labels==main).astype(np.uint8);near=cv2.dilate(component,np.ones((15,15),np.uint8))
        part[:,:,3]*=near
        yy,xx=np.where(part[:,:,3]>8);l=max(0,int(xx.min())-2);r=min(part.shape[1],int(xx.max())+3);t=max(0,int(yy.min())-2);b=min(part.shape[0],int(yy.max())+3)
        if min(xx.min(),yy.min(),part.shape[1]-1-xx.max(),part.shape[0]-1-yy.max())<2:raise RuntimeError(f'Panel {k+1} vehicle touches the edge')
        part=part[t:b,l:r];scale=min(320/part.shape[1],384/part.shape[0],1)
        f=part.astype(np.float32)/255;f[:,:,:3]*=f[:,:,3:4]
        f=cv2.resize(f,None,fx=scale,fy=scale,interpolation=cv2.INTER_AREA)
        f[:,:,:3]=np.divide(f[:,:,:3],f[:,:,3:4],out=np.zeros_like(f[:,:,:3]),where=f[:,:,3:4]>1e-6)
        part=np.round(np.clip(f,0,1)*255).astype(np.uint8);parts.append(part)
    cw=max(p.shape[1] for p in parts);ch=max(p.shape[0] for p in parts);sheet=np.zeros((ch,cw*4,4),np.uint8);poses=[]
    for k,p in enumerate(parts):
        sheet[:p.shape[0],k*cw:k*cw+p.shape[1]]=p
        if k not in entry.get('excluded_poses',[]):poses.append({'frame':entry['pose_frames'][k],'x':k*cw,'y':0,'w':p.shape[1],'h':p.shape[0]})
    output=root/'repaired/clips'/f'{jid}.png';cv2.imwrite(str(output),sheet)
    entry.update(status='ingested',key_version=2,poses=poses,asset=str(output),asset_sha256=hashlib.sha256(output.read_bytes()).hexdigest())
    atomic_json(job/'job.json',entry);print(json.dumps({'ingested':jid,'size':list(sheet.shape[1::-1]),'alpha_transparent':int(np.sum(sheet[:,:,3]==0))}))

def build(root):
    expected=unique_clips(root);clips=[];missing=[]
    for original in expected:
        jid=Path(original['sheet']).stem;p=root/'repaired/jobs'/jid/'job.json'
        if not p.exists():missing.append(jid);continue
        j=json.loads(p.read_text())
        if j['status']!='ingested':missing.append(jid);continue
        motion=p.with_name('motion.json')
        if not motion.exists():missing.append(jid+' (motion)');continue
        im=cv2.imread(j['asset'],cv2.IMREAD_UNCHANGED)
        if im is None or im.shape[2]!=4 or j.get('key_version')!=2:missing.append(jid+' (alpha)');continue
        boxes=json.loads(motion.read_text())['boxes']
        # A crowded approach may only become trackable later. Do not play its
        # extrapolated invisible path through the sky before reaching the bridge.
        offset=next((i for i,b in enumerate(boxes) if b[1]+b[3]>430),0)
        boxes=boxes[offset:]
        # Smoothing can pull the last sample a few pixels back inside the plate.
        velocity=np.array(boxes[-1])-np.array(boxes[-2])
        velocity[1]=max(.5,velocity[1]);velocity[2:]=np.maximum(0,velocity[2:])
        for _ in range(100):
            b=boxes[-1]
            if b[1]>=1082 or b[0]>=1922 or b[0]+b[2]<=-2:break
            boxes.append((np.array(b)+velocity).tolist())
        poses=[{**p,'frame':p['frame']-offset} for p in j['poses']]
        clips.append({**original,'cars':1,'sheet':f'repaired/clips/{jid}.png','boxes':boxes,'poses':poses,'sourceFrameOffset':offset,'cell':[im.shape[1]//4,im.shape[0]],'cols':4,'sub':1,'repairVersion':1})
    if missing:raise RuntimeError(f'{len(missing)} unfinished jobs: '+', '.join(missing))
    manifest={'fps':25,'lanes':4,'repairVersion':1,'clips':clips}
    atomic_json(root/'manifest-repaired.json',manifest);print(f'Built {len(clips)} unique repaired clips')

def status(root):
    expected=unique_clips(root);counts={};missing=[]
    for c in expected:
        jid=Path(c['sheet']).stem;p=root/'repaired/jobs'/jid/'job.json';e=p.with_name('error.json')
        s=json.loads(p.read_text())['status'] if p.exists() else 'error' if e.exists() else 'pending'
        counts[s]=counts.get(s,0)+1
        if s=='error':missing.append({'id':jid,**json.loads(e.read_text())})
    print(json.dumps({'total':len(expected),'counts':counts,'errors':missing},indent=2))

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,default=DEFAULT)
    sub=ap.add_subparsers(dest='command',required=True);p=sub.add_parser('prepare');p.add_argument('--only',nargs='*');p.add_argument('--refresh',action='store_true')
    p=sub.add_parser('ingest');p.add_argument('job');p.add_argument('image')
    sub.add_parser('build');sub.add_parser('status');sub.add_parser('reingest');args=ap.parse_args()
    if args.command=='prepare':prepare(args.root,args.only,args.refresh)
    elif args.command=='ingest':ingest(args.root,args.job,args.image)
    elif args.command=='build':build(args.root)
    elif args.command=='status':status(args.root)
    elif args.command=='reingest':
        failures=[]
        for p in sorted((args.root/'repaired/jobs').glob('*/generated.png')):
            try:ingest(args.root,p.parent.name,p)
            except Exception as e:failures.append({'id':p.parent.name,'error':str(e)})
        if failures:raise RuntimeError(json.dumps(failures,indent=2))
