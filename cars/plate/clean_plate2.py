# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy", "opencv-python-headless", "tqdm"]
# ///
"""Iterative masked clean plate.

1. Read all frames into a disk memmap (once).
2. Plate 0 = temporal median.
3. Repeat: mark a sample as 'road' when it is within tol of the current
   plate (after a small blur, so JPEG noise does not count), then set the
   plate to the median of the road samples only. Pixels with too few road
   samples keep the previous value and are reported in a hole mask.
Also writes an occupancy timeline over a road polygon: fraction of road
pixels that differ from the plate, per frame, so the emptiest moments can
be found.
"""
import argparse
from pathlib import Path

import cv2
import numpy as np
from tqdm import tqdm

ROAD_POLY = np.array([(830, 420), (1250, 420), (1920, 880), (1920, 1080), (300, 1080)])


def build_memmap(folder: Path, path: Path, step: int):
    files = sorted(folder.glob("*.jpg"))[::step]
    first = cv2.imread(str(files[0]))
    shape = (len(files), *first.shape)
    if path.exists() and np.memmap(path, dtype=np.uint8, mode="r").size == np.prod(shape):
        return np.memmap(path, dtype=np.uint8, mode="r", shape=shape)
    mm = np.memmap(path, dtype=np.uint8, mode="w+", shape=shape)
    for i, f in enumerate(tqdm(files, desc="load")):
        mm[i] = cv2.imread(str(f))
    mm.flush()
    return np.memmap(path, dtype=np.uint8, mode="r", shape=shape)


def band_iter(h, bands):
    step = -(-h // bands)
    for y0 in range(0, h, step):
        yield y0, min(y0 + step, h)


def masked_median(mm, plate, tol, min_samples, bands=12):
    n, h, w, _ = mm.shape
    out = plate.copy()
    holes = np.zeros((h, w), dtype=np.uint8)
    counts = np.zeros((h, w), dtype=np.int32)
    for y0, y1 in tqdm(list(band_iter(h, bands)), desc=f"masked median tol={tol}"):
        band = np.asarray(mm[:, y0:y1])  # (n, bh, w, 3)
        ref = plate[y0:y1]
        if plate is None:
            med = np.median(band, axis=0)
        else:
            diff = np.abs(band.astype(np.int16) - ref.astype(np.int16)).max(-1)  # (n, bh, w)
            # blur the difference so a single noisy pixel does not flip
            diff = np.stack([cv2.blur(d.astype(np.float32), (5, 5)) for d in diff])
            road = diff < tol
            c = road.sum(0)
            counts[y0:y1] = c
            bandf = band.astype(np.float32)
            bandf[~road] = np.nan
            med = np.nanmedian(bandf, axis=0)
            ok = c >= min_samples
            med[~ok] = ref[~ok]
            holes[y0:y1] = (~ok).astype(np.uint8) * 255
        out[y0:y1] = np.nan_to_num(med).astype(np.uint8)
    return out, holes, counts


def plain_median(mm, bands=12):
    n, h, w, _ = mm.shape
    out = np.empty((h, w, 3), dtype=np.uint8)
    for y0, y1 in tqdm(list(band_iter(h, bands)), desc="median"):
        out[y0:y1] = np.median(np.asarray(mm[:, y0:y1]), axis=0).astype(np.uint8)
    return out


def occupancy(mm, plate, tol):
    n, h, w, _ = mm.shape
    mask = np.zeros((h, w), dtype=np.uint8)
    cv2.fillPoly(mask, [ROAD_POLY], 255)
    mask = mask > 0
    frac = np.empty(n)
    for i in tqdm(range(n), desc="occupancy"):
        d = np.abs(mm[i].astype(np.int16) - plate.astype(np.int16)).max(-1)
        d = cv2.blur(d.astype(np.float32), (5, 5))
        frac[i] = ((d > tol) & mask).sum() / mask.sum()
    return frac


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("frames", type=Path)
    ap.add_argument("--out", type=Path, default=Path("output-plate"))
    ap.add_argument("--memmap", type=Path, default=Path("output-plate/frames.u8"))
    ap.add_argument("--step", type=int, default=1)
    ap.add_argument("--iters", type=int, default=3)
    ap.add_argument("--tol", type=float, default=18)
    ap.add_argument("--min-samples", type=int, default=20)
    args = ap.parse_args()
    args.out.mkdir(exist_ok=True)

    mm = build_memmap(args.frames, args.memmap, args.step)
    print("frames", mm.shape)

    plate = plain_median(mm)
    cv2.imwrite(str(args.out / "iter0.png"), plate)
    for it in range(1, args.iters + 1):
        plate, holes, counts = masked_median(mm, plate, args.tol, args.min_samples)
        cv2.imwrite(str(args.out / f"iter{it}.png"), plate)
        cv2.imwrite(str(args.out / f"iter{it}_holes.png"), holes)
        cnt = np.clip(counts / mm.shape[0] * 255, 0, 255).astype(np.uint8)
        cv2.imwrite(str(args.out / f"iter{it}_roadfrac.png"), cv2.applyColorMap(cnt, cv2.COLORMAP_VIRIDIS))
        print(f"iter {it}: holes {holes.mean() / 255 * 100:.2f}% of pixels")

    frac = occupancy(mm, plate, args.tol)
    np.save(args.out / "occupancy.npy", frac)
    order = np.argsort(frac)
    print("emptiest frames (index, occupied fraction):")
    for i in order[:15]:
        print(f"  {i:5d}  t={i * args.step:5d}s  {frac[i]:.3f}")
    # timeline strip
    strip = np.full((120, mm.shape[0]), 255, dtype=np.uint8)
    for i, f in enumerate(frac):
        strip[int(120 - f * 120):, i] = 0
    cv2.imwrite(str(args.out / "occupancy.png"), strip)


if __name__ == "__main__":
    main()
