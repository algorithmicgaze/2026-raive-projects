"""Cut a landmarks.jsonl into control clips for VACE.

Takes runs of consecutive frames that have a pose and writes for each clip:
  <out>/<name>_<k>.mp4              white skeleton + face on black, 480x832, 16 fps
  <out>/<name>_<k>.landmarks.jsonl  the landmarks used, one row per output frame

Short detection gaps are bridged by linear interpolation of the landmarks.
Runs shorter than --frames but at least --min-run long are extended by
ping-pong (forward, then backward): a gesture and its return.

  uv run scripts/make_control_clips.py media/dataset_apple_ceo_v2/apple_ceo_landmarks.jsonl media/control apple_ceo
"""

import argparse
import json
from pathlib import Path

import cv2

from render_conditioning import render_landmarks


def lerp_points(a, b, t):
    return [(x0 + (x1 - x0) * t, y0 + (y1 - y0) * t) for (x0, y0), (x1, y1) in zip(a, b)]


def fill_gaps(rows, max_gap):
    """Interpolate the first pose (and face, when both ends have one) across
    gaps of at most `max_gap` frames."""
    rows = [dict(r) for r in rows]
    i = 0
    while i < len(rows):
        if rows[i]["poses"]:
            i += 1
            continue
        j = i
        while j < len(rows) and not rows[j]["poses"]:
            j += 1
        gap = j - i
        if 0 < i and j < len(rows) and gap <= max_gap:
            a, b = rows[i - 1], rows[j]
            for k in range(gap):
                t = (k + 1) / (gap + 1)
                rows[i + k]["poses"] = [lerp_points(a["poses"][0], b["poses"][0], t)]
                if a["faces"] and b["faces"]:
                    rows[i + k]["faces"] = [lerp_points(a["faces"][0], b["faces"][0], t)]
                rows[i + k]["interpolated"] = True
        i = j
    return rows


def runs_with_pose(rows):
    run, out = [], []
    for row in rows:
        if row["poses"]:
            run.append(row)
        elif run:
            out.append(run); run = []
    if run:
        out.append(run)
    return out


def pingpong(seq, length):
    """Extend seq to `length` frames by bouncing back and forth."""
    out, forward = [], True
    while len(out) < length:
        chunk = seq if forward else seq[-2:0:-1]
        out.extend(chunk)
        forward = not forward
    return out[:length]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("landmarks", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("name")
    ap.add_argument("--frames", type=int, default=81)
    ap.add_argument("--stride", type=int, default=1, help="source frames per output frame")
    ap.add_argument("--fill-gaps", type=int, default=6, help="interpolate detection gaps up to this many frames")
    ap.add_argument("--min-run", type=int, default=41, help="shortest run to keep; shorter runs are dropped")
    ap.add_argument("--width", type=int, default=480)
    ap.add_argument("--height", type=int, default=832)
    ap.add_argument("--fps", type=int, default=16)
    args = ap.parse_args()

    rows = [json.loads(l) for l in args.landmarks.read_text().splitlines()]
    rows = fill_gaps(rows, args.fill_gaps)
    runs = runs_with_pose(rows)
    print("runs after gap fill:", sorted((len(r) for r in runs), reverse=True)[:12])

    args.out.mkdir(parents=True, exist_ok=True)
    k = 0
    for run in runs:
        run = run[::args.stride]
        if len(run) < args.min_run:
            continue
        chunks = [run[i:i + args.frames] for i in range(0, len(run), args.frames)]
        for chunk in chunks:
            if len(chunk) < args.min_run:
                continue
            if len(chunk) < args.frames:
                chunk = pingpong(chunk, args.frames)
            path = args.out / f"{args.name}_{k:03d}.mp4"
            writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), args.fps, (args.width, args.height))
            with open(path.with_suffix(".landmarks.jsonl"), "w") as f:
                for row in chunk:
                    img = render_landmarks(row["poses"][:1], row["faces"][:1], args.width, args.height)
                    writer.write(cv2.cvtColor(img, cv2.COLOR_RGB2BGR))
                    f.write(json.dumps({"name": row["name"], "poses": row["poses"][:1], "faces": row["faces"][:1]}) + "\n")
            writer.release()
            print(path, f"source frames {chunk[0]['name']}..{max(r['name'] for r in chunk)}")
            k += 1
    print(f"{k} control clips of {args.frames} frames")


if __name__ == "__main__":
    main()
