# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy", "opencv-python-headless", "tqdm"]
# ///
"""Build a clean plate (empty road) from sparse frames of a fixed camera.

Strategies, each written as its own image so they can be compared:
  median  - per-pixel temporal median. Works where the road is visible
            more than half of the time.
  mode    - per-pixel most frequent colour (coarse histogram). Works where
            the road is the single most consistent value, even below 50%.
  spread  - median absolute deviation: bright = the median is unreliable
            (vehicles occupied that pixel most of the time).
"""
import argparse
from pathlib import Path

import cv2
import numpy as np
from tqdm import tqdm


def load_frames(folder: Path, step: int, limit: int | None):
    files = sorted(folder.glob("*.jpg"))[::step]
    if limit:
        files = files[:limit]
    first = cv2.imread(str(files[0]))
    stack = np.empty((len(files), *first.shape), dtype=np.uint8)
    for i, f in enumerate(tqdm(files, desc="load")):
        stack[i] = cv2.imread(str(f))
    return stack


def median_plate(stack, bands=8):
    h = stack.shape[1]
    out = np.empty(stack.shape[1:], dtype=np.uint8)
    spread = np.empty(stack.shape[1:3], dtype=np.float32)
    for y0 in tqdm(range(0, h, h // bands), desc="median"):
        y1 = min(y0 + h // bands, h)
        band = stack[:, y0:y1]
        med = np.median(band, axis=0)
        out[y0:y1] = med.astype(np.uint8)
        spread[y0:y1] = np.median(np.abs(band.astype(np.int16) - med.astype(np.int16)), axis=0).mean(-1)
    return out, spread


def mode_plate(stack, bins=32, bands=8):
    """Most frequent quantised colour per pixel, then the mean of the
    samples that fall in that bin (so the result is not posterised)."""
    n, h, w, _ = stack.shape
    out = np.empty((h, w, 3), dtype=np.uint8)
    q = 256 // bins
    for y0 in tqdm(range(0, h, h // bands), desc="mode"):
        y1 = min(y0 + h // bands, h)
        band = stack[:, y0:y1].astype(np.int32)
        code = (band[..., 0] // q) * bins * bins + (band[..., 1] // q) * bins + (band[..., 2] // q)
        bh, bw = code.shape[1:]
        flat = code.reshape(n, -1)
        # per-pixel histogram via sort + run lengths
        s = np.sort(flat, axis=0)
        change = np.ones_like(s, dtype=bool)
        change[1:] = s[1:] != s[:-1]
        # run id per column
        cols = np.arange(s.shape[1])
        # run length = next run start - this run start
        starts = np.where(change, np.arange(n)[:, None], n)
        starts_sorted = np.sort(starts, axis=0)
        lengths = np.diff(np.vstack([starts_sorted, np.full((1, s.shape[1]), n)]), axis=0)
        best = np.argmax(lengths, axis=0)
        best_start = starts_sorted[best, cols]
        best_code = s[best_start, cols]
        mask = flat == best_code[None, :]
        band_f = stack[:, y0:y1].reshape(n, -1, 3).astype(np.float32)
        mean = (band_f * mask[..., None]).sum(0) / mask.sum(0)[:, None]
        out[y0:y1] = mean.reshape(bh, bw, 3).astype(np.uint8)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("frames", type=Path)
    ap.add_argument("--out", type=Path, default=Path("output-plate"))
    ap.add_argument("--step", type=int, default=3, help="use every Nth frame")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--scale", type=float, default=1.0, help="downscale frames before processing")
    args = ap.parse_args()
    args.out.mkdir(exist_ok=True)

    stack = load_frames(args.frames, args.step, args.limit)
    if args.scale != 1.0:
        stack = np.stack([cv2.resize(f, None, fx=args.scale, fy=args.scale, interpolation=cv2.INTER_AREA) for f in stack])
    print("stack", stack.shape, f"{stack.nbytes / 1e9:.1f} GB")

    med, spread = median_plate(stack)
    cv2.imwrite(str(args.out / "median.png"), med)
    sp = np.clip(spread / spread.max() * 255, 0, 255).astype(np.uint8)
    cv2.imwrite(str(args.out / "spread.png"), cv2.applyColorMap(sp, cv2.COLORMAP_INFERNO))

    mode = mode_plate(stack)
    cv2.imwrite(str(args.out / "mode.png"), mode)
    print("wrote", args.out)


if __name__ == "__main__":
    main()
