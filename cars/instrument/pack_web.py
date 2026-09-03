# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy", "opencv-python-headless"]
# ///
"""Pack plate and clips for the in-browser player: half resolution,
WebP sprite sheets with alpha as data URIs, one JSON file, capped size.

  uv run instrument/pack_web.py output-clips output-plate-stab/iter3.png web.json --budget-mb 9
"""
import argparse, base64, json
from pathlib import Path
import cv2, numpy as np

ap = argparse.ArgumentParser()
ap.add_argument("clips", type=Path); ap.add_argument("plate", type=Path); ap.add_argument("out", type=Path)
ap.add_argument("--scale", type=float, default=0.5); ap.add_argument("--budget-mb", type=float, default=9)
ap.add_argument("--quality", type=int, default=55)
ap.add_argument("--sub", type=int, default=2, help="store every Nth frame")
args = ap.parse_args()
s = args.scale

def uri(mime, buf):
    return f"data:{mime};base64," + base64.b64encode(buf).decode()

plate = cv2.imread(str(args.plate)); plate = cv2.resize(plate, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
ok, pb = cv2.imencode(".jpg", plate, [cv2.IMWRITE_JPEG_QUALITY, 82])
out = {"fps": 25, "width": plate.shape[1], "height": plate.shape[0], "plate": uri("image/jpeg", pb), "clips": []}
total = len(pb)

def pack(d):
    m = json.loads((d / "meta.json").read_text()); n = len(m["boxes"])
    frames = [cv2.imread(str(d / f"{i:03d}.png"), cv2.IMREAD_UNCHANGED) for i in range(n)]
    frames = [cv2.resize(f, (max(1, round(f.shape[1] * s)), max(1, round(f.shape[0] * s))), interpolation=cv2.INTER_AREA) for f in frames]
    # store every `sub`-th frame; positions stay per frame, the look updates at fps/sub
    sub = args.sub; keep = list(range(0, n, sub)); stored = [frames[i] for i in keep]
    # shelf packing: rows of frames at their own size, row height = tallest in the row
    W = 2048; rows, row, x = [], [], 0
    for i, f in enumerate(stored):
        if x + f.shape[1] > W and row:
            rows.append(row); row, x = [], 0
        row.append((i, x)); x += f.shape[1]
    rows.append(row)
    H = sum(max(stored[i].shape[0] for i, _ in r) for r in rows)
    sheet = np.zeros((H, W, 4), np.uint8); place = [None] * len(stored); y = 0
    for r in rows:
        rh = max(stored[i].shape[0] for i, _ in r)
        for i, x in r:
            f = stored[i]; sheet[y:y + f.shape[0], x:x + f.shape[1]] = f; place[i] = (x, y)
        y += rh
    fr = []
    for i in range(n):
        j = i // sub; f = stored[j]; b = m["boxes"][i]
        fr.append([round(b[0] * s), round(b[1] * s), f.shape[1], f.shape[0], *place[j]])
    ok, wb = cv2.imencode(".webp", sheet, [cv2.IMWRITE_WEBP_QUALITY, args.quality])
    return {"id": d.name, "lane": m["lane"], "frames": fr, "sheet": uri("image/webp", wb)}, len(wb)

# thin lanes first so they are never squeezed out, then the rich ones
dirs = sorted(args.clips.glob("lane*/*/meta.json"))
by_lane = {k: [d.parent for d in dirs if d.parent.parent.name == f"lane{k}"] for k in (1, 2, 3, 4)}
order = sorted(by_lane, key=lambda k: len(by_lane[k]))
for k in order:
    for d in by_lane[k]:
        c, size = pack(d)
        if total + size > args.budget_mb * 1e6:
            continue
        out["clips"].append(c); total += size
counts = {k: sum(c["lane"] == k for c in out["clips"]) for k in (1, 2, 3, 4)}
args.out.write_text(json.dumps(out))
print(f"packed {len(out['clips'])} clips {counts}, {total / 1e6:.1f} MB raw -> {args.out}")
