"""OpenPose control clip from a human video, for VACE.

VACE follows the drawing the OpenPose detector produces (body + hands + face,
`controlnet_aux`), not our own skeleton render. This script runs that detector
on source frames and writes <out>.mp4 at 16 fps, 480x832. Each source frame
is cover-cropped to the target aspect before detection, the same crop
`make_control_clips.py` applies to the landmarks.

Frames come from one of:
  --landmarks <clip>.landmarks.jsonl   the source frames of a control clip made by
                                       make_control_clips.py (its "name" field), in
                                       order, so the two clips pair frame by frame
  --start N --stride S --frames F      F frames from N, every S source frames

  uv run scripts/video_to_openpose.py media/driving/myrthe.mp4 media/control_dw/myrthe_000.mp4 \
      --landmarks media/control/myrthe_000.landmarks.jsonl
"""

import argparse
import json
from pathlib import Path

import cv2
import numpy as np
import torch
from PIL import Image

# controlnet_aux imports its MediaPipe face module at package import, and that
# module needs mediapipe<1 (`mp.solutions`). We only use OpenposeDetector, so a
# stub stands in for mediapipe when the installed version has no `solutions`.
try:
    import mediapipe

    mediapipe.solutions
except (ImportError, AttributeError):
    import sys
    from unittest import mock

    sys.modules["mediapipe"] = mock.MagicMock()
from controlnet_aux import OpenposeDetector  # noqa: E402


def crop_cover(bgr, width, height):
    h, w = bgr.shape[:2]
    s = max(width / w, height / h)
    bgr = cv2.resize(bgr, (round(w * s), round(h * s)), interpolation=cv2.INTER_AREA)
    h, w = bgr.shape[:2]
    x0, y0 = (w - width) // 2, (h - height) // 2
    return bgr[y0:y0 + height, x0:x0 + width]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--landmarks", type=Path, help="control clip .landmarks.jsonl; render its source frames")
    ap.add_argument("--start", type=int, default=0, help="first source frame")
    ap.add_argument("--frames", type=int, default=81)
    ap.add_argument("--stride", type=int, default=3, help="source frames per output frame")
    ap.add_argument("--width", type=int, default=480)
    ap.add_argument("--height", type=int, default=832)
    ap.add_argument("--fps", type=int, default=16)
    ap.add_argument("--no-hand-face", action="store_true", help="body only")
    args = ap.parse_args()

    if args.landmarks:
        names = [json.loads(l)["name"] for l in args.landmarks.read_text().splitlines()]
    else:
        names = [args.start + k * args.stride for k in range(args.frames)]
    wanted = set(names)

    detector = OpenposeDetector.from_pretrained("lllyasviel/Annotators").to("cuda" if torch.cuda.is_available() else "cpu")
    cap = cv2.VideoCapture(str(args.video))
    cap.set(cv2.CAP_PROP_POS_FRAMES, min(wanted))
    rendered = {}
    idx = min(wanted)
    while idx <= max(wanted):
        ok, bgr = cap.read()
        if not ok:
            break
        if idx in wanted:
            rgb = cv2.cvtColor(crop_cover(bgr, args.width, args.height), cv2.COLOR_BGR2RGB)
            pose = detector(Image.fromarray(rgb), detect_resolution=args.height, image_resolution=args.height,
                            hand_and_face=not args.no_hand_face, output_type="pil")
            rendered[idx] = cv2.cvtColor(np.array(pose.resize((args.width, args.height), Image.BILINEAR)), cv2.COLOR_RGB2BGR)
        idx += 1
    cap.release()
    missing = wanted - rendered.keys()
    if missing:
        raise SystemExit(f"{args.video}: {len(missing)} wanted frames not in the video, e.g. {sorted(missing)[:3]}")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(str(args.out), cv2.VideoWriter_fourcc(*"mp4v"), args.fps, (args.width, args.height))
    for name in names:
        writer.write(rendered[name])
    writer.release()
    print(f"{args.out}: {len(names)} frames, {len(rendered)} detected (source {min(wanted)}..{max(wanted)})")


if __name__ == "__main__":
    main()
