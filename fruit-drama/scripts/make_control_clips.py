"""Cut a landmarks.jsonl into control clips for VACE.

Takes runs of consecutive frames that have a pose, subsamples them to the
VACE frame rate, and writes for each segment:
  <out>/<name>_<k>.mp4            white skeleton + face on black, 480x832, 16 fps
  <out>/<name>_<k>.landmarks.jsonl  the landmarks used, one row per output frame

  uv run scripts/make_control_clips.py media/dataset_apple_ceo/apple_ceo_landmarks.jsonl media/control apple_ceo
"""

import argparse
import json
from pathlib import Path

import cv2

from render_conditioning import render_landmarks


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("landmarks", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("name")
    ap.add_argument("--frames", type=int, default=81)
    ap.add_argument("--stride", type=int, default=2, help="source frames per output frame (30 fps -> 15 fps)")
    ap.add_argument("--width", type=int, default=480)
    ap.add_argument("--height", type=int, default=832)
    ap.add_argument("--fps", type=int, default=16)
    args = ap.parse_args()

    rows = [json.loads(l) for l in args.landmarks.read_text().splitlines()]
    need = (args.frames - 1) * args.stride + 1
    segments, run = [], []
    for row in rows:
        if row["poses"]:
            run.append(row)
        else:
            segments.append(run); run = []
    segments.append(run)

    args.out.mkdir(parents=True, exist_ok=True)
    k = 0
    for seg in segments:
        for start in range(0, len(seg) - need + 1, need):
            chunk = seg[start:start + need:args.stride][:args.frames]
            path = args.out / f"{args.name}_{k:03d}.mp4"
            writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), args.fps, (args.width, args.height))
            with open(path.with_suffix(".landmarks.jsonl"), "w") as f:
                for row in chunk:
                    img = render_landmarks(row["poses"][:1], row["faces"][:1], args.width, args.height)
                    writer.write(cv2.cvtColor(img, cv2.COLOR_RGB2BGR))
                    f.write(json.dumps(row) + "\n")
            writer.release()
            print(path, f"frames {chunk[0]['name']}..{chunk[-1]['name']}")
            k += 1
    print(f"{k} control clips of {args.frames} frames")


if __name__ == "__main__":
    main()
