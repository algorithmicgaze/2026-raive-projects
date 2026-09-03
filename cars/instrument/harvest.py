# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy", "opencv-python-headless", "tqdm"]
# ///
"""Cut vehicle clips out of aligned 25 fps frames.

A clip is one vehicle from the moment it appears under the bridge until
it leaves the bottom edge, as a sequence of RGBA crops plus its box in
plate coordinates. Only tracks that stay in one lane and never touch
another vehicle are kept, so the clip holds exactly one car.

Output: <out>/lane<k>/<clip id>/NNN.png and meta.json
"""
import argparse, json, sys
from pathlib import Path
import cv2, numpy as np
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).parent))
from lanes import lane_of, bound_x
from segment import vehicle_labels, soft_alpha, local_plate, ratio_map

FPS = 25


class Track:
    def __init__(self, tid, frame_idx, box, label):
        self.id = tid; self.frames = [frame_idx]; self.boxes = [box]; self.labels = [label]
        self.missed = 0; self.taints = []; self.parent = None

    def isolated(self, min_other=15):
        """Tainted only by another vehicle that lived long enough to be
        real and is not a fragment of this track itself."""
        for why, other, fi in self.taints:
            if len(other.frames) < min_other:
                continue
            if other.parent is self or self.parent is other:
                continue
            return False
        return True

    def taint(self, why, other, fi):
        self.taints.append((why, other, fi))

    def predict(self):
        if len(self.boxes) < 2:
            return self.boxes[-1]
        a, b = self.boxes[-2], self.boxes[-1]
        return b + (b - a) * 0.8

    def add(self, frame_idx, box, label):
        self.frames.append(frame_idx); self.boxes.append(box); self.labels.append(label); self.missed = 0


def box_center(box):
    x, y, w, h = box
    return x + w / 2, y + h / 2


def inside(px, py, box):
    x, y, w, h = box
    return x <= px <= x + w and y <= py <= y + h


def bottom_center(box):
    x, y, w, h = box
    return x + w / 2, y + h


def boxes_touch(a, b, margin):
    ax, ay, aw, ah = a; bx, by, bw, bh = b
    return not (ax + aw + margin < bx or bx + bw + margin < ax or ay + ah + margin < by or by + bh + margin < ay)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("frames", type=Path, nargs="+")
    ap.add_argument("--plate", type=Path, default=Path("output-plate-stab/iter3.png"))
    ap.add_argument("--out", type=Path, default=Path("output-clips"))
    ap.add_argument("--min-len", type=int, default=50)
    ap.add_argument("--debug", type=Path, default=None, help="folder for annotated frames")
    args = ap.parse_args()
    plate = cv2.imread(str(args.plate))
    h, w = plate.shape[:2]
    args.out.mkdir(parents=True, exist_ok=True)
    if args.debug: args.debug.mkdir(parents=True, exist_ok=True)
    kept = 0
    for folder in args.frames:
        files = sorted(folder.glob("*.jpg"))
        local = local_plate(files, plate)
        gain = ratio_map(plate, local)
        cv2.imwrite(str(args.out / f"local_plate_{folder.name}.jpg"), local)
        tracks, done, next_id = [], [], 0
        masks = {}
        for fi, f in enumerate(tqdm(files, desc=folder.name)):
            frame = cv2.imread(str(f))
            lab, stats = vehicle_labels(frame, local)
            comps = [(stats[i, :4].astype(float), i) for i in range(1, len(stats))]
            comps = [c for c in comps if c[0][2] * c[0][3] >= 900]
            # match: closest pairs first, each component to at most one track
            pairs = []
            for ti, t in enumerate(tracks):
                pc = bottom_center(t.predict())
                for j, (box, _) in enumerate(comps):
                    d = np.hypot(*(np.subtract(bottom_center(box), pc)))
                    if d < 80: pairs.append((d, ti, j))
            pairs.sort()
            matched_t, matched_c = {}, {}
            for d, ti, j in pairs:
                if ti in matched_t or j in matched_c: continue
                matched_t[ti] = j; matched_c[j] = ti
            prev_boxes = {ti: t.boxes[-1] for ti, t in enumerate(tracks)}
            for ti, t in enumerate(tracks):
                if ti in matched_t:
                    box, label = comps[matched_t[ti]]
                    t.add(fi, box, label)
                else:
                    t.missed += 1
            # merge: an established track lost its match while its box lies
            # inside a matched track's new box -> that track now holds two cars
            for ti, t in enumerate(tracks):
                if ti in matched_t or len(t.frames) < 5 or t.missed != 1: continue
                cx, cy = box_center(prev_boxes[ti])
                for tj in matched_t:
                    if inside(cx, cy, tracks[tj].boxes[-1]):
                        tracks[tj].taint("merge", t, fi)
            # split: a new component whose centre lies in an established
            # track's previous box came out of that track
            for j, (box, label) in enumerate(comps):
                if j in matched_c: continue
                cx, cy = box_center(box)
                for ti, t in enumerate(tracks):
                    if len(t.frames) >= 5 and inside(cx, cy, prev_boxes[ti]) and box[2] * box[3] > 0.15 * prev_boxes[ti][2] * prev_boxes[ti][3]:
                        child = Track(next_id, fi, box, label); child.parent = t
                        t.taint("split", child, fi)
                        break
                else:
                    child = Track(next_id, fi, box, label)
                tracks.append(child); next_id += 1
            masks[fi] = lab
            if args.debug and fi % 25 == 0:
                vis = frame.copy()
                for t in tracks:
                    if t.frames[-1] != fi: continue
                    x, y, bw, bh = [int(v) for v in t.boxes[-1]]
                    col = (0, 200, 0) if t.isolated() else (0, 0, 255)
                    cv2.rectangle(vis, (x, y), (x + bw, y + bh), col, 2)
                    cv2.putText(vis, str(t.id), (x, y - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.6, col, 2)
                cv2.imwrite(str(args.debug / f"{folder.name}_{fi:05d}.jpg"), vis)
            # retire
            still = []
            for t in tracks:
                if t.missed > 3: done.append(t)
                else: still.append(t)
            tracks = still
            # cut out finished tracks right away and drop their masks
            for t in [t for t in done if not getattr(t, "written", False)]:
                t.written = True
                kept += write_clip(t, files, masks, plate, gain, args, folder.name)
            keep_from = min([t.frames[0] for t in tracks], default=fi)
            for k in [k for k in masks if k < keep_from]:
                del masks[k]
        done += tracks
        for t in [t for t in done if not getattr(t, "written", False)]:
            t.written = True
            kept += write_clip(t, files, masks, plate, gain, args, folder.name)
    print("clips kept:", kept, "rejected:", REJECT)


REJECT = {}


def reject(why, t=None):
    REJECT[why] = REJECT.get(why, 0) + 1
    if t is not None and len(t.frames) >= 40:
        b0, b1 = [int(v) for v in t.boxes[0]], [int(v) for v in t.boxes[-1]]
        print(f"track {t.id} len {len(t.frames)} f{t.frames[0]}-{t.frames[-1]} {why}: first {b0} last {b1} missed {t.missed}")
    return 0


def sane_shape(boxes, lane, h):
    """One vehicle is never wider than about 1.3 lanes at its own row, nor
    taller than most of the road. Anything bigger is a merged pack."""
    for x, y, w, bh in boxes:
        yb = min(y + bh, h)
        lane_w = bound_x(lane + 1, yb) - bound_x(lane, yb)
        if w > 1.3 * lane_w or bh > 0.8 * (h - 425):
            return False
    return True


def write_clip(t, files, masks, plate, gain, args, src):
    if len(t.frames) < args.min_len:
        return reject("short")
    if not t.isolated():
        return reject("touched")
    h, w = plate.shape[:2]
    first, last = t.boxes[0], t.boxes[-1]
    if first[1] > 520:
        return reject("late start", t)
    if last[1] + last[3] < h - 12 and last[0] + last[2] < w - 12:
        return reject("early end", t)
    lanes = [lane_of(*bottom_center(b)) for b in t.boxes]
    lane = max(set(lanes), key=lanes.count)
    if lane < 0 or lane > 3 or lanes.count(lane) < 0.9 * len(lanes):
        return reject("lane change", t)
    if not sane_shape(t.boxes, lane, h):
        return reject("too big", t)
    frames, boxes, labels = [], [], []
    for k in range(len(t.frames)):
        if k and t.frames[k] - t.frames[k - 1] > 1:
            f0, f1 = t.frames[k - 1], t.frames[k]
            for fi in range(f0 + 1, f1):
                a = (fi - f0) / (f1 - f0)
                frames.append(fi); boxes.append(t.boxes[k - 1] * (1 - a) + t.boxes[k] * a); labels.append(None)
        frames.append(t.frames[k]); boxes.append(t.boxes[k]); labels.append(t.labels[k])
    cid = f"{src}_{t.id:04d}"
    d = args.out / f"lane{lane + 1}" / cid
    d.mkdir(parents=True, exist_ok=True)
    meta = {"lane": lane + 1, "source": src, "fps": FPS, "boxes": [], "start_frame": int(t.frames[0])}
    prev_rgba = None
    for fi, box, label in zip(frames, boxes, labels):
        if label is None:   # missed frame: hold the previous cut-out
            x, y = int(box[0]), int(box[1])
            cv2.imwrite(str(d / f"{fi - frames[0]:03d}.png"), prev_rgba)
            meta["boxes"].append([x, y, prev_rgba.shape[1], prev_rgba.shape[0]])
            continue
        lab = masks[fi]
        x, y, bw, bh = [int(v) for v in box]
        pad = 6
        x0, y0, x1, y1 = max(x - pad, 0), max(y - pad, 0), min(x + bw + pad, w), min(y + bh + pad, h)
        frame = cv2.imread(str(files[fi]))
        crop = np.clip(frame[y0:y1, x0:x1].astype(np.float32) * gain[y0:y1, x0:x1], 0, 255).astype(np.uint8)
        comp = (lab[y0:y1, x0:x1] == label).astype(np.uint8) * 255
        a = (soft_alpha(comp) * 255).astype(np.uint8)
        rgba = np.dstack([crop, a]); prev_rgba = rgba
        cv2.imwrite(str(d / f"{fi - frames[0]:03d}.png"), rgba)
        meta["boxes"].append([x0, y0, x1 - x0, y1 - y0])
    (d / "meta.json").write_text(json.dumps(meta))
    return 1


if __name__ == "__main__":
    main()
