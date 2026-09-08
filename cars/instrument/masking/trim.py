# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Apply reviewed playback ranges without deleting any atlas pixels.

Overrides map atlas IDs to inclusive source-window frame ranges and a reason:
{"lane1_example": {"start": 80, "end": 300, "reason": "Occluded approach"}}
"""

import argparse
import json
from pathlib import Path


def run(root, overrides):
    out = root.resolve() / "output-figment"
    rules = json.loads(overrides.read_text())
    original = json.loads((out / "manifest.json").read_text())
    for c in original["clips"]:
        job = json.loads(
            (out / "masked/jobs" / (Path(c["sheet"]).stem + ".json")).read_text()
        )
        assert job["version"] == 4, "Finish the full build before trimming"
    backup = out / "masked/untrimmed-jobs"
    backup.mkdir(exist_ok=True)
    report = []
    for jid, rule in rules.items():
        p = out / "masked/jobs" / f"{jid}.json"
        saved = backup / p.name
        current = json.loads(p.read_text())
        if (
            not saved.exists()
            or json.loads(saved.read_text())["sha256"] != current["sha256"]
        ):
            saved.write_bytes(p.read_bytes())
        job = json.loads(saved.read_text())
        assert job["version"] == 4
        samples = job["source_sample_frames"]
        keep = [
            i
            for i, f in enumerate(samples)
            if rule.get("start", samples[0]) <= f <= rule.get("end", samples[-1])
        ]
        assert len(keep) >= 2, jid
        lo, hi = keep[0], keep[-1] + 1
        c = job["clip"]
        c["frameRects"] = c["frameRects"][lo:hi]
        c["boxes"] = c["boxes"][lo * 2 : hi * 2]
        c["sourceFrameOffset"] = samples[lo]
        job["source_sample_frames"] = samples[lo:hi]
        job["metrics"] = job["metrics"][lo:hi]
        job["review_trim"] = {
            **rule,
            "original_samples": len(samples),
            "retained_samples": hi - lo,
        }
        temp = p.with_suffix(".tmp")
        temp.write_text(json.dumps(job, indent=2))
        temp.replace(p)
        report.append({"id": jid, **job["review_trim"]})
    # Rebuild from the original entry order and retain each occupancy variant.
    clips = []
    for c in original["clips"]:
        job = json.loads(
            (out / "masked/jobs" / (Path(c["sheet"]).stem + ".json")).read_text()
        )
        assert job["version"] == 4
        clips.append(
            {**job["clip"], "id": c["id"], "lane": c["lane"], "cars": c["cars"]}
        )
    target = out / "manifest-masked.json"
    temp = target.with_suffix(".tmp")
    temp.write_text(
        json.dumps({**original, "maskVersion": 4, "clips": clips}, indent=2)
    )
    temp.replace(target)
    (out / "masked/review/trim-verification.json").write_text(
        json.dumps(report, indent=2)
    )
    print(json.dumps(report))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("root", type=Path)
    ap.add_argument("overrides", type=Path)
    args = ap.parse_args()
    run(args.root, args.overrides)
