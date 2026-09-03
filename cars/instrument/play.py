# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy", "opencv-python-headless", "tqdm"]
# ///
"""Play the highway: composite vehicle clips over the clean plate with a
number of cars per lane. Cars enter under the bridge and roll down; when
a lane holds more than wanted, the farthest ones fade out.

  uv run instrument/play.py --lanes 2,5,0,1 --seconds 20 out.mp4
  uv run instrument/play.py --demo out.mp4
"""
import argparse, json, random, subprocess, sys
from pathlib import Path
import cv2, numpy as np
from tqdm import tqdm

FPS = 25
FADE = 20


class Clip:
    def __init__(self, folder):
        meta = json.loads((folder / "meta.json").read_text())
        self.lane = meta["lane"] - 1
        self.boxes = np.array(meta["boxes"])
        self.frames = [cv2.imread(str(folder / f"{i:03d}.png"), cv2.IMREAD_UNCHANGED) for i in range(len(self.boxes))]
        self.n = len(self.boxes)


class Library:
    def __init__(self, root):
        self.by_lane = {k: [] for k in range(4)}
        for d in sorted(root.glob("lane*/*/meta.json")):
            c = Clip(d.parent)
            self.by_lane[c.lane].append(c)
        counts = {k + 1: len(v) for k, v in self.by_lane.items()}
        print("clips per lane:", counts)


class Car:
    def __init__(self, clip, t0):
        self.clip, self.t0 = clip, t0
        self.fade = None

    def box_at(self, t):
        i = t - self.t0
        return self.clip.boxes[i] if 0 <= i < self.clip.n else None

    def alive(self, t):
        return t - self.t0 < self.clip.n


def boxes_touch(a, b, margin):
    ax, ay, aw, ah = a; bx, by, bw, bh = b
    return not (ax + aw + margin < bx or bx + bw + margin < ax or ay + ah + margin < by or by + bh + margin < ay)


def can_spawn(clip, t0, cars, margin):
    """No overlap with any existing car in the same lane over the clip's whole life."""
    others = [c for c in cars if c.clip.lane == clip.lane]
    for i in range(clip.n):
        t = t0 + i
        for c in others:
            b = c.box_at(t)
            if b is not None and boxes_touch(clip.boxes[i], b, margin):
                return False
    return True


def composite(plate, cars, t):
    out = plate.copy()
    # far cars first, so near cars draw over them
    active = [(c.box_at(t), c) for c in cars]
    active = [(b, c) for b, c in active if b is not None]
    active.sort(key=lambda bc: bc[0][1] + bc[0][3])
    for (x, y, w, h), c in active:
        rgba = c.clip.frames[t - c.t0]
        a = rgba[:, :, 3:4].astype(np.float32) / 255.0
        if c.fade is not None:
            a *= max(0.0, 1 - (t - c.fade) / FADE)
        roi = out[y:y + h, x:x + w]
        roi[:] = (rgba[:, :, :3] * a + roi * (1 - a)).astype(np.uint8)
    return out


def demo_fill(t_sec):
    """A 40 s sweep: each lane fills up in turn, then everything at once, then empty."""
    d = np.zeros(4)
    if t_sec < 20:
        k = int(t_sec // 5); d[k] = min(1.0, (t_sec % 5) / 4)
        for j in range(k): d[j] = 0.2
    elif t_sec < 30:
        d[:] = min(1.0, (t_sec - 20) / 4)
    else:
        d[:] = max(0.0, 1 - (t_sec - 30) / 4)
    return d


def measure_capacity(lane, margin):
    """How many cars fit at once: pack the lane's clips nose to tail for 30 s."""
    if not lane:
        return 0
    sim, best = [], 0
    for t in range(750):
        clip = lane[t % len(lane)]
        if can_spawn(clip, t, sim, margin):
            sim.append(Car(clip, t))
        sim = [c for c in sim if c.alive(t)]
        best = max(best, len(sim))
    return max(1, best)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out", type=Path)
    ap.add_argument("--clips", type=Path, default=Path("output-clips"))
    ap.add_argument("--plate", type=Path, default=Path("output-plate-stab/iter3.png"))
    ap.add_argument("--lanes", type=str, default=None, help="fill per lane 0..1, e.g. 0.2,1,0,0.5 (1 = as many cars as fit)")
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--seconds", type=float, default=20)
    ap.add_argument("--margin", type=int, default=24)
    ap.add_argument("--seed", type=int, default=1)
    args = ap.parse_args()
    random.seed(args.seed)
    plate = cv2.imread(str(args.plate)); h, w = plate.shape[:2]
    lib = Library(args.clips)
    fill = np.array([float(v) for v in args.lanes.split(",")]) if args.lanes else None
    capacity = [measure_capacity(lib.by_lane[k], args.margin) for k in range(4)]
    print("capacity per lane:", capacity)
    last_clip = [None] * 4
    seconds = 40 if args.demo else args.seconds
    n = int(seconds * FPS)
    ff = subprocess.Popen(["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{w}x{h}", "-r", str(FPS),
                           "-i", "-", "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p", str(args.out)], stdin=subprocess.PIPE)
    cars = []
    for t in tqdm(range(n), desc="render"):
        wanted = [round(f * c) for f, c in zip(demo_fill(t / FPS) if args.demo else fill, capacity)]
        for k in range(4):
            lane = lib.by_lane[k]
            if not lane: continue
            mine = [c for c in cars if c.clip.lane == k and c.fade is None]
            if len(mine) < wanted[k]:
                if random.random() < 0.35:   # jitter, so cars do not enter in lock-step
                    clip = random.choice(lane)
                    if len(lane) > 1 and clip is last_clip[k]:
                        clip = lane[(lane.index(clip) + 1) % len(lane)]
                    if can_spawn(clip, t, cars, args.margin):
                        cars.append(Car(clip, t)); last_clip[k] = clip
            elif len(mine) > wanted[k]:
                far = min(mine, key=lambda c: c.box_at(t)[1] + c.box_at(t)[3])
                far.fade = t
        cars = [c for c in cars if c.alive(t) and (c.fade is None or t - c.fade < FADE)]
        frame = composite(plate, cars, t)
        if args.demo:
            for k in range(4):
                cv2.rectangle(frame, (20 + k * 60, 20), (60 + k * 60, 40), (40, 40, 40), -1)
                cv2.rectangle(frame, (20 + k * 60, 20), (20 + k * 60 + int(40 * wanted[k] / max(1, capacity[k])), 40), (40, 160, 255), -1)
        ff.stdin.write(frame.tobytes())
    ff.stdin.close(); ff.wait()
    print("wrote", args.out)


if __name__ == "__main__":
    main()
