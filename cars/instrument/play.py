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

sys.path.insert(0, str(Path(__file__).parent))
from lanes import lane_center_x

FPS = 25
MIN_OWN = 8
FADE = 6   # short fades: built for an equalizer


class Clip:
    def __init__(self, folder):
        meta = json.loads((folder / "meta.json").read_text())
        self.lane = meta["lane"] - 1
        self.cars = meta.get("cars", 1)
        self.boxes = np.array(meta["boxes"])
        self.frames = [cv2.imread(str(folder / f"{i:03d}.png"), cv2.IMREAD_UNCHANGED) for i in range(len(self.boxes))]
        self.n = len(self.boxes)

    def shifted(self, k):
        """This clip moved into lane k: same rows, x shifted to that lane's centre."""
        c = Clip.__new__(Clip)
        c.lane, c.frames, c.n, c.cars = k, self.frames, self.n, self.cars
        yb = self.boxes[:, 1] + self.boxes[:, 3]
        dx = np.array([lane_center_x(k, y) - lane_center_x(self.lane, y) for y in yb])
        c.boxes = self.boxes.copy(); c.boxes[:, 0] = np.round(self.boxes[:, 0] + dx).astype(int)
        return c


class Train:
    """A train passage: the railway strip as video, drawn through a mask."""
    def __init__(self, folder, meta, mask):
        self.meta = meta
        cap = cv2.VideoCapture(str(folder / meta["file"]))
        self.frames = []
        while True:
            ok, f = cap.read()
            if not ok: break
            self.frames.append(f)
        self.mask = mask[..., None]
        self.n = len(self.frames)

    def draw(self, out, i):
        m = self.meta; roi = out[m["y"]:m["y"] + m["h"], m["x"]:m["x"] + m["w"]]
        a = self.mask
        roi[:] = (self.frames[i] * a + roi * (1 - a)).astype(np.uint8)


def load_trains(folder):
    if not folder or not (folder / "trains.json").exists():
        return []
    mask = cv2.imread(str(folder / "mask.png"), 0).astype(np.float32) / 255
    return [Train(folder, m, mask) for m in json.loads((folder / "trains.json").read_text())]


class Library:
    def __init__(self, roots, borrow=True):
        self.own = {k: [] for k in range(4)}
        for d in sorted(m for root in roots for m in root.glob("lane*/*/meta.json")):
            c = Clip(d.parent)
            self.own[c.lane].append(c)
        print("own clips per lane:", {k + 1: len(v) for k, v in self.own.items()})
        self.by_lane = {k: list(v) for k, v in self.own.items()}
        if borrow:
            # lanes with few clips of their own borrow lane 1's cars, slid sideways
            for k in range(4):
                if len(self.own[k]) < MIN_OWN:
                    for j in range(4):
                        if j != k:
                            self.by_lane[k] += [c.shifted(k) for c in self.own[j]]
        print("clips per lane:", {k + 1: len(v) for k, v in self.by_lane.items()})


class Car:
    """A car has a fractional playhead into its clip, moved by its lane's tempo."""
    def __init__(self, clip, pos, fade_in=None):
        self.clip, self.pos = clip, float(pos)
        self.fade = None
        self.fade_in = fade_in

    def index(self):
        i = int(round(self.pos))
        return i if 0 <= i < self.clip.n else -1

    def box(self):
        i = self.index()
        return self.clip.boxes[i] if i >= 0 else None

    def alive(self):
        return 0 <= self.pos < self.clip.n


def core(b):
    """Boxes hold shadow and padding too; cars may sit closer than the boxes."""
    x, y, w, h = b
    return x + 0.2 * w, y + 0.2 * h, 0.6 * w, 0.6 * h


def boxes_touch(a, b, margin):
    ax, ay, aw, ah = core(a); bx, by, bw, bh = core(b)
    return not (ax + aw + margin < bx or bx + bw + margin < ax or ay + ah + margin < by or by + bh + margin < ay)


def can_spawn(clip, start, tempo, cars, margin):
    """Would a car starting at `start`, moving at `tempo`, touch any car of the
    same lane for the rest of its run? The others move at the same tempo."""
    others = [c for c in cars if c.clip.lane == clip.lane]
    if not others:
        return True
    step = 1.0 if abs(tempo) < 0.05 else tempo
    for s in range(2000):
        i = int(round(start + s * step))
        if not 0 <= i < clip.n:
            break
        for c in others:
            j = int(round(c.pos + s * step))
            if 0 <= j < c.clip.n and boxes_touch(clip.boxes[i], c.clip.boxes[j], margin):
                return False
    return True


def find_start(clip, tempo, cars, margin, mid_road):
    """Where to start: the entrance (bridge, or bottom edge when driving
    backwards) if it fits, else a random spot along the road."""
    entrance = clip.n - 1 if tempo < 0 else 0
    if can_spawn(clip, entrance, tempo, cars, margin):
        return entrance
    if not mid_road:
        return -1
    for _ in range(12):
        j = random.randint(10, max(10, clip.n - 50))
        if can_spawn(clip, j, tempo, cars, margin):
            return j
    return -1


def car_bottom(c):
    b = c.box()
    return 0 if b is None else int(b[1] + b[3])


def composite(plate, cars, t):
    out = plate.copy()
    # far cars first, so near cars draw over them
    active = [(c.box(), c) for c in cars]
    active = [(b, c) for b, c in active if b is not None]
    active.sort(key=lambda bc: bc[0][1] + bc[0][3])
    for (x, y, w, h), c in active:
        rgba = c.clip.frames[c.index()]
        a = rgba[:, :, 3:4].astype(np.float32) / 255.0
        if c.fade is not None:
            a *= max(0.0, 1 - (t - c.fade) / FADE)
        if c.fade_in is not None:
            a *= min(1.0, (t - c.fade_in + 1) / FADE)
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
        j = find_start(clip, 1.0, sim, margin, True)
        if j >= 0:
            sim.append(Car(clip, j))
        for c in sim:
            c.pos += 1
        sim = [c for c in sim if c.alive()]
        best = max(best, sum(c.clip.cars for c in sim))
    return max(1, best)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out", type=Path)
    ap.add_argument("--clips", type=Path, nargs="+", default=[Path("output-clips")])
    ap.add_argument("--plate", type=Path, default=Path("output-plate-stab/iter3.png"))
    ap.add_argument("--lanes", type=str, default=None, help="level per lane 0..1, e.g. 0.2,1,0,0.5")
    ap.add_argument("--tempo", type=str, default="1,1,1,1", help="speed per lane, e.g. 1,0.5,-1,2 (negative: backwards)")
    ap.add_argument("--train-tempo", type=float, default=1.0)
    ap.add_argument("--global-tempo", type=float, default=1.0, help="multiplies every lane's tempo, train included")
    ap.add_argument("--max-loops", type=int, default=8, help="loops of carriages at train length just under 1")
    ap.add_argument("--mode", choices=["roll", "count"], default="count",
                    help="roll: a lane value is a note, cars stream in at the bridge while it is held; count: fill fraction with quick fades")
    ap.add_argument("--sparse-gap", type=int, default=300, help="px between cars at a whisper in roll mode; 0 at full level")
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--seconds", type=float, default=20)
    ap.add_argument("--margin", type=int, default=24)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--no-borrow", action="store_true", help="do not fill thin lanes with lane-1 cars")
    ap.add_argument("--trains", type=Path, default=Path("output-trains"))
    ap.add_argument("--train", type=float, default=1.0, help="lane 0, train length: 0 none, small = one carriage, 1 = endless")
    args = ap.parse_args()
    random.seed(args.seed)
    plate = cv2.imread(str(args.plate)); h, w = plate.shape[:2]
    lib = Library(args.clips, borrow=not args.no_borrow)
    trains = load_trains(args.trains)
    train, train_next = None, 0   # [Train, playhead, loops done]
    tempos = [float(v) * args.global_tempo for v in args.tempo.split(",")]
    args.train_tempo *= args.global_tempo
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
        levels = demo_fill(t / FPS) if args.demo else fill
        wanted = [round(f * c) for f, c in zip(levels, capacity)]
        for k in range(4):
            tp = tempos[k]
            if args.mode == "roll":
                lane = lib.by_lane[k]
                if not lane or levels[k] <= 0.02: continue
                margin = int(args.margin + (1 - levels[k]) * args.sparse_gap)
                big = [c for c in lane if c.cars > 1]
                clip = random.choice(big) if levels[k] > 0.7 and big and random.random() < 0.5 else random.choice(lane)
                if len(lane) > 1 and clip is last_clip[k]:
                    clip = lane[(lane.index(clip) + 1) % len(lane)]
                entrance = clip.n - 1 if tp < 0 else 0
                if can_spawn(clip, entrance, tp, cars, margin):
                    cars.append(Car(clip, entrance)); last_clip[k] = clip
                continue
            lane = lib.by_lane[k]
            if not lane: continue
            mine = [c for c in cars if c.clip.lane == k and c.fade is None]
            have = sum(c.clip.cars for c in mine)
            if have < wanted[k]:
                for tries in range(3):   # fill the deficit now
                    if have + tries >= wanted[k]: break
                    clip = random.choice(lane)
                    if len(lane) > 1 and clip is last_clip[k]:
                        clip = lane[(lane.index(clip) + 1) % len(lane)]
                    j = find_start(clip, tp, cars, args.margin, True)
                    if j < 0: break
                    entrance = clip.n - 1 if tp < 0 else 0
                    cars.append(Car(clip, j, fade_in=t if j != entrance else None)); last_clip[k] = clip
            if have > wanted[k]:
                far = min(mine, key=car_bottom)
                far.fade = t
        for c in cars:
            c.pos += tempos[c.clip.lane]
        cars = [c for c in cars if c.alive() and (c.fade is None or t - c.fade < FADE)]
        frame = composite(plate, cars, t)
        length = args.train if not args.demo else (1.0 if 5 < t / FPS < 35 else 0.0)
        # lane 0 is the train's length: loops of carriages, endless at 1
        loops_allowed = float("inf") if length >= 0.99 else round(length * args.max_loops)
        if train and train[1] >= train[0].n:
            train, train_next = None, t
        if not train and length > 0.01 and trains and t >= train_next:
            train = [random.choice(trains), 0.0, 0]
        if train:
            tr, pos, loops = train
            i = int(pos)
            lo = tr.meta.get("loop_out")
            if lo and i >= lo and loops < loops_allowed and i - lo < FPS:
                # loop, or step back onto the loop at the same offset when the tail has only just begun
                pos = float(tr.meta["loop_in"] + (i - lo)); i = int(pos); train[2] += 1
            tr.draw(frame, min(i, tr.n - 1)); train[1] = pos + max(0.0, args.train_tempo)
        if args.demo:
            for k in range(4):
                cv2.rectangle(frame, (20 + k * 60, 20), (60 + k * 60, 40), (40, 40, 40), -1)
                cv2.rectangle(frame, (20 + k * 60, 20), (20 + k * 60 + int(40 * wanted[k] / max(1, capacity[k])), 40), (40, 160, 255), -1)
        ff.stdin.write(frame.tobytes())
    ff.stdin.close(); ff.wait()
    print("wrote", args.out)


if __name__ == "__main__":
    main()
