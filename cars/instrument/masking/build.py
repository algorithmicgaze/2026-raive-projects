# /// script
# requires-python = ">=3.11"
# dependencies = ["ultralytics==8.4.31", "opencv-python", "numpy"]
# ///
"""Rebuild source-derived vehicle masks and contact shadows from the 1080p master.

Read-only inputs: original manifest, repaired/jobs tracking metadata and source video.
Outputs go to output-figment/masked; existing project files are not changed.
"""

import argparse
import hashlib
import itertools
import json
import math
import time
from pathlib import Path

import cv2
import numpy as np
from ultralytics import SAM

VERSION = 4


def atomic_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(data, indent=2))
    temp.replace(path)


def shadow_rgba(source, background, body):
    """Attenuation matte: black translucent shadow under unmodified source pixels."""
    sy = cv2.GaussianBlur(
        cv2.cvtColor(source, cv2.COLOR_BGR2GRAY).astype(np.float32), (3, 3), 0.65
    )
    by = cv2.GaussianBlur(
        cv2.cvtColor(background, cv2.COLOR_BGR2GRAY).astype(np.float32), (3, 3), 0.65
    )
    yy, xx = np.where(body > 0.5)
    if not len(xx):
        raise ValueError("Empty body mask")
    _x, y, w, h = (
        int(xx.min()),
        int(yy.min()),
        int(xx.max() - xx.min() + 1),
        int(yy.max() - yy.min() + 1),
    )
    distance = cv2.distanceTransform((body < 0.5).astype(np.uint8), cv2.DIST_L2, 5)
    ratio = sy / np.maximum(by, 15)
    reference = (distance > max(8, w * 0.12)) & (by > 40) & (by < 200)
    gain = float(
        np.clip(
            np.median(ratio[reference]) if reference.sum() > 30 else 1.0, 0.85, 1.15
        )
    )
    darkness = np.clip(1 - ratio / gain, 0, 0.85)
    strength = np.clip((darkness - 0.018) / 0.04, 0, 1) * darkness
    proximity = np.exp(-0.5 * (distance / (max(5, w * 0.12) * 0.58)) ** 2)
    rows = np.indices(body.shape)[0]
    lower = np.clip((rows - (y + h * 0.53)) / max(1, h * 0.18), 0, 1)
    shadow = cv2.GaussianBlur(
        strength * proximity * lower, (0, 0), max(0.65, w * 0.008)
    )
    shadow[shadow < 0.006] = 0
    alpha = body + (1 - body) * shadow
    rgb = np.divide(
        source.astype(np.float32) * body[:, :, None],
        alpha[:, :, None],
        out=np.zeros_like(source, dtype=np.float32),
        where=alpha[:, :, None] > 1e-6,
    )
    return np.dstack(
        [
            np.round(np.clip(rgb, 0, 255)).astype(np.uint8),
            np.round(alpha * 255).astype(np.uint8),
        ]
    ), {"gain": gain, "shadow_pixels": int(np.sum((shadow > 0.03) & (body < 0.5)))}


def crop_bounds(box, shape):
    x, y, w, h = box
    H, W = shape[:2]
    pad = max(30, min(100, w * 0.24))
    return (
        max(0, int(x - pad)),
        max(0, int(y - pad)),
        min(W, math.ceil(x + w + pad)),
        min(H, math.ceil(y + h + pad)),
    )


def segment(model, frame, plate, box, device):
    l, t, r, b = crop_bounds(box, frame.shape)
    if r - l < 5 or b - t < 5:
        return None
    crop = frame[t:b, l:r]
    H, W = crop.shape[:2]
    x, y, w, h = box
    visible = [max(0, x - l), max(0, y - t), min(W, x + w - l), min(H, y + h - t)]
    if visible[2] - visible[0] < 3 or visible[3] - visible[1] < 3:
        return None
    px = (visible[0] + visible[2]) * 0.5
    py = visible[1] + (visible[3] - visible[1]) * 0.45
    prompt = [
        max(0, visible[0] - 8),
        max(0, visible[1] - 8),
        min(W - 1, visible[2] + 8),
        min(H - 1, visible[3] + 8),
    ]
    result = model(
        crop,
        bboxes=prompt,
        points=[
            [
                [px, visible[1] + (visible[3] - visible[1]) * 0.15],
                [px, py],
                [px, visible[1] + (visible[3] - visible[1]) * 0.75],
            ]
        ],
        labels=[[1, 1, 1]],
        device=device,
        verbose=False,
        conf=0.25,
    )[0]
    retried = False
    if result.masks is None or len(result.masks.data) == 0:
        retried = True
        result = model(
            crop,
            bboxes=prompt,
            points=[
                [
                    [px, visible[1] + (visible[3] - visible[1]) * 0.15],
                    [px, py],
                    [px, visible[1] + (visible[3] - visible[1]) * 0.75],
                ]
            ],
            labels=[[1, 1, 1]],
            device=device,
            verbose=False,
            conf=0.0,
        )[0]
    if result.masks is None or len(result.masks.data) == 0:
        return None
    mask = result.masks.data[0].cpu().numpy().astype(np.uint8)
    if mask.shape != (H, W):
        mask = cv2.resize(mask, (W, H), interpolation=cv2.INTER_NEAREST)
    # Prompt boxes guide SAM, but do not constrain its output. Exclude
    # distant connected fragments from the following vehicle.
    limit = np.zeros_like(mask)
    margin_x = max(6, w * 0.06)
    margin_y = max(6, h * 0.06)
    ll = max(0, int(visible[0] - margin_x))
    rr = min(W, math.ceil(visible[2] + margin_x))
    tt = max(0, int(visible[1] - margin_y))
    bb = min(H, math.ceil(visible[3] + margin_y))
    limit[tt:bb, ll:rr] = 1
    mask *= limit
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    if count < 2:
        return None
    target = int(labels[min(H - 1, int(py)), min(W - 1, int(px))])
    if target == 0:
        target = 1 + int(np.argmax(stats[1:, 4]))
    mask = (labels == target).astype(np.uint8) * 255
    # A vehicle's windows and painted panels must remain opaque. Preserve the
    # outer silhouette while filling erroneous enclosed background holes.
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cv2.drawContours(mask, contours, -1, 255, cv2.FILLED)
    before_fill = int(np.sum(mask > 0))
    # Small, low-contrast vehicles sometimes have an open notch through solid
    # bodywork. Fill only the interior of a markedly more solid hull; retain
    # the measured silhouette at the boundary.
    hull = np.zeros_like(mask)
    cv2.fillConvexPoly(hull, cv2.convexHull(np.concatenate(contours)), 255)
    if np.sum(hull > 0) > before_fill * 1.12:
        inner = cv2.erode(hull, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)))
        mask = np.maximum(mask, inner)
    area = int(np.sum(mask > 0))
    expected = (visible[2] - visible[0]) * (visible[3] - visible[1])
    if area < max(15, expected * 0.06):
        return None
    body = cv2.GaussianBlur(mask, (3, 3), 0.45).astype(np.float32) / 255
    rgba, metrics = shadow_rgba(crop, plate[t:b, l:r], body)
    yy, xx = np.where(rgba[:, :, 3] > 0)
    left, right = int(xx.min()), int(xx.max() + 1)
    top, bottom = int(yy.min()), int(yy.max() + 1)
    body_y, body_x = np.where(mask > 0)
    touches = (
        (body_x.min() == 0 and l > 0)
        or (body_x.max() == W - 1 and r < 1920)
        or (body_y.min() == 0 and t > 0)
        or (body_y.max() == H - 1 and b < 1080)
    )
    metrics.update(
        low_confidence_retry=retried,
        core_fill_pixels=int(np.sum(mask > 0)) - before_fill,
        body_area=area,
        area_ratio=float(area / expected),
        crop_edge=bool(touches),
        body_bounds=[
            int(l + body_x.min()),
            int(t + body_y.min()),
            int(body_x.max() - body_x.min() + 1),
            int(body_y.max() - body_y.min() + 1),
        ],
    )
    return (
        rgba[top:bottom, left:right],
        [l + left, t + top, right - left, bottom - top],
        metrics,
    )


def pack(sprites):
    # Variable-size shelf packing avoids wasting a maximum-sized cell per frame.
    width = 4096
    x = y = row_h = 0
    rects = []
    for im in sprites:
        h, w = im.shape[:2]
        if w > width:
            raise ValueError(f"Sprite wider than atlas: {w}")
        if x + w > width:
            x = 0
            y += row_h
            row_h = 0
        rects.append([x, y, w, h])
        x += w
        row_h = max(row_h, h)
    height = y + row_h
    if height > 16384:
        raise ValueError(f"Atlas exceeds texture limit: {width}x{height}")
    sheet = np.zeros((height, width, 4), np.uint8)
    for im, (x, y, w, h) in zip(sprites, rects):
        sheet[y : y + h, x : x + w] = im
    return sheet, rects


def corrected_prompts(track, motion):
    """Reject identity switches, interpolate observations, retain measured exit flow.

    These boxes guide segmentation only. Final placement still uses source pixels.
    """
    track = sorted(track, key=lambda r: r["frame"])
    all_track = track
    confident = [r for r in track if r.get("confidence", 1.0) >= 0.4]
    if len(confident) >= 4:
        track = confident
    runs = [[0]]
    for i in range(1, len(track)):
        a = np.array(track[i - 1]["box"], float)
        b = np.array(track[i]["box"], float)
        dt = track[i]["frame"] - track[i - 1]["frame"]
        switched = (
            b[1] < a[1] - max(5, a[3] * 0.10)
            or np.any(b[2:] < a[2:] * 0.75)
            or np.any(b[2:] > a[2:] * np.exp(0.03 * max(1, dt)) + 8)
            or b[1] - a[1] > max(20, dt * max(3, a[3] * 0.15))
        )
        if switched:
            runs.append([])
        runs[-1].append(i)
    # Keep a continuous identity span, rather than joining an early leading car
    # to a following car after discarding the intervening observations.
    chosen = max(
        runs,
        key=lambda run: (len(run), track[run[-1]]["frame"] - track[run[0]]["frame"]),
    )
    selected = [track[i] for i in chosen]
    if len(selected) < 4:
        raise ValueError("Fewer than four consistent vehicle observations")
    ts = np.array([r["frame"] for r in selected])
    observed = np.array([r["box"] for r in selected], float)
    output = np.array(motion, float)
    last = min(int(ts[-1]), len(output) - 1)
    # Align the old optical-flow tail to the last measured vehicle observation.
    delta = observed[-1, :2] - output[last, :2]
    size_ratio = observed[-1, 2:] / output[last, 2:]
    output[last:, :2] += delta
    output[last:, 2:] *= size_ratio
    for k in range(4):
        output[: last + 1, k] = np.interp(np.arange(last + 1), ts, observed[:, k])
    return (
        output.tolist(),
        int(ts[0]),
        [
            r["frame"]
            for r in all_track
            if r["frame"] not in {v["frame"] for v in selected}
        ],
    )


def prepare(root, c):
    jid = Path(c["sheet"]).stem
    jobroot = root / "output-figment/repaired/jobs" / jid
    job = json.loads((jobroot / "job.json").read_text())
    meta_path = Path(job["source_meta"])
    meta = (
        root
        / meta_path.parts[-4]
        / meta_path.parts[-3]
        / meta_path.parts[-2]
        / meta_path.parts[-1]
    )
    if not meta.exists():
        candidates = [
            root / folder / f"lane{c['lane']}" / c["id"] / "meta.json"
            for folder in ["output-clips-groups", "output-clips"]
        ]
        meta = next(
            p
            for p in candidates
            if p.exists() and len(json.loads(p.read_text())["boxes"]) == len(c["boxes"])
        )
    metadata = json.loads(meta.read_text())
    detections = json.loads((jobroot / "detections.json").read_text())
    starts = {int(Path(d["file"]).stem[1:]) - 1 - int(d["frame"]) for d in detections}
    if len(starts) != 1:
        raise ValueError(f"Inconsistent source timing for {jid}")
    start = job.get("source_start_frame", next(iter(starts)))
    if start not in starts:
        raise ValueError(f"Source start disagrees with detections for {jid}")
    source = metadata["source"]
    base = int(source[1:]) * 25 + start
    motion = json.loads((jobroot / "motion.json").read_text())
    boxes, minimum, rejected = corrected_prompts(
        job.get("motion_track", job["track"]), motion["boxes"]
    )
    override_path = root / "output-figment/masked/prompt-overrides.json"
    override = (
        json.loads(override_path.read_text()).get(jid, {})
        if override_path.exists()
        else {}
    )
    if override:
        maximum_height = 0
        for box in boxes:
            maximum_height = max(maximum_height, box[3])
            extension = min(
                (maximum_height if override.get("hold_height") else box[3])
                * override.get("extend_top", 0),
                max(0, box[1] - override.get("min_top", 0)),
            )
            box[1] -= extension
            box[3] += extension
    # Do not extrapolate an occluded approach backwards into a different vehicle.
    offset = max(0, minimum)
    offset = max(offset, next((i for i, b in enumerate(boxes) if b[1] + b[3] > 430), 0))
    return (
        jid,
        base,
        boxes,
        offset,
        {
            "source_clip": source,
            "clip_start": start,
            "source_frame": base,
            "tracking_offset": offset,
            "rejected_tracking_frames": rejected,
            "last_observed_frame": max(
                r["frame"]
                for r in job.get("motion_track", job["track"])
                if r["frame"] not in rejected
            ),
            "tracking_method": "continuous identity span + interpolated prompts + measured exit",
            "kind": metadata.get("kind", "car"),
            "prompt_override": override,
        },
    )


def run(args):
    cv2.setNumThreads(2)
    root = args.root.resolve()
    out = root / "output-figment/masked"
    (out / "clips").mkdir(parents=True, exist_ok=True)
    (out / "jobs").mkdir(exist_ok=True)
    original = json.loads((root / "output-figment/manifest.json").read_text())
    unique = list({c["sheet"]: c for c in original["clips"]}.values())
    chosen = [c for c in unique if not args.only or Path(c["sheet"]).stem in args.only]
    chosen = chosen[args.shard :: args.shards]
    if args.shard % 2:
        chosen.reverse()
    model = None
    cap = cv2.VideoCapture(str(root / "media/highway-stabilized-1080p.mp4"))
    plate = cv2.imread(str(root / "output-figment/plate.png"))
    assert plate is not None
    starttime = time.time()
    for index, c in enumerate(chosen):
        try:
            jid, base, boxes, offset, provenance = prepare(root, c)
            jobfile = out / "jobs" / f"{jid}.json"
            if jobfile.exists() and not args.refresh:
                old = json.loads(jobfile.read_text())
                if (
                    old.get("version") == VERSION
                    and old.get("checkpoint") == args.checkpoint.name
                    and old.get("source", {}).get("prompt_override", {})
                    == provenance["prompt_override"]
                    and (root / "output-figment" / old["clip"]["sheet"]).exists()
                ):
                    continue
            if model is None:
                model = SAM(str(args.checkpoint))
            cap.set(cv2.CAP_PROP_POS_FRAMES, base + offset)
            sprites = []
            positions = []
            metrics = []
            samples = []
            gaps = []
            for n in range(offset, len(boxes)):
                ok, frame = cap.read()
                if not ok:
                    break
                if (n - offset) % 2:
                    continue
                result = segment(model, frame, plate, boxes[n], args.device)
                if result is None:
                    gaps.append(n)
                    if sprites and (
                        n > provenance["last_observed_frame"]
                        or boxes[n][1] > 1020
                        or boxes[n][0] > 1880
                        or boxes[n][0] + boxes[n][2] < 40
                    ):
                        break
                    if not sprites:
                        continue
                    raise ValueError(f"{jid}: empty mask mid-passage at frame {n}")
                sprite, pos, stat = result
                sprites.append(sprite)
                positions.append(pos)
                samples.append(n)
                metrics.append({"frame": n, **stat})
            if len(sprites) < 2:
                raise ValueError(f"{jid}: insufficient masks")
            if any(b - a != 2 for a, b in itertools.pairwise(samples)):
                raise ValueError(f"{jid}: discontinuous samples")
            sheet, rects = pack(sprites)
            file = out / "clips" / f"{jid}.png"
            temp = file.with_suffix(".tmp.png")
            cv2.imwrite(str(temp), sheet)
            temp.replace(file)
            playback = []
            for i, pos in enumerate(positions):
                playback.append(pos)
                if i + 1 < len(positions):
                    playback.append(
                        [
                            (pos[0] + positions[i + 1][0]) * 0.5,
                            (pos[1] + positions[i + 1][1]) * 0.5,
                            pos[2],
                            pos[3],
                        ]
                    )
                else:
                    playback.append(pos)
            clip = {
                **c,
                "sheet": f"masked/clips/{jid}.png",
                "boxes": playback,
                "frameRects": rects,
                "cell": [1, 1],
                "cols": 1,
                "sub": 2,
                "maskVersion": VERSION,
                "sourceFrameOffset": samples[0],
            }
            job = {
                "version": VERSION,
                "clip": clip,
                "source": provenance,
                "source_sample_frames": samples,
                "metrics": metrics,
                "skipped_frames": gaps,
                "sha256": hashlib.sha256(file.read_bytes()).hexdigest(),
                "bytes": file.stat().st_size,
                "atlas_size": [sheet.shape[1], sheet.shape[0]],
                "checkpoint": args.checkpoint.name,
            }
            atomic_json(jobfile, job)
            (out / "errors" / f"{jid}.json").unlink(missing_ok=True)
            print(
                json.dumps(
                    {
                        "done": jid,
                        "index": index + 1,
                        "selected": len(chosen),
                        "samples": len(samples),
                        "bytes": job["bytes"],
                        "edge_flags": sum(m["crop_edge"] for m in metrics),
                        "seconds": round(time.time() - starttime, 1),
                    }
                ),
                flush=True,
            )
        except Exception as exc:  # noqa: BLE001 - preserve completed independent clips
            jid = Path(c["sheet"]).stem
            atomic_json(out / "errors" / f"{jid}.json", {"id": jid, "error": str(exc)})
            print(json.dumps({"failed": jid, "error": str(exc)}), flush=True)
    completed = {
        p.stem: json.loads(p.read_text())
        for p in (out / "jobs").glob("*.json")
        if json.loads(p.read_text()).get("version") == VERSION
    }
    missing = [
        Path(c["sheet"]).stem for c in unique if Path(c["sheet"]).stem not in completed
    ]
    if not missing:
        manifest = {
            **original,
            "maskVersion": VERSION,
            "clips": [
                {
                    **completed[Path(c["sheet"]).stem]["clip"],
                    "id": c["id"],
                    "lane": c["lane"],
                    "cars": c["cars"],
                }
                for c in original["clips"]
            ],
        }
        atomic_json(root / "output-figment/manifest-masked.json", manifest)
    atomic_json(
        out / "status.json",
        {
            "complete": len(unique) - len(missing),
            "total": len(unique),
            "missing": missing,
            "elapsed_seconds": time.time() - starttime,
        },
    )


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--root", type=Path, required=True, help="Private Cars asset folder"
    )
    ap.add_argument("--checkpoint", type=Path, required=True)
    ap.add_argument("--device", default="mps")
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--shard", type=int, default=0)
    ap.add_argument("--shards", type=int, default=1)
    args = ap.parse_args()
    assert args.shards > 0 and 0 <= args.shard < args.shards
    run(args)
