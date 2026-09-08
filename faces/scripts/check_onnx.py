"""Run an exported ONNX on a conditioning image with onnxruntime.

Prints the model's input/output shapes (what Figment reads) and writes
`[input | output]` or, with --pair, `[input | output | target]`.

  uv run scripts/check_onnx.py MODEL.onnx PAIR_OR_COND.jpg OUT.jpg [--pair]
"""

import argparse
import time

import numpy as np
import onnxruntime as ort
from PIL import Image


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("model")
    ap.add_argument("image")
    ap.add_argument("out")
    ap.add_argument("--pair", action="store_true", help="image is a [target | input] pair; use the right half")
    args = ap.parse_args()

    sess = ort.InferenceSession(args.model, providers=["CUDAExecutionProvider", "CPUExecutionProvider"])
    inp, out = sess.get_inputs()[0], sess.get_outputs()[0]
    print(f"input  {inp.name} {inp.shape} {inp.type}")
    print(f"output {out.name} {out.shape} {out.type}")
    _, _, h, w = inp.shape

    img = Image.open(args.image).convert("RGB")
    target = None
    if args.pair:
        target = img.crop((0, 0, img.width // 2, img.height)).resize((w, h), Image.BICUBIC)
        img = img.crop((img.width // 2, 0, img.width, img.height))
    img = img.resize((w, h), Image.BICUBIC)
    x = (np.asarray(img).astype(np.float32) / 127.5 - 1.0).transpose(2, 0, 1)[None]

    sess.run([out.name], {inp.name: x})  # warm-up
    t0 = time.time()
    y = sess.run([out.name], {inp.name: x})[0]
    print(f"inference {1000 * (time.time() - t0):.1f} ms ({sess.get_providers()[0]})")

    y = Image.fromarray(((y[0].transpose(1, 2, 0) + 1) * 127.5).clip(0, 255).astype(np.uint8))
    panels = [img, y] + ([target] if target is not None else [])
    strip = Image.new("RGB", (w * len(panels), h))
    for i, p in enumerate(panels):
        strip.paste(p, (i * w, 0))
    strip.save(args.out, quality=92)
    print("wrote", args.out)


if __name__ == "__main__":
    main()
