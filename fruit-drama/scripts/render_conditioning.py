"""Render pose + face conditioning images the way Figment draws them.

Reproduces the `train.fgmt` network: Detect Pose (points r=2, lines w=2) and
Detect Faces (contours w=1), white on a background color, composited with
lighten, then stacked next to the source frame: left = source (target),
right = conditioning.

The background color is the scene code. One color per scene lets one model
serve several scenes; at inference set the same color on Figment's Detect Pose
and Detect Faces `background` parameter.

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


def hex_to_rgb(color):
    color = color.lstrip("#")
    return tuple(int(color[i:i + 2], 16) for i in (0, 2, 4))


def make_detectors(pose_model="heavy", num_poses=1, num_faces=1, confidence=0.5):
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


def detect(frame_rgb, pose, face):
    """Return (pose_landmarks, face_landmarks) as lists of [(x, y), ...] in 0..1."""
    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(frame_rgb))
    poses = [[(l.x, l.y) for l in lm] for lm in pose.detect(mp_image).pose_landmarks]
    faces = [[(l.x, l.y) for l in lm] for lm in face.detect(mp_image).face_landmarks]
    return poses, faces


def draw_pose(canvas, poses, point_radius=2, line_width=2):
    """Match mediapipe DrawingUtils: circle of `radius` filled, plus a stroke of
    lineWidth 4 (the DrawingUtils default) in the same color."""
    h, w = canvas.shape[:2]
    r = int(round(point_radius + 4 / 2))
    for landmarks in poses:
        pts = [(int(round(x * w)), int(round(y * h))) for x, y in landmarks]
        for a, b in POSE_CONNECTIONS:
            cv2.line(canvas, pts[a], pts[b], WHITE, line_width, cv2.LINE_AA)
        for p in pts:
            cv2.circle(canvas, p, r, WHITE, -1, cv2.LINE_AA)


def draw_face(canvas, faces, line_width=1):
    h, w = canvas.shape[:2]
    for landmarks in faces:
        pts = [(int(round(x * w)), int(round(y * h))) for x, y in landmarks]
        for a, b in FACE_CONTOURS:
            cv2.line(canvas, pts[a], pts[b], WHITE, line_width, cv2.LINE_AA)


def render_landmarks(poses, faces, width, height, background=(0, 0, 0)):
    """Conditioning image (RGB uint8) from landmarks. Lighten composite of the
    pose canvas and the face canvas, both on the same background."""
    pose_canvas = np.zeros((height, width, 3), np.uint8)
    pose_canvas[:] = background
    face_canvas = pose_canvas.copy()
    draw_pose(pose_canvas, poses)
    draw_face(face_canvas, faces)
    return np.maximum(pose_canvas, face_canvas)


def crop_to_aspect(rgb, width, height):
    """Center-crop the frame to width:height so a later resize does not distort."""
    h, w = rgb.shape[:2]
    target = width / height
    if w / h > target:
        nw = int(round(h * target)); x0 = (w - nw) // 2
        return rgb[:, x0:x0 + nw]
    nh = int(round(w / target)); y0 = (h - nh) // 2
    return rgb[y0:y0 + nh]


def iter_frames(source: Path, step: int):
    if source.is_dir():
        files = sorted(p for p in source.iterdir() if p.suffix.lower() in {".jpg", ".jpeg", ".png"})
        for f in files[::step]:
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


def process(source, out, *, size=None, background="#000000", prefix="", step=1, skip_empty=False,
            overlay=False, pose_model="heavy", num_poses=1, num_faces=1, confidence=0.5, detectors=None):
    """Render pairs for one video or frame folder. Returns the stats dict.

    Writes `out/pairs/<prefix><frame>.jpg`, `out/<prefix>frames.csv`
    (poses,faces per frame), `out/<prefix>landmarks.jsonl` (normalized
    landmarks per frame) and `out/<prefix>stats.json`.
    """
    source, out = Path(source), Path(out)
    pairs_dir = out / "pairs"
    pairs_dir.mkdir(parents=True, exist_ok=True)
    if overlay:
        (out / "overlay").mkdir(exist_ok=True)
    bg = hex_to_rgb(background)
    pose, face = detectors or make_detectors(pose_model, num_poses, num_faces, confidence)
    stats = {"source": str(source), "background": background, "frames": 0, "with_pose": 0, "with_face": 0,
             "with_both": 0, "written": 0}

    with open(out / f"{prefix}frames.csv", "w") as csv, open(out / f"{prefix}landmarks.jsonl", "w") as lmf:
        csv.write("name,poses,faces\n")
        for name, rgb in tqdm(iter_frames(source, step), desc=f"{prefix or source.name}"):
            if size:
                rgb = crop_to_aspect(rgb, *size)
                rgb = cv2.resize(rgb, size, interpolation=cv2.INTER_AREA)
            h, w = rgb.shape[:2]
            poses, faces = detect(rgb, pose, face)
            stats["frames"] += 1
            stats["with_pose"] += bool(poses)
            stats["with_face"] += bool(faces)
            stats["with_both"] += bool(poses and faces)
            csv.write(f"{name},{len(poses)},{len(faces)}\n")
            lmf.write(json.dumps({"name": name, "poses": poses, "faces": faces}) + "\n")
            if skip_empty and not poses:
                continue
            cond = render_landmarks(poses, faces, w, h, bg)
            pair = np.concatenate([rgb, cond], axis=1)
            out_name = f"{prefix}{name}.jpg"
            cv2.imwrite(str(pairs_dir / out_name), cv2.cvtColor(pair, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 95])
            stats["written"] += 1
            if overlay:
                cv2.imwrite(str(out / "overlay" / out_name), cv2.cvtColor(np.maximum(rgb, cond), cv2.COLOR_RGB2BGR))

    (out / f"{prefix}stats.json").write_text(json.dumps(stats, indent=2))
    return stats


def process_with_landmarks(source, out, landmarks_file, *, size=None, background="#000000", prefix=""):
    """Pair each frame of `source` with the landmarks row of the same index.
    For clips generated from a control video: the skeleton is known exactly."""
    source, out = Path(source), Path(out)
    pairs_dir = out / "pairs"
    pairs_dir.mkdir(parents=True, exist_ok=True)
    bg = hex_to_rgb(background)
    rows = [json.loads(l) for l in Path(landmarks_file).read_text().splitlines()]
    stats = {"source": str(source), "background": background, "frames": 0, "written": 0, "landmarks": str(landmarks_file)}
    for (name, rgb), row in zip(iter_frames(source, 1), rows):
        if size:
            rgb = crop_to_aspect(rgb, *size)
            rgb = cv2.resize(rgb, size, interpolation=cv2.INTER_AREA)
        h, w = rgb.shape[:2]
        cond = render_landmarks(row["poses"], row["faces"], w, h, bg)
        pair = np.concatenate([rgb, cond], axis=1)
        cv2.imwrite(str(pairs_dir / f"{prefix}{name}.jpg"), cv2.cvtColor(pair, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 95])
        stats["frames"] += 1
        stats["written"] += 1
    (out / f"{prefix}stats.json").write_text(json.dumps(stats, indent=2))
    return stats


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source", type=Path, help="video file or directory of frames")
    ap.add_argument("out", type=Path, help="output directory")
    ap.add_argument("--pose-model", default="heavy", choices=["lite", "full", "heavy"])
    ap.add_argument("--num-poses", type=int, default=1)
    ap.add_argument("--num-faces", type=int, default=1)
    ap.add_argument("--confidence", type=float, default=0.5)
    ap.add_argument("--step", type=int, default=1, help="use every Nth frame")
    ap.add_argument("--size", type=str, default=None, help="center-crop to the aspect of WxH, then resize each half to WxH, e.g. 512x768")
    ap.add_argument("--background", default="#000000", help="scene color for the conditioning background, e.g. '#400d0d'")
    ap.add_argument("--prefix", default="", help="prefix for output file names")
    ap.add_argument("--overlay", action="store_true", help="also write conditioning drawn over the source")
    ap.add_argument("--skip-empty", action="store_true", help="skip frames with no pose")
    args = ap.parse_args()
    size = tuple(int(v) for v in args.size.split("x")) if args.size else None
    stats = process(args.source, args.out, size=size, background=args.background, prefix=args.prefix, step=args.step,
                    skip_empty=args.skip_empty, overlay=args.overlay, pose_model=args.pose_model,
                    num_poses=args.num_poses, num_faces=args.num_faces, confidence=args.confidence)
    print(json.dumps(stats), file=sys.stderr)


if __name__ == "__main__":
    main()
