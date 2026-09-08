"""Converts emotion2vec+ base (PyTorch, FunASR) to a compiled Core ML model.

usage: uv run convert.py OUT.mlmodelc [--seconds 3]

The model takes `waveform` (1, seconds*16000) float32 at 16 kHz and returns
`probs` (1, 9): angry disgusted fearful happy neutral other sad surprised unknown.
Waveform normalization, mean pooling, the linear head and softmax are inside the model.
"""

import argparse, os, shutil, subprocess, tempfile, wave
import numpy as np, torch, coremltools as ct
from funasr import AutoModel
from huggingface_hub import snapshot_download
import coremltools.converters.mil.frontend.torch.ops as tops
from coremltools.converters.mil import Builder as mb
from coremltools.converters.mil.frontend.torch.torch_op_registry import register_torch_op
from coremltools.converters.mil.mil import types

SR = 16000

# coremltools 9 + NumPy 2: int(np.array([v])) raises; fold length-1 arrays to a scalar first.
_orig_cast = tops._cast


def _cast(context, node, dtype, dtype_name):
    x = tops._get_inputs(context, node, expected=1)[0]
    if x.can_be_folded_to_const() and isinstance(x.val, np.ndarray) and x.val.ndim > 0:
        context.add(mb.const(val=dtype(x.val.reshape(-1)[0]), name=node.name), node.name)
        return
    return _orig_cast(context, node, dtype, dtype_name)


tops._cast = _cast


# FunASR clamps a float parameter with an int bound; cast the bound like coremltools' clamp does.
@register_torch_op(override=True)
def clamp_min(context, node):
    x, y = tops._get_inputs(context, node, expected=2)
    if y.can_be_folded_to_const():
        y = mb.const(val=np.array(y.val, dtype=types.nptype_from_builtin(x.dtype)))
    elif y.dtype != x.dtype:
        y = mb.cast(x=y, dtype=types.builtin_to_string(x.dtype))
    context.add(mb.maximum(x=x, y=y, name=node.name))


class Wrapper(torch.nn.Module):
    def __init__(self, m):
        super().__init__()
        self.m = m

    def forward(self, wav):
        wav = (wav - wav.mean()) / torch.sqrt(wav.var(unbiased=False) + 1e-5)  # F.layer_norm over the waveform
        x = self.m.extract_features(wav, padding_mask=None)["x"]
        return torch.softmax(self.m.proj(x.mean(dim=1)), dim=-1)


def load_wav(path):
    with wave.open(path) as f:
        return np.frombuffer(f.readframes(f.getnframes()), np.int16).astype(np.float32) / 32768


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out", help="output .mlmodelc directory")
    ap.add_argument("--seconds", type=float, default=3.0, help="fixed window length")
    args = ap.parse_args()
    n = int(args.seconds * SR)

    weights = snapshot_download("emotion2vec/emotion2vec_plus_base", allow_patterns=["model.pt", "config.yaml", "tokens.txt", "configuration.json", "example/*"])
    model = AutoModel(model=weights, disable_update=True, device="cpu").model.eval()
    labels = [l.split()[0].split("/")[-1] for l in open(os.path.join(weights, "tokens.txt")) if l.strip()]
    w = Wrapper(model).eval()

    with torch.no_grad():
        w(torch.zeros(1, n))  # FunASR builds its alibi bias lazily; prime it so the trace is stable
        traced = torch.jit.trace(w, torch.randn(1, n))
    ml = ct.convert(
        traced,
        inputs=[ct.TensorType(name="waveform", shape=(1, n), dtype=np.float32)],
        outputs=[ct.TensorType(name="probs", dtype=np.float32)],
        convert_to="mlprogram",
        minimum_deployment_target=ct.target.macOS14,
        compute_precision=ct.precision.FLOAT16,
        compute_units=ct.ComputeUnit.CPU_AND_GPU,
    )

    # parity check on the FunASR example clip
    x = np.zeros((1, n), np.float32)
    clip = load_wav(os.path.join(weights, "example", "test.wav"))[:n]
    x[0, : len(clip)] = clip
    with torch.no_grad():
        ref = w(torch.from_numpy(x))[0].numpy()
    got = ml.predict({"waveform": x})["probs"][0]
    print(f"pytorch {labels[ref.argmax()]} {ref.max():.3f} | coreml {labels[got.argmax()]} {got.max():.3f} | max|diff| {np.abs(ref - got).max():.4f}")
    if labels[ref.argmax()] != labels[got.argmax()] or np.abs(ref - got).max() > 0.05:
        raise SystemExit("Core ML output does not match PyTorch")

    out = os.path.abspath(args.out)
    with tempfile.TemporaryDirectory() as tmp:
        pkg = os.path.join(tmp, "emotion2vec.mlpackage")
        ml.save(pkg)
        subprocess.run(["xcrun", "coremlcompiler", "compile", pkg, tmp], check=True)
        shutil.rmtree(out, ignore_errors=True)
        shutil.move(os.path.join(tmp, "emotion2vec.mlmodelc"), out)
    print("wrote", out)


if __name__ == "__main__":
    main()
