# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy", "opencv-python-headless", "tqdm"]
# ///
"""Find train passages: seconds where the railway strip differs strongly
from the plate. Writes a timeline and prints the passages."""
import sys
from pathlib import Path
import cv2, numpy as np
from tqdm import tqdm

RAIL_ROI = np.array([(0, 470), (470, 400), (640, 425), (600, 520), (330, 1080), (0, 1080)], dtype=np.int32)
frames = sorted(Path(sys.argv[1]).glob("*.jpg")); out = Path(sys.argv[2])
plate = cv2.imread(sys.argv[3]).astype(np.int16)
mask = np.zeros(plate.shape[:2], np.uint8); cv2.fillPoly(mask, [RAIL_ROI], 255); mask = mask > 0
occ = np.zeros(len(frames))
for i, f in enumerate(tqdm(frames)):
    d = np.abs(cv2.imread(str(f)).astype(np.int16) - plate).max(-1)
    d = cv2.blur(d.astype(np.float32), (5, 5)) > 40
    occ[i] = d[mask].mean()
np.save(out / "rail_occupancy.npy", occ)
H, W = 200, 1280; img = np.full((H, W, 3), 255, np.uint8); n = len(frames)
for x in range(W):
    v = occ[int(x * n / W):max(int((x + 1) * n / W), int(x * n / W) + 1)].mean()
    cv2.line(img, (x, H - 20), (x, int(H - 20 - v * (H - 40))), (60, 60, 200), 1)
for m in range(0, 31, 5):
    x = int(m * 60 / n * W); cv2.line(img, (x, H - 20), (x, H - 14), (0, 0, 0), 1); cv2.putText(img, f"{m} min", (x + 3, H - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 0), 1)
cv2.imwrite(str(out / "rail_occupancy.png"), img)
print("baseline (median):", round(float(np.median(occ)), 3))
thr = max(0.15, 3 * np.median(occ)); on = occ > thr
i = 0
while i < n:
    if on[i]:
        j = i
        while j < n and on[j]: j += 1
        # frames are keyframes, one per 0.96 s: report film seconds
        if j - i >= 3: print(f"train {i * 0.96:.0f}s .. {j * 0.96:.0f}s  ({(j - i) * 0.96:.0f} s, peak {occ[i:j].max():.2f})")
        i = j
    else: i += 1
