"""Convert a Figment Detect Pose export to our landmarks.jsonl format.

Figment writes one line per frame:
  {"frame": 0, "width": 1024, "height": 1024, "landmarks": [[x, y, z, visibility] * 33]}

We write one line per frame:
  {"name": "00000", "poses": [[[x, y] * 33]], "faces": []}

with x remapped through a center crop to the target aspect (default 480:832,
the VACE portrait size), so the skeleton lands where render_landmarks draws it.

  uv run scripts/import_figment_skeleton.py skeletons/myrthe.jsonl media/driving_lm/myrthe/myrthe_landmarks.jsonl
"""

import argparse
import json
from pathlib import Path


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("src", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--width", type=int, default=480, help="target frame width (aspect only)")
    ap.add_argument("--height", type=int, default=832, help="target frame height (aspect only)")
    ap.add_argument("--min-visibility", type=float, default=0.0,
                    help="drop a frame when any of the 33 landmarks is below this visibility")
    args = ap.parse_args()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    kept = dropped = 0
    with open(args.src) as f, open(args.out, "w") as out:
        for line in f:
            if not line.strip():
                continue
            row = json.loads(line)
            src_w, src_h = row["width"], row["height"]
            target = args.width / args.height
            # center crop of the source frame to the target aspect, in normalized units
            if src_w / src_h > target:
                crop_w = src_h * target / src_w
                x0, sx, y0, sy = (1 - crop_w) / 2, 1 / crop_w, 0.0, 1.0
            else:
                crop_h = src_w / target / src_h
                x0, sx, y0, sy = 0.0, 1.0, (1 - crop_h) / 2, 1 / crop_h
            lm = row["landmarks"]
            if len(lm) != 33 or min(l[3] for l in lm) < args.min_visibility:
                dropped += 1
                continue
            pose = [(round((l[0] - x0) * sx, 5), round((l[1] - y0) * sy, 5)) for l in lm]
            out.write(json.dumps({"name": f"{row['frame']:05d}", "poses": [pose], "faces": []}) + "\n")
            kept += 1
    print(f"{kept} frames written, {dropped} dropped -> {args.out}")


if __name__ == "__main__":
    main()
