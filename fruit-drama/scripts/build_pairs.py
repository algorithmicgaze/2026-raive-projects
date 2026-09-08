"""Render training pairs for every generated clip listed in one or more job files.

Each job's `scene` becomes the file prefix and its `background` becomes the
conditioning background color. Clips that do not exist yet are skipped.

  uv run scripts/build_pairs.py media/dataset_scenes jobs_scenes_i2v.json jobs_pineapple_i2v.json
"""

import argparse
import json
from pathlib import Path

from render_conditioning import make_detectors, process, process_with_landmarks


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out", type=Path)
    ap.add_argument("jobs", nargs="+", type=Path)
    ap.add_argument("--size", default="512x768")
    ap.add_argument("--keep-empty", action="store_true", help="also write frames without a pose")
    args = ap.parse_args()

    size = tuple(int(v) for v in args.size.split("x"))
    detectors = make_detectors(num_poses=1, num_faces=1)
    summary = []
    for jobs_file in args.jobs:
        for job in json.loads(jobs_file.read_text()):
            clip = Path(job["out"])
            if not clip.exists():
                continue
            scene = job.get("scene", clip.stem)
            kwargs = dict(size=size, background=job.get("background", "#000000"), prefix=f"{scene}__{clip.stem}__")
            if job.get("landmarks"):
                stats = process_with_landmarks(clip, args.out, job["landmarks"], **kwargs)
            else:
                stats = process(clip, args.out, skip_empty=not args.keep_empty, detectors=detectors, **kwargs)
            stats["scene"] = scene
            summary.append(stats)
            print(f"{clip.name}: {stats['written']}/{stats['frames']} pairs, face in {stats.get('with_face', '-')}")

    (args.out / "summary.json").write_text(json.dumps(summary, indent=2))
    total = sum(s["written"] for s in summary)
    print(f"{len(summary)} clips, {total} pairs -> {args.out / 'pairs'}")


if __name__ == "__main__":
    main()
