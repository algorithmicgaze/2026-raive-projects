"""Convert a pix2pix(HD) ONNX to fp16 weights with fp32 input/output.

Figment's ONNX Image Model node binds float32 GPU buffers, so the graph keeps
fp32 tensors at the boundary (`keep_io_types=True`) while weights and compute
run in fp16: half the file, faster WebGPU.

  uv run --with onnxconverter-common scripts/convert_fp16.py IN.onnx OUT.onnx
"""

import sys

import onnx
from onnxconverter_common import float16

src, dst = sys.argv[1], sys.argv[2]
model = onnx.load(src)
model_fp16 = float16.convert_float_to_float16(model, keep_io_types=True)
onnx.save(model_fp16, dst)
print(f"{dst}: {len(model_fp16.SerializeToString()) / 1e6:.0f} MB")
