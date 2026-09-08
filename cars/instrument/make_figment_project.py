# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Assemble a Figment project folder for the highway instrument:

  <out>/highway.fgmt        Highway with sliders, to Out
  <out>/highway-hands.fgmt  webcam -> Detect Hands -> Hand Keys -> Highway -> Out
  <out>/plate.png         clean plate
  <out>/manifest.json     clip manifest (from pack_clips.py)
  <out>/clips/*.png       sprite sheets
  <out>/trains/           train videos, mask.png, trains.json

  uv run instrument/pack_clips.py output-clips output-clips-groups output-figment
  uv run instrument/make_figment_project.py output-figment
"""
import json, shutil, sys
from pathlib import Path

out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
here = Path(__file__).parent
shutil.copy("output-plate-stab/iter3.png", out / "plate.png")
trains_src = Path("output-trains")
if trains_src.exists():
    tdir = out / "trains"; tdir.mkdir(exist_ok=True)
    for f in trains_src.glob("*"):
        if f.suffix in (".mp4", ".png", ".json"):
            shutil.copy(f, tdir / f.name)
source = (here / "figment" / "highway.js").read_text()
hand_source = (here / "figment" / "handKeys.js").read_text()
types = [{"name": "Highway", "type": "project.highway", "source": source},
         {"name": "Hand Keys", "type": "project.handKeys", "source": hand_source}]
highway_values = {
    "manifest": {"type": "value", "value": "manifest-repaired.json" if (out / "manifest-repaired.json").exists() else "manifest.json"},
    "trains": {"type": "value", "value": "trains/trains.json"},
    "plate": {"type": "value", "value": "plate.png"},
}
def v(x): return {"type": "value", "value": x}

# 1. sliders only
project = {
    "version": 6,
    "nodes": [
        {"id": 1, "name": "Highway", "type": "project.highway", "x": 120, "y": 120, "values": {
            **highway_values, "lane 0": v(0.5), "lane 1": v(0.5), "lane 2": v(0.4), "lane 3": v(0.4), "lane 4": v(0.4)}},
        {"id": 2, "name": "Out", "type": "core.out", "x": 120, "y": 300},
    ],
    "connections": [{"outNode": 1, "outPort": "out", "inNode": 2, "inPort": "in"}],
    "settings": {},
    "types": types,
}
(out / "highway.fgmt").write_text(json.dumps(project, indent=1))

# 2. webcam -> detect hands -> hand keys -> highway -> out
hands = {
    "version": 6,
    "nodes": [
        {"id": 1, "name": "Webcam Image", "type": "image.webcamImage", "x": 120, "y": 40},
        {"id": 2, "name": "Detect Hands", "type": "ml.detectHands", "x": 120, "y": 120, "values": {"smoothing": v(0.6)}},
        {"id": 3, "name": "Hand Keys", "type": "project.handKeys", "x": 120, "y": 200},
        {"id": 4, "name": "Highway", "type": "project.highway", "x": 120, "y": 300, "values": highway_values},
        {"id": 5, "name": "Out", "type": "core.out", "x": 120, "y": 420},
        # keys drawn over the webcam: select this node to see what you play
        {"id": 6, "name": "Keys View", "type": "image.composite", "x": 360, "y": 300,
         "values": {"factor": v(1), "operation": v("lighten")}},
    ],
    "connections": [
        {"outNode": 1, "outPort": "image", "inNode": 2, "inPort": "in"},
        {"outNode": 2, "outPort": "landmarks", "inNode": 3, "inPort": "landmarks"},
        {"outNode": 2, "outPort": "out", "inNode": 3, "inPort": "in"},
        {"outNode": 2, "outPort": "out", "inNode": 6, "inPort": "image 1"},
        {"outNode": 3, "outPort": "out", "inNode": 6, "inPort": "image 2"},
        *[{"outNode": 3, "outPort": f"lane {k}", "inNode": 4, "inPort": f"lane {k}"} for k in range(5)],
        {"outNode": 4, "outPort": "out", "inNode": 5, "inPort": "in"},
    ],
    "settings": {},
    "types": types,
}
(out / "highway-hands.fgmt").write_text(json.dumps(hands, indent=1))
n = len(json.loads((out / "manifest.json").read_text())["clips"]) if (out / "manifest.json").exists() else 0
print(f"project at {out}: {n} clips, trains: {len(list((out / 'trains').glob('*.mp4')))}; highway.fgmt and highway-hands.fgmt")
