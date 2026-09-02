"""Markdown table of the variant experiments in an output folder.

Reads each variant's training_log.txt (params, GMAC, epoch time, ONNX CPU
time), eval_epoch_N/metrics.json (box-side L1, PSNR, SSIM against the targets
and against V0), and, when present, the Mac-side files bench_epoch_N.json
(Figment fp16 timing) and vs_V0_e{N}.txt (frame comparison with V0).

  uv run python scripts/summarize_experiments.py output-exp [--epoch 4] > output-exp/summary.md
"""

import argparse
import json
import os
import re


def read(path):
    try:
        with open(path) as f:
            return f.read()
    except OSError:
        return ""


def parse_log(text, epoch):
    info = {}
    m = re.search(r"G ([\d.]+)M params, ([\d.]+) GMAC per frame \(channels (\[[^\]]*\])", text)
    if m:
        info["params"], info["gmac"], info["channels"] = float(m[1]), float(m[2]), m[3]
    times = [float(x) for x in re.findall(r"epoch \d+ done in ([\d.]+) min", text)]
    if times:
        info["epoch_min"] = sum(times) / len(times)
    losses = re.findall(rf"epoch ({epoch}) iter \d+/\d+ \| d ([\d.]+) .*?adv ([\d.]+) l1 ([\d.]+) vgg ([\d.]+)", text)
    if losses:
        info["losses"] = losses[-1]
    for ep, ms in re.findall(r"onnx generator_epoch_(\d+)\.onnx: .*?cpu (\d+) ms", text):
        info[f"cpu_ms_e{ep}"] = int(ms)
    return info


def parse_vs(text):
    m = re.search(r"PSNR min [\d.]+ mean ([\d.]+) \| SSIM min [\d.]+ mean ([\d.]+)", text)
    return (float(m[1]), float(m[2])) if m else (None, None)


def fmt(v, spec=".3f"):
    return "" if v is None else format(v, spec)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("exp_dir")
    ap.add_argument("--epoch", type=int, default=4)
    args = ap.parse_args()
    e = args.epoch

    names = sorted(d for d in os.listdir(args.exp_dir) if os.path.isdir(os.path.join(args.exp_dir, d)))
    names.sort(key=lambda n: (n != "V0", n))
    rows = []
    for name in names:
        d = os.path.join(args.exp_dir, name)
        info = parse_log(read(os.path.join(d, "training_log.txt")), e)
        flags = read(os.path.join(d, "variant.txt")).strip()
        if "params" not in info and not flags:
            continue
        metrics = {}
        for eval_dir in (f"eval_epoch_{e}", "eval"):  # "eval": an external baseline such as pix2pix
            try:
                metrics = json.load(open(os.path.join(d, eval_dir, "metrics.json")))
                break
            except (OSError, ValueError):
                pass
        bench = {}
        try:
            bench = json.load(open(os.path.join(d, f"bench_epoch_{e}.json")))
        except (OSError, ValueError):
            pass
        vs_psnr, vs_ssim = parse_vs(read(os.path.join(d, f"vs_V0_e{e}.txt")))
        loss = info.get("losses")
        rows.append([
            name, flags, fmt(info.get("params"), ".1f"), fmt(info.get("gmac"), ".1f"),
            fmt(info.get("epoch_min"), ".1f"),
            f"{loss[3]} / {loss[4]}" if loss else "",
            fmt(metrics.get("l1")), fmt(metrics.get("psnr"), ".2f"), fmt(metrics.get("ssim"), ".4f"),
            fmt(metrics.get("psnr_vs_ref"), ".2f"), fmt(metrics.get("ssim_vs_ref"), ".4f"),
            fmt(info.get(f"cpu_ms_e{e}", metrics.get("ms_cpu")), ".0f"),
            fmt(bench.get("ms"), ".1f"), fmt(bench.get("fps"), ".1f"),
            fmt(vs_psnr, ".2f"), fmt(vs_ssim, ".4f"),
        ])

    head = ["variant", "flags", "G Mparams", "GMAC", "min/epoch", f"train l1 / vgg (e{e})",
            f"L1 e{e}", "PSNR", "SSIM", "PSNR vs V0", "SSIM vs V0", "box CPU ms",
            "Figment fp16 ms", "fps", "frames PSNR vs V0", "frames SSIM vs V0"]
    print(f"# Variant experiments, epoch {e}\n")
    print("Box-side metrics on 48 fixed pairs (onnxruntime CPU). Figment columns come from "
          "`stylegan/bench_variants.sh` on the Mac: fp16 model, `onnx-image:inference-total` p50, "
          "and PSNR/SSIM of 40 rendered frames against V0's frames.\n")
    print("| " + " | ".join(head) + " |")
    print("|" + "---|" * len(head))
    for r in rows:
        print("| " + " | ".join(str(c) for c in r) + " |")


if __name__ == "__main__":
    main()
