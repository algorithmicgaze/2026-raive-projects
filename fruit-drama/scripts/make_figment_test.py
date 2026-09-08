"""Write Figment test projects that run an ONNX model on a control clip.

Each project: Load Movie (control clip) -> Resize 512x768 -> ONNX Image Model
Sync (custom node, source from figment/onnxImageModelSync.js) -> Out.
Headless render: `Figment --render <project>.fgmt -o out/f-####.png --frames 81`.

  uv run scripts/make_figment_test.py media/figment control_h264.mp4 unet=unet_fp32.onnx hd16=hd_fp16.onnx
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NODE_SOURCE = (ROOT / "figment" / "onnxImageModelSync.js").read_text()
TYPE = {"name": "ONNX Image Model Sync", "type": "project.onnxImageModelSync", "source": NODE_SOURCE}


def v(x):
    return {"type": "value", "value": x}


def project(movie, model, width=512, height=768):
    nodes = [
        {"id": 1, "name": "Load Movie", "type": "image.loadMovie", "x": 100, "y": 100,
         "values": {"file": v(movie), "quality": v("accurate")}},
        {"id": 2, "name": "Resize", "type": "image.resize", "x": 300, "y": 100,
         "values": {"width": v(width), "height": v(height), "fit": v("fill")}},
        {"id": 3, "name": "ONNX Image Model Sync", "type": TYPE["type"], "x": 500, "y": 100,
         "values": {"model": v(model)}},
        {"id": 4, "name": "Out", "type": "core.out", "x": 700, "y": 100, "values": {}},
    ]
    connections = [
        {"outNode": 1, "outPort": "out", "inNode": 2, "inPort": "in"},
        {"outNode": 2, "outPort": "out", "inNode": 3, "inPort": "in"},
        {"outNode": 3, "outPort": "out", "inNode": 4, "inPort": "in"},
    ]
    return {"version": 6, "types": [TYPE], "nodes": nodes, "connections": connections}


def main():
    out_dir, movie, *specs = sys.argv[1:]
    out_dir = Path(out_dir)
    for spec in specs:
        name, model = spec.split("=")
        (out_dir / f"{name}.fgmt").write_text(json.dumps(project(movie, model), indent=1))
        print(out_dir / f"{name}.fgmt", "->", model)


if __name__ == "__main__":
    main()
