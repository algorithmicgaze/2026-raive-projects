# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy"]
# ///
"""Remove harvested clips that fail the harvester's sanity rules
(merged packs, impossibly short crossings)."""
import json, shutil, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from lanes import bound_x

root = Path(sys.argv[1]); H = 1080; MIN_LEN = 50
bad = []
for meta in sorted(root.glob("lane*/*/meta.json")):
    m = json.loads(meta.read_text()); lane = m["lane"] - 1; boxes = m["boxes"]
    why = None
    if len(boxes) < MIN_LEN:
        why = "short"
    for x, y, w, h in boxes:
        yb = min(y + h, H); lane_w = bound_x(lane + 1, yb) - bound_x(lane, yb)
        if w > 1.3 * lane_w or h > 0.8 * (H - 425):
            why = why or "too big"; break
    if why:
        bad.append((meta.parent, why))
for d, why in bad:
    print(f"remove {d.relative_to(root)}: {why}"); shutil.rmtree(d)
print(f"removed {len(bad)}; left:", {k: len(list(root.glob(f"lane{k}/*/meta.json"))) for k in (1, 2, 3, 4)})
