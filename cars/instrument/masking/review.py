# /// script
# requires-python = ">=3.11"
# dependencies = ["opencv-python", "numpy"]
# ///
"""Review new transparent atlases on the actual clean plate, without changing them."""

import argparse
import itertools
import json
from pathlib import Path

import cv2
import numpy as np


def run(root):
    out = root / "output-figment/masked"
    review = out / "review"
    review.mkdir(exist_ok=True)
    plate = cv2.imread(str(root / "output-figment/plate.png"))
    summaries = []
    jobs = [
        (p, json.loads(p.read_text())) for p in sorted((out / "jobs").glob("*.json"))
    ]
    jobs = [(p, j) for p, j in jobs if j.get("version") == 4]
    for p, job in jobs:
        c = job["clip"]
        target = review / f"{p.stem}.jpg"
        if target.exists() and target.stat().st_mtime >= p.stat().st_mtime:
            continue
        sheet = cv2.imread(str(root / "output-figment" / c["sheet"]), -1)
        assert sheet is not None and sheet.shape[2] == 4
        cells = []
        n = len(c["frameRects"])
        for i in sorted(
            {
                0,
                int((n - 1) * 0.25),
                int((n - 1) * 0.5),
                int((n - 1) * 0.75),
                int((n - 1) * 0.9),
                n - 1,
            }
        ):
            sx, sy, w, h = c["frameRects"][i]
            x, y, _, _ = c["boxes"][i * 2]
            x, y = round(x), round(y)
            sprite = sheet[sy : sy + h, sx : sx + w]
            assert sprite.shape == (h, w, 4)
            canvas = plate.copy()
            a = sprite[:, :, 3:4] / 255
            ih = min(h, 1080 - y)
            iw = min(w, 1920 - x)
            canvas[y : y + ih, x : x + iw] = (
                sprite[:ih, :iw, :3] * a[:ih, :iw]
                + canvas[y : y + ih, x : x + iw] * (1 - a[:ih, :iw])
            ).astype(np.uint8)
            pad = max(20, round(w * 0.1))
            l = max(0, x - pad)
            t = max(0, y - pad)
            r = min(1920, x + w + pad)
            b = min(1080, y + h + pad)
            crop = canvas[t:b, l:r]
            scale = min(300 / crop.shape[1], 280 / crop.shape[0])
            crop = cv2.resize(crop, None, fx=scale, fy=scale)
            cell = np.full((320, 320, 3), 238, np.uint8)
            yy = (320 - crop.shape[0]) // 2
            xx = (320 - crop.shape[1]) // 2
            cell[yy : yy + crop.shape[0], xx : xx + crop.shape[1]] = crop
            cv2.putText(
                cell,
                f"{p.stem} / {i * 2}",
                (5, 18),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.38,
                (15, 15, 15),
                1,
            )
            cells.append(cell)
        while len(cells) < 6:
            cells.append(np.full((320, 320, 3), 238, np.uint8))
        cv2.imwrite(
            str(target), np.vstack([np.hstack(cells[:3]), np.hstack(cells[3:])])
        )
    for p, j in jobs:
        metrics = j["metrics"]
        summaries.append(
            {
                "id": p.stem,
                "samples": len(metrics),
                "max_area_ratio": max(m["area_ratio"] for m in metrics),
                "crop_edge_frames": [m["frame"] for m in metrics if m["crop_edge"]],
                "zero_shadow_frames": [
                    m["frame"] for m in metrics if m["shadow_pixels"] == 0
                ],
                "area_jump_frames": [
                    b["frame"]
                    for a, b in itertools.pairwise(metrics)
                    if not 0.65 <= b["body_area"] / a["body_area"] <= 1.55
                    and all(
                        m["body_bounds"][1] + m["body_bounds"][3] < 1078 for m in [a, b]
                    )
                ],
                "atlas_size": j["atlas_size"],
                "bytes": j["bytes"],
            }
        )
    reviewed_path = review / "visual-review.json"
    reviewed = json.loads(reviewed_path.read_text()) if reviewed_path.exists() else {}
    hashes = {p.stem: j["sha256"] for p, j in jobs}
    pending = [r for r in summaries if reviewed.get(r["id"]) != hashes[r["id"]]]
    (review / "pending-review.json").write_text(
        json.dumps([r["id"] for r in pending], indent=2)
    )
    for prefix, rows in [("overview", summaries), ("pending-overview", pending)]:
        page_count = (len(rows) + 7) // 8
        for old in review.glob(f"{prefix}-*.jpg"):
            if int(old.stem.rsplit("-", 1)[1]) > page_count:
                old.unlink()
        for page in range(page_count):
            canvas = np.full((1280, 1920, 3), 238, np.uint8)
            for k, row in enumerate(rows[page * 8 : (page + 1) * 8]):
                contact = cv2.imread(str(review / f"{row['id']}.jpg"))
                strip = np.hstack(
                    [
                        contact[:320, :320],
                        contact[:320, 640:960],
                        contact[320:640, 320:640],
                    ]
                )
                y, x = (k // 2) * 320, (k % 2) * 960
                canvas[y : y + 320, x : x + 960] = strip
            cv2.imwrite(str(review / f"{prefix}-{page + 1:02d}.jpg"), canvas)
    (review / "audit.json").write_text(json.dumps(summaries, indent=2))
    print(
        json.dumps(
            {
                "reviewed": len(summaries),
                "edge_flags": sum(len(s["crop_edge_frames"]) for s in summaries),
                "bytes": sum(s["bytes"] for s in summaries),
            }
        )
    )


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("root", type=Path)
    run(ap.parse_args().root.resolve())
