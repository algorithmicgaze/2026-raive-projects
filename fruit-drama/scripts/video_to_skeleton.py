# /// script
# requires-python = ">=3.12,<3.13"
# dependencies = [
#     "mediapipe>=0.10.21,<1",
#     "opencv-python-headless",
#     "numpy",
#     "tqdm",
# ]
# ///
"""Render a video as MediaPipe skeleton frames: white 2px anti-aliased lines on black.

Detects one pose per frame on the full source frame (center-cropped to a
square). Writes, next to the video, in <video>_skeleton/:
  frames/<frame>.png          skeleton, --size square (default 1024)
  landmarks.jsonl             one line per frame: normalized x, y, z, visibility
                              for the 33 pose landmarks (empty list = no pose)
and encodes <video>_skeleton.mp4 at the source frame rate. Frames without
a pose are blank black so the output stays in sync with the source.

mediapipe is pinned below 1.0: the 1.x graph aborts on macOS with
"Check failed: service_ Service is unavailable".

  uv run scripts/video_to_skeleton.py media/myrthe-ai-control.mp4
"""

import argparse
import json
import subprocess
import urllib.request
from pathlib import Path

import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks.python import BaseOptions
from mediapipe.tasks.python.vision import PoseLandmarker, PoseLandmarkerOptions, RunningMode
from mediapipe.tasks.python.vision.pose_landmarker import PoseLandmarksConnections
from tqdm import tqdm

MODEL_DIR = Path(__file__).resolve().parent.parent / "media" / "models"
MODEL_URL = "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_{name}/float16/latest/pose_landmarker_{name}.task"
CONNECTIONS = [(c.start, c.end) for c in PoseLandmarksConnections.POSE_LANDMARKS]
WHITE = (255, 255, 255)


def model_path(name):
    path = MODEL_DIR / f"pose_landmarker_{name}.task"
    if not path.exists():
        MODEL_DIR.mkdir(parents=True, exist_ok=True)
        print("downloading", path.name)
        urllib.request.urlretrieve(MODEL_URL.format(name=name), path)
    return path


def crop_square(rgb):
    h, w = rgb.shape[:2]
    s = min(h, w)
    y0, x0 = (h - s) // 2, (w - s) // 2
    return rgb[y0:y0 + s, x0:x0 + s]


def render(landmarks, size, line_width):
    canvas = np.zeros((size, size, 3), np.uint8)
    if landmarks:
        pts = [(int(round(x * size)), int(round(y * size))) for x, y, _, _ in landmarks]
        for a, b in CONNECTIONS:
            cv2.line(canvas, pts[a], pts[b], WHITE, line_width, cv2.LINE_AA)
    return canvas


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video", type=Path)
    ap.add_argument("--out", type=Path, help="output directory (default: <video>_skeleton next to the video)")
    ap.add_argument("--size", type=int, default=1024)
    ap.add_argument("--line-width", type=int, default=2)
    ap.add_argument("--pose-model", default="heavy", choices=["lite", "full", "heavy"])
    args = ap.parse_args()

    out = args.out or args.video.with_name(args.video.stem + "_skeleton")
    frames_dir = out / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)

    cap = cv2.VideoCapture(str(args.video))
    fps = cap.get(cv2.CAP_PROP_FPS)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    landmarker = PoseLandmarker.create_from_options(
        PoseLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=str(model_path(args.pose_model))),
            running_mode=RunningMode.VIDEO,
            num_poses=1,
        )
    )

    detected = 0
    with open(out / "landmarks.jsonl", "w") as jsonl:
        for i in tqdm(range(total), desc=args.video.name, mininterval=5):
            ok, bgr = cap.read()
            if not ok:
                break
            rgb = crop_square(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
            image = mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(rgb))
            result = landmarker.detect_for_video(image, int(i * 1000 / fps))
            landmarks = [(round(l.x, 5), round(l.y, 5), round(l.z, 5), round(l.visibility, 3))
                         for l in result.pose_landmarks[0]] if result.pose_landmarks else []
            detected += bool(landmarks)
            jsonl.write(json.dumps({"frame": i, "width": rgb.shape[1], "height": rgb.shape[0],
                                    "landmarks": landmarks}) + "\n")
            cv2.imwrite(str(frames_dir / f"{i:05d}.png"), render(landmarks, args.size, args.line_width))
    cap.release()
    landmarker.close()
    print(f"pose in {detected}/{total} frames")

    mp4 = out.with_suffix(".mp4")
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-framerate", f"{fps:g}", "-i", str(frames_dir / "%05d.png"),
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", str(mp4)],
        check=True,
    )
    print(mp4)


if __name__ == "__main__":
    main()
