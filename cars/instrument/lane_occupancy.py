# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy", "opencv-python-headless", "tqdm"]
# ///
"""Per-lane occupancy per second: the fraction of each lane's pixels
that differ from the plate, over the aligned 1 fps keyframes. This is
the first version of the instrument's own input signal, and it tells us
where in the film each lane flows freely."""
import sys
from pathlib import Path
import cv2, numpy as np
from tqdm import tqdm
sys.path.insert(0, str(Path(__file__).parent))
from lanes import lane_polygon

frames = sorted(Path(sys.argv[1]).glob("*.jpg")); out = Path(sys.argv[2]); out.mkdir(exist_ok=True)
plate = cv2.imread(sys.argv[3]).astype(np.int16)
masks = []
for k in range(4):
    m = np.zeros(plate.shape[:2], np.uint8); cv2.fillPoly(m, [lane_polygon(k, y_top=480).astype(np.int32)], 255); masks.append(m > 0)
occ = np.zeros((len(frames), 4))
for i, f in enumerate(tqdm(frames)):
    d = np.abs(cv2.imread(str(f)).astype(np.int16) - plate).max(-1)
    d = cv2.blur(d.astype(np.float32), (5, 5)) > 28
    occ[i] = [d[m].mean() for m in masks]
np.save(out / "lane_occupancy.npy", occ)
H, W = 4 * 90, 1280; img = np.full((H, W, 3), 255, np.uint8); n = len(frames)
cols = [(0, 160, 230), (60, 170, 60), (200, 60, 200), (220, 150, 0)]
for k in range(4):
    y1 = (k + 1) * 90 - 8
    for x in range(W):
        v = occ[int(x * n / W):max(int((x + 1) * n / W), int(x * n / W) + 1), k].mean()
        cv2.line(img, (x, y1), (x, int(y1 - v * 75)), cols[k], 1)
    cv2.putText(img, f"lane {k + 1}", (6, k * 90 + 16), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)
    for m in range(0, 31, 5):
        x = int(m * 60 / n * W); cv2.line(img, (x, y1), (x, y1 + 5), (0, 0, 0), 1)
cv2.imwrite(str(out / "lane_occupancy.png"), img)
w = 60
for k in range(4):
    m = np.convolve(occ[:, k], np.ones(w) / w, mode="valid"); order = np.argsort(m); picked = []
    for i in order:
        if all(abs(i - p) >= w for p in picked): picked.append(int(i))
        if len(picked) == 4: break
    print(f"lane {k + 1}: mean {occ[:, k].mean():.2f}  lightest 60 s windows: " + ", ".join(f"{p}s ({m[p]:.2f})" for p in sorted(picked)))
