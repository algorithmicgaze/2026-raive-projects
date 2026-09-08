# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Write piano-roll.fgmt with piano-roll.js embedded as the project's node type.

  uv run piano-roll/make_project.py
"""
import json
from pathlib import Path

here = Path(__file__).parent
source = (here / "piano-roll.js").read_text()
project = {
    "version": 6,
    "nodes": [
        {"id": 1, "name": "Piano Roll", "type": "project.pianoRoll", "x": 120, "y": 120, "values": {
            "section 1": {"type": "value", "value": 0.8},
            "section 2": {"type": "value", "value": 0.0},
            "section 3": {"type": "value", "value": 0.5},
            "section 4": {"type": "value", "value": 0.0},
            "section 5": {"type": "value", "value": 1.0},
        }},
        {"id": 2, "name": "Out", "type": "core.out", "x": 120, "y": 300},
    ],
    "connections": [{"outNode": 1, "outPort": "out", "inNode": 2, "inPort": "in"}],
    "settings": {"oscEnabled": False, "oscPort": 8000},
    "types": [{"name": "Piano Roll", "type": "project.pianoRoll", "source": source}],
}
(here / "piano-roll.fgmt").write_text(json.dumps(project, indent=1))
print("wrote", here / "piano-roll.fgmt")
