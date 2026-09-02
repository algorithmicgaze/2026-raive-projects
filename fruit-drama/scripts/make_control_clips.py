"""Cut a landmarks.jsonl into control clips for VACE.

Takes runs of consecutive frames that have a pose and writes for each clip:
  <out>/<name>_<k>.mp4              skeleton on black, 480x832, 16 fps (--style mediapipe | openpose)
  <out>/<name>_<k>.landmarks.jsonl  the landmarks used, one row per output frame

Reads two formats: render_conditioning rows ({name, poses, faces}, already in
the target aspect) and video_to_skeleton rows ({frame, width, height,
landmarks: 33 x [x, y, z, visibility]} on the source frame). The second is
cover-cropped to the target aspect, so the body spans the full height.

Short detection gaps are bridged by linear interpolation of the landmarks.
Runs shorter than --frames but at least --min-run long are extended by
ping-pong (forward, then backward): a gesture and its return.

  uv run scripts/make_control_clips.py media/dataset_apple_ceo_v2/apple_ceo_landmarks.jsonl media/control apple_ceo
"""

import argparse
import json
import subprocess
from pathlib import Path

import cv2
import numpy as np

from render_conditioning import render_landmarks

# OpenPose (COCO-18) joints from MediaPipe's 33 pose landmarks. Index 1 (neck)
# is the midpoint of the shoulders. Order: nose, neck, R shoulder, R elbow,
# R wrist, L shoulder, L elbow, L wrist, R hip, R knee, R ankle, L hip, L knee,
# L ankle, R eye, L eye, R ear, L ear.
MP_TO_OPENPOSE = [0, None, 12, 14, 16, 11, 13, 15, 24, 26, 28, 23, 25, 27, 5, 2, 8, 7]
OPENPOSE_LIMBS = [(1, 2), (1, 5), (2, 3), (3, 4), (5, 6), (6, 7), (1, 8), (8, 9), (9, 10), (1, 11), (11, 12),
                  (12, 13), (1, 0), (0, 14), (14, 16), (0, 15), (15, 17)]
OPENPOSE_COLORS = [(255, 0, 0), (255, 85, 0), (255, 170, 0), (255, 255, 0), (170, 255, 0), (85, 255, 0), (0, 255, 0),
                   (0, 255, 85), (0, 255, 170), (0, 255, 255), (0, 170, 255), (0, 85, 255), (0, 0, 255), (85, 0, 255),
                   (170, 0, 255), (255, 0, 255), (255, 0, 170), (255, 0, 85)]


def render_openpose(pose, width, height, stick=4):
    """Pose as the OpenPose body drawing VACE was trained on: colored limbs
    (60 % blend) and joint discs on black. RGB uint8."""
    canvas = np.zeros((height, width, 3), np.uint8)
    neck = ((pose[11][0] + pose[12][0]) / 2, (pose[11][1] + pose[12][1]) / 2)
    pts = [neck if i is None else pose[i] for i in MP_TO_OPENPOSE]
    pts = [(x * width, y * height) for x, y in pts]
    for (a, b), color in zip(OPENPOSE_LIMBS, OPENPOSE_COLORS):
        (x0, y0), (x1, y1) = pts[a], pts[b]
        length = ((x0 - x1) ** 2 + (y0 - y1) ** 2) ** 0.5
        angle = np.degrees(np.arctan2(y0 - y1, x0 - x1))
        poly = cv2.ellipse2Poly((int((x0 + x1) / 2), int((y0 + y1) / 2)), (int(length / 2), stick), int(angle), 0, 360, 1)
        limb = canvas.copy()
        cv2.fillConvexPoly(limb, poly, color)
        canvas = cv2.addWeighted(canvas, 0.4, limb, 0.6, 0)
    for (x, y), color in zip(pts, OPENPOSE_COLORS):
        cv2.circle(canvas, (int(x), int(y)), stick, color, -1)
    return canvas


def fit_points(pts, src_w, src_h, width, height):
    """Normalized points on a src_w x src_h frame -> normalized points on the
    width x height frame that covers it (scale to fill, center crop)."""
    s = max(width / src_w, height / src_h)
    ox, oy = (src_w * s - width) / 2, (src_h * s - height) / 2
    return [((x * src_w * s - ox) / width, (y * src_h * s - oy) / height) for x, y in pts]


def load_rows(path, width, height):
    rows = [json.loads(l) for l in path.read_text().splitlines()]
    if rows and "landmarks" in rows[0]:
        rows = [{
            "name": r["frame"],
            "poses": [fit_points([p[:2] for p in r["landmarks"]], r["width"], r["height"], width, height)]
                     if r["landmarks"] else [],
            "faces": [],
        } for r in rows]
    return rows


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
    ap.add_argument("--style", choices=["mediapipe", "openpose"], default="mediapipe",
                    help="mediapipe: white lines like Figment; openpose: colored OpenPose body, what VACE expects")
    args = ap.parse_args()

    rows = load_rows(args.landmarks, args.width, args.height)
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
            raw = path.with_suffix(".raw.mp4")
            writer = cv2.VideoWriter(str(raw), cv2.VideoWriter_fourcc(*"mp4v"), args.fps, (args.width, args.height))
            with open(path.with_suffix(".landmarks.jsonl"), "w") as f:
                for row in chunk:
                    if args.style == "openpose":
                        img = render_openpose(row["poses"][0], args.width, args.height)
                    else:
                        img = render_landmarks(row["poses"][:1], row["faces"][:1], args.width, args.height)
                    writer.write(cv2.cvtColor(img, cv2.COLOR_RGB2BGR))
                    f.write(json.dumps({"name": row["name"], "poses": row["poses"][:1], "faces": row["faces"][:1]}) + "\n")
            writer.release()
            # H.264: OpenCV's mp4v (MPEG-4 part 2) does not play in Chromium, so Figment cannot load it.
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(raw), "-c:v", "libx264", "-pix_fmt", "yuv420p",
                            "-crf", "18", str(path)], check=True)
            raw.unlink()
            print(path, f"source frames {chunk[0]['name']}..{max(r['name'] for r in chunk)}")
            k += 1
    print(f"{k} control clips of {args.frames} frames")


if __name__ == "__main__":
    main()
