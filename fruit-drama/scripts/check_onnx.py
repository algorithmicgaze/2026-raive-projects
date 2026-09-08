"""Run a trained pix2pix ONNX on a conditioning image with onnxruntime.

Prints the model's input/output shapes (what Figment reads) and writes
`[input | output]` side by side.

  uv run scripts/check_onnx.py MODEL.onnx PAIR_OR_COND.jpg OUT.jpg [--pair]
"""

import argparse

import cv2
import numpy as np
import onnxruntime as ort


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("model")
    ap.add_argument("image")
    ap.add_argument("out")
    ap.add_argument("--pair", action="store_true", help="image is a [target | input] pair; use the right half")
    args = ap.parse_args()

    sess = ort.InferenceSession(args.model, providers=["CUDAExecutionProvider", "CPUExecutionProvider"])
    inp = sess.get_inputs()[0]
    out = sess.get_outputs()[0]
    print(f"input  {inp.name} {inp.shape} {inp.type}")
    print(f"output {out.name} {out.shape} {out.type}")
    _, _, h, w = inp.shape

    bgr = cv2.imread(args.image)
    if args.pair:
        bgr = bgr[:, bgr.shape[1] // 2:]
    bgr = cv2.resize(bgr, (w, h), interpolation=cv2.INTER_AREA)
    x = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB).astype(np.float32) / 127.5 - 1.0
    x = x.transpose(2, 0, 1)[None]

    import time
    t0 = time.time()
    y = sess.run([out.name], {inp.name: x})[0]
    print(f"inference {1000 * (time.time() - t0):.1f} ms ({sess.get_providers()[0]})")

    y = ((y[0].transpose(1, 2, 0) + 1) * 127.5).clip(0, 255).astype(np.uint8)
    y = cv2.cvtColor(y, cv2.COLOR_RGB2BGR)
    cv2.imwrite(args.out, np.concatenate([bgr, y], axis=1))
    print("wrote", args.out)


if __name__ == "__main__":
    main()
