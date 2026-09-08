"""Build generation job lists from scenes.json.

  uv run scripts/make_jobs.py t2v   -> jobs_scenes_t2v.json  (one reference clip per scene)
  uv run scripts/make_jobs.py i2v   -> jobs_scenes_i2v.json  (motion clips from each reference clip's first frame)
  uv run scripts/make_jobs.py vace [N] -> jobs_vace.json     (N control clips per scene through VACE, default 1)

The i2v step reads media/clips/<scene>_ref.mp4, saves frame 0 as
media/refs/<scene>.png and writes one job per motion prompt of the scene's
emotion. Every job carries `scene` and `background` so build_pairs.py can
render the conditioning with the scene color.
"""

import json
import sys
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parent.parent
SCENES = json.loads((ROOT / "scenes.json").read_text())


def prompt_for(scene, action=None):
    text = f"{scene['character']}, {scene['setting']}. "
    text += f"{scene['emotion'].capitalize()} expression. "
    if action:
        text += f"The character {action}. "
    return text + SCENES["framing"]


def t2v_jobs():
    return [{
        "mode": "t2v", "scene": s["id"], "background": s["color"], "seed": 100 + i,
        "out": f"media/clips/{s['id']}_ref.mp4",
        "prompt": prompt_for(s, SCENES["motions"][s["emotion"]][0]),
    } for i, s in enumerate(SCENES["scenes"])]


def i2v_jobs():
    jobs = []
    (ROOT / "media" / "refs").mkdir(parents=True, exist_ok=True)
    for i, s in enumerate(SCENES["scenes"]):
        ref_clip = ROOT / "media" / "clips" / f"{s['id']}_ref.mp4"
        if not ref_clip.exists():
            print(f"skip {s['id']}: no reference clip", file=sys.stderr)
            continue
        cap = cv2.VideoCapture(str(ref_clip))
        ok, frame = cap.read()
        cap.release()
        if not ok:
            print(f"skip {s['id']}: cannot read reference clip", file=sys.stderr)
            continue
        ref_png = ROOT / "media" / "refs" / f"{s['id']}.png"
        cv2.imwrite(str(ref_png), frame)
        for k, action in enumerate(SCENES["motions"][s["emotion"]]):
            jobs.append({
                "mode": "i2v", "scene": s["id"], "background": s["color"], "seed": 1000 + 10 * i + k,
                "image": str(ref_png.relative_to(ROOT)),
                "out": f"media/clips/{s['id']}_{k:02d}.mp4",
                "prompt": prompt_for(s, action),
            })
    return jobs


def vace_jobs(per_scene=1):
    """Skeleton-driven clips: each scene's reference image + an OpenPose control
    clip (media/control_dw). The landmarks for the pairs are the MediaPipe
    landmarks of the same source frames (media/control/<clip>.landmarks.jsonl)."""
    controls = sorted((ROOT / "media" / "control_dw").glob("*.mp4"))
    if not controls:
        print("no OpenPose control clips in media/control_dw (run scripts/box/driving_to_control.sh)", file=sys.stderr)
        return []
    fallback = ROOT / "media" / "refs" / "pineapple_mom.png"
    jobs = []
    for i, s in enumerate(SCENES["scenes"]):
        ref = ROOT / "media" / "refs" / f"{s['id']}.png"
        if not ref.exists():
            ref = fallback
        for k in range(per_scene):
            control = controls[(i * per_scene + k) % len(controls)]
            jobs.append({
                "scene": s["id"], "background": s["color"], "seed": 2000 + 10 * i + k,
                "image": str(ref.relative_to(ROOT)),
                "control": str(control.relative_to(ROOT)),
                "landmarks": f"media/control/{control.stem}.landmarks.jsonl",
                "out": f"media/clips_vace/{s['id']}__{control.stem}.mp4",
                "prompt": prompt_for(s),
            })
    return jobs


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "t2v"
    if mode == "vace":
        jobs = vace_jobs(int(sys.argv[2]) if len(sys.argv) > 2 else 1)
    else:
        jobs = t2v_jobs() if mode == "t2v" else i2v_jobs()
    out = ROOT / ("jobs_vace.json" if mode == "vace" else f"jobs_scenes_{mode}.json")
    out.write_text(json.dumps(jobs, indent=1))
    print(f"{out.name}: {len(jobs)} jobs")


if __name__ == "__main__":
    main()
