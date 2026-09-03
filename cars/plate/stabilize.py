# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy", "opencv-python-headless", "tqdm"]
# ///
"""Align every frame to frame 0 with a similarity transform (shift,
rotation, scale) estimated from SIFT matches on the static parts of the
scene. The road polygon is masked out so vehicles cannot vote. Transforms
are saved (as 1080p affines) so they can be scaled and reapplied to the
4K frames later."""
import argparse
from pathlib import Path
import cv2, numpy as np
from tqdm import tqdm

ROAD_POLY = np.array([(780, 400), (1300, 400), (1920, 820), (1920, 1080), (200, 1080)])

ap = argparse.ArgumentParser()
ap.add_argument("frames", type=Path)
ap.add_argument("out", type=Path)
ap.add_argument("--transforms", type=Path, default=Path("output-plate/transforms.npy"))
ap.add_argument("--ref", type=Path, default=None, help="reference frame (default: first frame in folder)")
ap.add_argument("--est-scale", type=float, default=1.0, help="estimate on a downscaled copy, warp at full size")
args = ap.parse_args()
args.out.mkdir(parents=True, exist_ok=True)

files = sorted(args.frames.glob("*.jpg"))
ref = cv2.imread(str(args.ref or files[0]))
h, w = ref.shape[:2]
mask = np.full((h, w), 255, np.uint8)
cv2.fillPoly(mask, [ROAD_POLY], 0)
es = args.est_scale
def small(img):
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    return g if es == 1.0 else cv2.resize(g, None, fx=es, fy=es, interpolation=cv2.INTER_AREA)
mask_s = mask if es == 1.0 else cv2.resize(mask, None, fx=es, fy=es, interpolation=cv2.INTER_NEAREST)
sift = cv2.SIFT_create(nfeatures=4000)
kp0, des0 = sift.detectAndCompute(small(ref), mask_s)
pts0 = np.float32([k.pt for k in kp0])
matcher = cv2.BFMatcher(cv2.NORM_L2)
transforms = np.zeros((len(files), 2, 3), np.float64)
inliers = np.zeros(len(files), int)
for i, f in enumerate(tqdm(files, desc="stabilize")):
    img = cv2.imread(str(f))
    kp, des = sift.detectAndCompute(small(img), mask_s)
    m = matcher.knnMatch(des, des0, k=2)
    good = [a for a, b in m if a.distance < 0.75 * b.distance]
    src = np.float32([kp[g.queryIdx].pt for g in good])
    dst = pts0[[g.trainIdx for g in good]]
    A, inl = cv2.estimateAffinePartial2D(src, dst, method=cv2.RANSAC, ransacReprojThreshold=1.5, maxIters=5000, confidence=0.999)
    if A is None:
        A = transforms[i - 1]
    else:
        A = A.copy(); A[:, 2] /= es
    transforms[i] = A
    inliers[i] = 0 if inl is None else int(inl.sum())
    warped = cv2.warpAffine(img, A, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REFLECT)
    cv2.imwrite(str(args.out / f.name), warped, [cv2.IMWRITE_JPEG_QUALITY, 95])
np.save(args.transforms, transforms)
t = transforms
ang = np.degrees(np.arctan2(t[:, 1, 0], t[:, 0, 0])); sc = np.hypot(t[:, 0, 0], t[:, 1, 0])
print("inliers min/median", inliers.min(), int(np.median(inliers)))
print("tx %.2f..%.2f  ty %.2f..%.2f  rot %.3f..%.3f deg  scale %.4f..%.4f" % (t[:,0,2].min(), t[:,0,2].max(), t[:,1,2].min(), t[:,1,2].max(), ang.min(), ang.max(), sc.min(), sc.max()))
