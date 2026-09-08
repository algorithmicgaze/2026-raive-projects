# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Activate the reviewed mask library and preserve runnable original projects."""

import argparse
import hashlib
import json
from pathlib import Path


def patch_source(source):
    old = """    const [cw, ch] = c.clip.cell;
    const sx = (j % c.clip.cols) * cw;
    const sy = Math.floor(j / c.clip.cols) * ch;"""
    new = """    const [cw, ch] = c.clip.cell;
    // New masks use compact variable-size shelves; older atlases use a grid.
    const rect = c.clip.frameRects?.[j];
    const sx = rect ? rect[0] : (j % c.clip.cols) * cw;
    const sy = rect ? rect[1] : Math.floor(j / c.clip.cols) * ch;"""
    if new in source:
        return source
    if source.count(old) != 1:
        raise ValueError("Cannot locate the expected atlas sampling code")
    return source.replace(old, new)


def prepare(root):
    out = root.resolve() / "output-figment"
    sources = []
    for name in ["highway.fgmt", "highway-hands.fgmt"]:
        project = json.loads((out / name).read_text())
        sources.extend(
            patch_source(t["source"])
            for t in project["types"]
            if t["type"] == "project.highway"
        )
    assert len(sources) == 2 and sources[0] == sources[1], (
        "Project renderers differ; verify each separately"
    )
    target = out / "masked/review/highway-candidate-source.js"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(sources[0])
    print(target)


def run(root):
    root = root.resolve() / "output-figment"
    manifest = json.loads((root / "manifest-masked.json").read_text())
    original = json.loads((root / "manifest.json").read_text())
    assert len(manifest["clips"]) == len(original["clips"])
    assert [(c["id"], c["lane"], c["cars"]) for c in manifest["clips"]] == [
        (c["id"], c["lane"], c["cars"]) for c in original["clips"]
    ]
    for c in manifest["clips"]:
        assert (root / c["sheet"]).is_file(), c["sheet"]
    review = json.loads((root / "masked/review/renderer-verification.json").read_text())
    assert len(review["clips"]) == len({c["sheet"] for c in manifest["clips"]})
    assert review["gridCompatibility"] and review["shelfCompatibility"]
    report = []
    for name in ["highway.fgmt", "highway-hands.fgmt"]:
        p = root / name
        backup = p.with_name(p.stem + "-original-backup.fgmt")
        if not backup.exists():
            backup.write_bytes(p.read_bytes())
        before = json.loads(p.read_text())
        after = json.loads(p.read_text())
        matched = 0
        for t in after["types"]:
            if t["type"] == "project.highway":
                t["source"] = patch_source(t["source"])
                assert (
                    hashlib.sha256(t["source"].encode()).hexdigest()
                    == review["sourceSha256"]
                ), "Embedded renderer must be verified before activation"
                matched += 1
        assert matched == 1
        for node in after["nodes"]:
            if node["type"] == "project.highway":
                node.setdefault("values", {})["manifest"] = {
                    "type": "value",
                    "value": "manifest-masked.json",
                }
        restored = json.loads(json.dumps(after))
        for t, old in zip(restored["types"], before["types"]):
            if t["type"] == "project.highway":
                t["source"] = old["source"]
        for n, old in zip(restored["nodes"], before["nodes"]):
            if n["type"] == "project.highway":
                n["values"] = old.get("values", {})
        assert restored == before, "Unexpected node, setting or connection change"
        temp = p.with_suffix(".tmp")
        temp.write_text(json.dumps(after, indent=1))
        temp.replace(p)
        report.append(
            {
                "project": name,
                "backup": backup.name,
                "backup_sha256": hashlib.sha256(backup.read_bytes()).hexdigest(),
                "updated_sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
                "only_highway_source_and_manifest_changed": True,
            }
        )
    (root / "masked/review/integration-verification.json").write_text(
        json.dumps(report, indent=2)
    )
    print(json.dumps(report))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("root", type=Path, help="Private Cars asset folder")
    ap.add_argument(
        "--prepare",
        action="store_true",
        help="Extract the patched embedded renderer for verification; do not activate",
    )
    args = ap.parse_args()
    (prepare if args.prepare else run)(args.root)
