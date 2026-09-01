"""Render pose + face conditioning images the way Figment draws them.

Reproduces the `train.fgmt` network: Detect Pose (points r=2, lines w=2) and
Detect Faces (contours w=1), white on black, composited with lighten, then
stacked next to the source frame: left = source (target), right = conditioning.

Usage:
  uv run scripts/render_conditioning.py VIDEO_OR_DIR OUT_DIR [options]
"""

import argparse
import json
import sys
from pathlib import Path

import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks.python import BaseOptions
from mediapipe.tasks.python.vision import (
    FaceLandmarker,
    FaceLandmarkerOptions,
    PoseLandmarker,
    PoseLandmarkerOptions,
    RunningMode,
)
from mediapipe.tasks.python.vision.face_landmarker import FaceLandmarksConnections
from mediapipe.tasks.python.vision.pose_landmarker import PoseLandmarksConnections
from tqdm import tqdm

MODEL_DIR = Path(__file__).resolve().parent.parent / "media" / "models"
WHITE = (255, 255, 255)

POSE_CONNECTIONS = [(c.start, c.end) for c in PoseLandmarksConnections.POSE_LANDMARKS]
FACE_CONTOURS = [(c.start, c.end) for c in FaceLandmarksConnections.FACE_LANDMARKS_CONTOURS]


def make_detectors(pose_model, num_poses, num_faces, confidence):
    pose = PoseLandmarker.create_from_options(
        PoseLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=str(MODEL_DIR / f"pose_landmarker_{pose_model}.task")),
            running_mode=RunningMode.IMAGE,
            num_poses=num_poses,
        )
    )
    face = FaceLandmarker.create_from_options(
        FaceLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=str(MODEL_DIR / "face_landmarker.task")),
            running_mode=RunningMode.IMAGE,
            num_faces=num_faces,
            min_face_detection_confidence=confidence,
            min_face_presence_confidence=confidence,
            min_tracking_confidence=confidence,
        )
    )
    return pose, face


def draw_pose(canvas, landmarks_list, point_radius=2, line_width=2):
    """Match mediapipe DrawingUtils: circle of `radius` filled, plus a stroke of
    lineWidth 4 (the DrawingUtils default) in the same color."""
    h, w = canvas.shape[:2]
    for landmarks in landmarks_list:
        pts = [(int(round(l.x * w)), int(round(l.y * h))) for l in landmarks]
        for a, b in POSE_CONNECTIONS:
            cv2.line(canvas, pts[a], pts[b], WHITE, line_width, cv2.LINE_AA)
        r = int(round(point_radius + 4 / 2))
        for p in pts:
            cv2.circle(canvas, p, r, WHITE, -1, cv2.LINE_AA)


def draw_face(canvas, landmarks_list, line_width=1):
    h, w = canvas.shape[:2]
    for landmarks in landmarks_list:
        pts = [(int(round(l.x * w)), int(round(l.y * h))) for l in landmarks]
        for a, b in FACE_CONTOURS:
            cv2.line(canvas, pts[a], pts[b], WHITE, line_width, cv2.LINE_AA)


def render(frame_rgb, pose, face):
    """Return (conditioning_rgb, n_poses, n_faces)."""
    h, w = frame_rgb.shape[:2]
    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(frame_rgb))
    pose_res = pose.detect(mp_image)
    face_res = face.detect(mp_image)
    pose_canvas = np.zeros((h, w, 3), np.uint8)
    face_canvas = np.zeros((h, w, 3), np.uint8)
    draw_pose(pose_canvas, pose_res.pose_landmarks)
    draw_face(face_canvas, face_res.face_landmarks)
    return np.maximum(pose_canvas, face_canvas), len(pose_res.pose_landmarks), len(face_res.face_landmarks)


def iter_frames(source: Path, step: int):
    if source.is_dir():
        files = sorted(p for p in source.iterdir() if p.suffix.lower() in {".jpg", ".jpeg", ".png"})
        for i, f in enumerate(files[::step]):
            yield f.stem, cv2.cvtColor(cv2.imread(str(f)), cv2.COLOR_BGR2RGB)
        return
    cap = cv2.VideoCapture(str(source))
    i = 0
    while True:
        ok, bgr = cap.read()
        if not ok:
            break
        if i % step == 0:
            yield f"{i:05d}", cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        i += 1
    cap.release()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source", type=Path, help="video file or directory of frames")
    ap.add_argument("out", type=Path, help="output directory")
    ap.add_argument("--pose-model", default="heavy", choices=["lite", "full", "heavy"])
    ap.add_argument("--num-poses", type=int, default=2)
    ap.add_argument("--num-faces", type=int, default=2)
    ap.add_argument("--confidence", type=float, default=0.5)
    ap.add_argument("--step", type=int, default=1, help="use every Nth frame")
    ap.add_argument("--size", type=str, default=None, help="resize each half to WxH, e.g. 512x896")
    ap.add_argument("--prefix", default="", help="prefix for output file names")
    ap.add_argument("--overlay", action="store_true", help="also write conditioning drawn over the source")
    ap.add_argument("--skip-empty", action="store_true", help="skip frames with no pose")
    args = ap.parse_args()

    pairs_dir = args.out / "pairs"
    pairs_dir.mkdir(parents=True, exist_ok=True)
    if args.overlay:
        (args.out / "overlay").mkdir(exist_ok=True)
    size = tuple(int(v) for v in args.size.split("x")) if args.size else None

    pose, face = make_detectors(args.pose_model, args.num_poses, args.num_faces, args.confidence)
    stats = {"frames": 0, "with_pose": 0, "with_face": 0, "with_both": 0, "written": 0}

    for name, rgb in tqdm(iter_frames(args.source, args.step), desc=args.source.name):
        cond, n_pose, n_face = render(rgb, pose, face)
        stats["frames"] += 1
        stats["with_pose"] += n_pose > 0
        stats["with_face"] += n_face > 0
        stats["with_both"] += n_pose > 0 and n_face > 0
        if args.skip_empty and n_pose == 0:
            continue
        target, inp = rgb, cond
        if size:
            target = cv2.resize(target, size, interpolation=cv2.INTER_AREA)
            inp = cv2.resize(inp, size, interpolation=cv2.INTER_AREA)
        pair = np.concatenate([target, inp], axis=1)
        out_name = f"{args.prefix}{name}.jpg"
        cv2.imwrite(str(pairs_dir / out_name), cv2.cvtColor(pair, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 95])
        stats["written"] += 1
        if args.overlay:
            ov = np.maximum(rgb, cond)
            cv2.imwrite(str(args.out / "overlay" / out_name), cv2.cvtColor(ov, cv2.COLOR_RGB2BGR))

    (args.out / f"{args.prefix or 'stats'}.json").write_text(json.dumps(stats, indent=2))
    print(json.dumps(stats), file=sys.stderr)


if __name__ == "__main__":
    main()
