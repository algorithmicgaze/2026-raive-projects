# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy", "opencv-python-headless"]
# ///
"""Pack the clip library for the Figment node: one RGBA sprite sheet per
clip (frames side by side in rows) and one manifest.json with, per clip,
the lane, the sheet file, the cell size and the per-frame box in plate
coordinates.

  uv run instrument/pack_clips.py output-clips output-highway
"""
import argparse, json
from pathlib import Path
import cv2, numpy as np

ap = argparse.ArgumentParser()
ap.add_argument("srcs", type=Path, nargs="+", help="clip folders, the last argument is the output folder")
ap.add_argument("--sub", type=int, default=2, help="store every Nth frame; positions stay per frame")
ap.add_argument("--max-per-kind", type=int, default=20, help="cap per lane and kind (car, truck, group)")
args = ap.parse_args()
srcs, out = args.srcs[:-1], args.srcs[-1]
per_kind = {}
(out / "clips").mkdir(parents=True, exist_ok=True)
manifest = {"fps": 25, "lanes": 4, "clips": []}
for meta in sorted(m for src in srcs for m in src.glob("lane*/*/meta.json")):
    d = meta.parent; m = json.loads(meta.read_text()); n = len(m["boxes"])
    key = (m["lane"], m.get("kind", "car"))
    if per_kind.get(key, 0) >= args.max_per_kind:
        continue
    per_kind[key] = per_kind.get(key, 0) + 1
    sub = args.sub
    stored = [cv2.imread(str(d / f"{i:03d}.png"), cv2.IMREAD_UNCHANGED) for i in range(0, n, sub)]
    cw = max(f.shape[1] for f in stored); ch = max(f.shape[0] for f in stored)
    cols = max(1, min(len(stored), 4096 // cw)); rows = -(-len(stored) // cols)
    sheet = np.zeros((rows * ch, cols * cw, 4), np.uint8)
    for j, f in enumerate(stored):
        r, c = divmod(j, cols)
        sheet[r * ch:r * ch + f.shape[0], c * cw:c * cw + f.shape[1]] = f
    name = f"{d.parent.name}_{d.name}.png"
    cv2.imwrite(str(out / "clips" / name), sheet)
    # per frame: position of that frame, size of the stored frame it draws
    boxes = [[int(b[0]), int(b[1]), int(stored[i // sub].shape[1]), int(stored[i // sub].shape[0])] for i, b in enumerate(m["boxes"])]
    manifest["clips"].append({"id": d.name, "lane": m["lane"], "cars": m.get("cars", 1), "sheet": f"clips/{name}", "cell": [cw, ch], "cols": cols,
                              "sub": sub, "boxes": boxes})
(out / "manifest.json").write_text(json.dumps(manifest))
print("packed", len(manifest["clips"]), "clips", {f"L{k[0]} {k[1]}": v for k, v in sorted(per_kind.items())}, "->", out)
