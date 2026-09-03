# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy", "opencv-python-headless", "tqdm"]
# ///
"""Measure camera drift per frame: sub-pixel translation of a static,
textured region (the graffiti panel on the bridge) against frame 0,
via phase correlation on a Hann-windowed crop."""
import sys
from pathlib import Path
import cv2, numpy as np
from tqdm import tqdm

folder = Path(sys.argv[1]); out = Path(sys.argv[2]); out.mkdir(exist_ok=True)
files = sorted(folder.glob("*.jpg"))
x0, y0, x1, y1 = 880, 280, 1440, 420   # graffiti panel, 1080p coords
def crop(f):
    g = cv2.imread(str(f), cv2.IMREAD_GRAYSCALE)[y0:y1, x0:x1].astype(np.float32)
    return g
ref = crop(files[0]); win = cv2.createHanningWindow(ref.shape[::-1], cv2.CV_32F)
shifts = np.zeros((len(files), 3))
for i, f in enumerate(tqdm(files)):
    (dx, dy), resp = cv2.phaseCorrelate(ref, crop(f), win)
    shifts[i] = dx, dy, resp
np.save(out / "drift.npy", shifts)
print("dx range %.2f..%.2f  dy range %.2f..%.2f  (px at 1080p)" % (shifts[:,0].min(), shifts[:,0].max(), shifts[:,1].min(), shifts[:,1].max()))
print("frames with |shift|>0.5px: %d of %d" % ((np.hypot(shifts[:,0], shifts[:,1]) > 0.5).sum(), len(files)))
# plot
H, W = 300, 1280; img = np.full((H, W, 3), 255, np.uint8)
n = len(files); mid = H // 2; scale = 40  # px per image px
cv2.line(img, (0, mid), (W, mid), (200, 200, 200), 1)
for k in (-2, -1, 1, 2):
    y = mid - k * scale; cv2.line(img, (0, y), (W, y), (230, 230, 230), 1)
    cv2.putText(img, f"{k:+d} px", (4, y - 3), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (120, 120, 120), 1)
for c, col in ((0, (190, 90, 20)), (1, (30, 100, 220))):
    pts = np.array([(int(i * W / n), int(mid - shifts[i, c] * scale)) for i in range(n)])
    cv2.polylines(img, [pts], False, col, 1, cv2.LINE_AA)
cv2.putText(img, "dx (blue)  dy (orange)", (W - 220, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)
cv2.imwrite(str(out / "drift.png"), img)
