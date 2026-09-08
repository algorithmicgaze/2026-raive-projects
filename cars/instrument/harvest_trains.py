# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy", "opencv-python-headless", "tqdm"]
# ///
"""Cut train passages: the railway strip of aligned 25 fps frames as a
short video, plus a feathered mask of the strip and its position. The
strip without a train equals the plate, so no per-frame alpha is needed.

  uv run instrument/harvest_trains.py 159 11 336 13 --out output-trains
"""
import argparse, json, shutil, subprocess
from pathlib import Path
import cv2, numpy as np

RAIL_ROI = np.array([(0, 470), (470, 400), (640, 425), (600, 520), (330, 1080), (0, 1080)], dtype=np.int32)
X0, Y0, X1, Y1 = 0, 390, 660, 1080

ap = argparse.ArgumentParser()
ap.add_argument("passages", type=int, nargs="+", help="start seconds and durations, alternating")
ap.add_argument("--out", type=Path, default=Path("output-trains"))
ap.add_argument("--video", type=Path, default=Path("media/147A3791.MP4"))
ap.add_argument("--margin", type=float, default=2.0)
ap.add_argument("--plate", type=Path, default=Path("output-plate-stab/iter3.png"))
args = ap.parse_args()
args.out.mkdir(parents=True, exist_ok=True)

plate_crop = cv2.imread(str(args.plate))[Y0:Y1, X0:X1]
mask = np.zeros((1080, 1920), np.uint8); cv2.fillPoly(mask, [RAIL_ROI], 255)
mask = cv2.GaussianBlur(mask, (0, 0), 6)[Y0:Y1, X0:X1]
cv2.imwrite(str(args.out / "mask.png"), mask)

def occupancy(crops, plate_crop, mask):
    """Fraction of the strip that differs from the plate, per frame."""
    small = [cv2.resize(c, None, fx=0.25, fy=0.25, interpolation=cv2.INTER_AREA).astype(np.float32) for c in crops]
    m = cv2.resize(mask, None, fx=0.25, fy=0.25) > 128
    p = cv2.resize(plate_crop, None, fx=0.25, fy=0.25, interpolation=cv2.INTER_AREA).astype(np.float32)
    return small, m, np.array([(np.abs(f - p).max(-1)[m] > 40).mean() for f in small])


def find_loop(small, m, occ, min_gap=20):
    """Two frames while the train fills the strip whose carriages line up:
    jump from loop_out back to loop_in and the train never ends; run past
    loop_out and it ends the way it really did. loop_out sits as late as
    possible so the natural ending follows it."""
    full = occ > 0.85 * occ.max()
    idx = np.nonzero(full)[0]
    best, best_pair = None, (idx[0], idx[-1])
    for b in idx[::-1]:
        for a in idx:
            if b - a < min_gap: break
            d = np.abs(small[a] - small[b]).mean(-1)[m].mean()
            score = d + 0.02 * (idx[-1] - b)   # prefer a late loop-out
            if best is None or score < best:
                best, best_pair = score, (int(a), int(b))
    return best_pair


trains = []
for s, d in zip(args.passages[::2], args.passages[1::2]):
    name = f"train_{s:04d}"
    tmp = args.out / "tmp_src"; stab = args.out / "tmp_stab"
    shutil.rmtree(tmp, ignore_errors=True); shutil.rmtree(stab, ignore_errors=True); tmp.mkdir()
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-hwaccel", "videotoolbox", "-ss", str(s - args.margin), "-t", str(d + 2 * args.margin),
                    "-i", str(args.video), "-vf", "scale=1920:1080", "-q:v", "2", str(tmp / "f%05d.jpg")], check=True)
    subprocess.run(["uv", "run", "plate/stabilize.py", str(tmp), str(stab), "--ref", "media/frames-1080/f00001.jpg", "--est-scale", "0.5",
                    "--transforms", str(args.out / f"{name}_transforms.npy")], check=True, stdin=subprocess.DEVNULL, capture_output=True)
    files = sorted(stab.glob("*.jpg"))
    crops = [cv2.imread(str(f))[Y0:Y1, X0:X1] for f in files]
    # keep only the frames where the train is in view (plus a few)
    small, m, occ = occupancy(crops, plate_crop, mask)
    on = np.nonzero(occ > 0.06)[0]
    a, b = max(0, int(on[0]) - 3), min(len(crops), int(on[-1]) + 4)
    crops, small, occ = crops[a:b], small[a:b], occ[a:b]
    loop_in, loop_out = find_loop(small, m, occ)
    # where does the train first show: near the bridge (top right of the
    # strip) means it comes down toward the camera; else it climbs up
    f0 = np.abs(small[3] - cv2.resize(plate_crop, None, fx=0.25, fy=0.25, interpolation=cv2.INTER_AREA).astype(np.float32)).max(-1) > 40
    f0 &= m
    ys, xs = np.nonzero(f0)
    direction = "down" if len(xs) and xs.mean() > 0.45 * f0.shape[1] and ys.mean() < 0.4 * f0.shape[0] else "up"
    # a keyframe at the loop-in frame, so jumping back there is instant
    ff = subprocess.Popen(["ffmpeg", "-nostdin", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{X1 - X0}x{Y1 - Y0}", "-r", "25",
                           "-i", "-", "-c:v", "libx264", "-preset", "slow", "-crf", "23", "-pix_fmt", "yuv420p", "-g", "25",
                           "-force_key_frames", f"{loop_in / 25:.3f}", "-movflags", "+faststart",
                           str(args.out / f"{name}.mp4")], stdin=subprocess.PIPE)
    for c in crops:
        ff.stdin.write(c.tobytes())
    ff.stdin.close(); ff.wait()
    shutil.rmtree(tmp); shutil.rmtree(stab)
    trains.append({"id": name, "file": f"{name}.mp4", "frames": len(crops), "fps": 25, "x": X0, "y": Y0, "w": X1 - X0, "h": Y1 - Y0,
                   "source_s": s, "loop_in": loop_in, "loop_out": loop_out, "direction": direction})
    print(f"  loop {loop_in} -> {loop_out}")
    print(name, len(files), "frames", f"{(args.out / f'{name}.mp4').stat().st_size / 1e6:.1f} MB")
manifest_path = args.out / "trains.json"
old = json.loads(manifest_path.read_text()) if manifest_path.exists() else []
ids = {t["id"] for t in trains}
manifest_path.write_text(json.dumps([t for t in old if t["id"] not in ids] + trains))
