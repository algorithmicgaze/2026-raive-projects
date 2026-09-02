# /// script
# requires-python = ">=3.12"
# dependencies = ["onnxruntime", "numpy", "pillow", "scikit-image"]
# ///
"""Box-side quality numbers for one exported ONNX.

Runs the model on a fixed, evenly spaced subset of the pairs with onnxruntime
(CPU), writes every output as PNG, and reports L1, PSNR and SSIM against the
targets. With --ref pointing at another run's output folder (the V0 reference),
it also reports PSNR and SSIM against those outputs. A contact sheet of six
rows [mesh | output | target] goes next to the metrics.

  uv run scripts/eval_variant.py MODEL.onnx datasets/three_faces OUT_DIR [--count 48] [--ref output-exp/V0/eval_epoch_4]
"""

import argparse
import json
import os
import time

import numpy as np
import onnxruntime as ort
from PIL import Image
from skimage.metrics import structural_similarity


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("model")
    ap.add_argument("dataset")
    ap.add_argument("out_dir")
    ap.add_argument("--count", type=int, default=48)
    ap.add_argument("--ref", default=None, help="folder with reference outputs (same file names)")
    args = ap.parse_args()

    files = sorted(f for f in os.listdir(args.dataset) if f.lower().endswith((".jpg", ".png")))
    picks = [files[int(i)] for i in np.linspace(0, len(files) - 1, args.count)]
    os.makedirs(args.out_dir, exist_ok=True)

    sess = ort.InferenceSession(args.model, providers=["CPUExecutionProvider"])
    inp = sess.get_inputs()[0]
    _, _, h, w = inp.shape

    rows, times, tiles = [], [], []
    for i, name in enumerate(picks):
        pair = Image.open(os.path.join(args.dataset, name)).convert("RGB")
        target = pair.crop((0, 0, pair.width // 2, pair.height)).resize((w, h), Image.BICUBIC)
        cond = pair.crop((pair.width // 2, 0, pair.width, pair.height)).resize((w, h), Image.BICUBIC)
        x = (np.asarray(cond).astype(np.float32) / 127.5 - 1.0).transpose(2, 0, 1)[None]
        t0 = time.time()
        y = sess.run(None, {inp.name: x})[0]
        times.append(time.time() - t0)
        out = ((y[0].transpose(1, 2, 0) + 1) * 127.5).clip(0, 255).astype(np.uint8)
        out_path = os.path.join(args.out_dir, os.path.splitext(name)[0] + ".png")
        Image.fromarray(out).save(out_path)

        t = np.asarray(target).astype(np.float64)
        o = out.astype(np.float64)
        mse = np.mean((o - t) ** 2)
        row = {
            "file": name,
            "l1": float(np.abs(o - t).mean() / 127.5),  # in the [-1, 1] scale the trainer logs
            "psnr": float(99.0 if mse == 0 else 10 * np.log10(255**2 / mse)),
            "ssim": float(structural_similarity(o, t, channel_axis=2, data_range=255)),
        }
        if args.ref:
            r = np.asarray(Image.open(os.path.join(args.ref, os.path.basename(out_path))).convert("RGB")).astype(np.float64)
            mse_r = np.mean((o - r) ** 2)
            row["psnr_vs_ref"] = float(99.0 if mse_r == 0 else 10 * np.log10(255**2 / mse_r))
            row["ssim_vs_ref"] = float(structural_similarity(o, r, channel_axis=2, data_range=255))
        rows.append(row)
        if i % max(1, args.count // 6) == 0 and len(tiles) < 6:
            tiles.append(np.concatenate([np.asarray(cond), out, np.asarray(target)], axis=1))

    keys = [k for k in rows[0] if k != "file"]
    summary = {
        "model": args.model,
        "count": len(rows),
        "ms_cpu": float(np.median(times[1:]) * 1000) if len(times) > 1 else float(times[0] * 1000),
        **{k: float(np.mean([r[k] for r in rows])) for k in keys},
        "rows": rows,
    }
    with open(os.path.join(args.out_dir, "metrics.json"), "w") as f:
        json.dump(summary, f, indent=1)
    sheet = Image.fromarray(np.concatenate(tiles, axis=0))
    sheet.thumbnail((768, 4096))
    sheet.save(os.path.join(args.out_dir, "sheet.jpg"), quality=88)
    line = " ".join(f"{k} {summary[k]:.4f}" for k in keys)
    print(f"{args.model}: {len(rows)} pairs, cpu {summary['ms_cpu']:.0f} ms, {line}")


if __name__ == "__main__":
    main()
