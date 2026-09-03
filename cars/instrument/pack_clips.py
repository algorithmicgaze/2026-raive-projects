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
import json, sys
from pathlib import Path
import cv2, numpy as np

src, out = Path(sys.argv[1]), Path(sys.argv[2])
(out / "clips").mkdir(parents=True, exist_ok=True)
manifest = {"fps": 25, "lanes": 4, "clips": []}
for meta in sorted(src.glob("lane*/*/meta.json")):
    d = meta.parent; m = json.loads(meta.read_text()); n = len(m["boxes"])
    frames = [cv2.imread(str(d / f"{i:03d}.png"), cv2.IMREAD_UNCHANGED) for i in range(n)]
    cw = max(f.shape[1] for f in frames); ch = max(f.shape[0] for f in frames)
    cols = max(1, min(n, 4096 // cw)); rows = -(-n // cols)
    sheet = np.zeros((rows * ch, cols * cw, 4), np.uint8)
    for i, f in enumerate(frames):
        r, c = divmod(i, cols)
        sheet[r * ch:r * ch + f.shape[0], c * cw:c * cw + f.shape[1]] = f
    name = f"{d.parent.name}_{d.name}.png"
    cv2.imwrite(str(out / "clips" / name), sheet)
    manifest["clips"].append({"id": d.name, "lane": m["lane"], "sheet": f"clips/{name}", "cell": [cw, ch], "cols": cols,
                              "boxes": [[int(v) for v in b] for b in m["boxes"]]})
(out / "manifest.json").write_text(json.dumps(manifest))
counts = {k: sum(c["lane"] == k for c in manifest["clips"]) for k in (1, 2, 3, 4)}
print("packed", len(manifest["clips"]), "clips", counts, "->", out)
