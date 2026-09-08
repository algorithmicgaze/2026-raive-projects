"""Rank clips by "speckle": how much high-frequency texture a frame carries.

Confetti and mosaic artefacts fill a frame with small high-contrast blobs, so
their edge density is far above that of a clean cartoon render. The score is
the mean absolute Laplacian of the grayscale frame, averaged over sampled
frames. Lower is cleaner.

  uv run scripts/speckle_score.py media/clips/*.mp4 media/clips_ab/*.mp4 [--step 20] [--json out.json]
"""

import argparse
import json
from pathlib import Path

import cv2
import numpy as np


def score(path, step=20, width=384):
    cap = cv2.VideoCapture(str(path))
    values, i = [], 0
    while True:
        ok, bgr = cap.read()
        if not ok:
            break
        if i % step == 0:
            h = int(bgr.shape[0] * width / bgr.shape[1])
            gray = cv2.cvtColor(cv2.resize(bgr, (width, h), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY)
            values.append(float(np.abs(cv2.Laplacian(gray, cv2.CV_32F)).mean()))
        i += 1
    cap.release()
    return float(np.mean(values)) if values else float("nan")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("clips", nargs="+", type=Path)
    ap.add_argument("--step", type=int, default=20)
    ap.add_argument("--json", type=Path)
    args = ap.parse_args()
    rows = sorted(((score(c, args.step), c) for c in args.clips), key=lambda r: r[0])
    for s, c in rows:
        print(f"{s:7.2f}  {c}")
    if args.json:
        args.json.write_text(json.dumps({str(c): s for s, c in rows}, indent=1))


if __name__ == "__main__":
    main()
