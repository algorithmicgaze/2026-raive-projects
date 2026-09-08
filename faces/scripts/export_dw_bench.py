"""Throwaway ONNX pair for the depthwise micro-benchmark (plan section 5).

Both models share the same skeleton: image in, average-pool to 256, 1x1 to
64 channels, two convs at 256 (64 ch), bilinear 2x, 1x1 to 32, two convs at
512 (32 ch), 1x1 to RGB. `dense.onnx` uses plain 3x3 convs, `dw.onnx` a
depthwise 3x3 followed by a 1x1 for each of them. Random weights; only the
Figment timing matters. Shapes follow variant V3's top two levels.

  uv run scripts/export_dw_bench.py output-exp/dwbench
"""

import os
import sys

import torch
import torch.nn as nn
import torch.nn.functional as F


def block(c, depthwise):
    if depthwise:
        return nn.Sequential(nn.Conv2d(c, c, 3, padding=1, groups=c, bias=False), nn.Conv2d(c, c, 1), nn.LeakyReLU(0.2))
    return nn.Sequential(nn.Conv2d(c, c, 3, padding=1), nn.LeakyReLU(0.2))


class Bench(nn.Module):
    def __init__(self, depthwise):
        super().__init__()
        self.in256 = nn.Conv2d(3, 64, 1)
        self.l256 = nn.Sequential(block(64, depthwise), block(64, depthwise))
        self.in512 = nn.Conv2d(64, 32, 1)
        self.l512 = nn.Sequential(block(32, depthwise), block(32, depthwise))
        self.out = nn.Conv2d(32, 3, 1)

    def forward(self, x):
        x = self.in256(F.avg_pool2d(x, 2))
        x = self.l256(x)
        x = F.interpolate(x, scale_factor=2, mode="bilinear", align_corners=False)
        x = self.l512(self.in512(x))
        return torch.tanh(self.out(x))


def main():
    out_dir = sys.argv[1]
    os.makedirs(out_dir, exist_ok=True)
    dummy = torch.randn(1, 3, 512, 512)
    for name, depthwise in (("dense", False), ("dw", True)):
        model = Bench(depthwise).eval()
        path = os.path.join(out_dir, f"{name}.onnx")
        torch.onnx.export(model, dummy, path, opset_version=17, do_constant_folding=True,
                          input_names=["input"], output_names=["output"], dynamo=False)
        macs = sum(p.numel() for p in model.parameters())
        print(f"{path}: {macs / 1e3:.0f}k params")


if __name__ == "__main__":
    main()
