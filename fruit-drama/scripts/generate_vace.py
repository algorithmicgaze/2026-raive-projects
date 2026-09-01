"""Pose-controlled generation with Wan 2.1 VACE 1.3B.

Input: a control video (our skeleton render), a reference image of the
character, a prompt. Output: a clip whose motion follows the skeleton frame
by frame. Pairs built from it need no detection: the landmarks are known.

  uv run scripts/generate_vace.py --control media/control/seg_000.mp4 --image media/refs/pineapple_hallway.png \
      --prompt "..." --out media/clips_vace/pineapple_hallway_seg000.mp4
  uv run scripts/generate_vace.py batch jobs_vace.json

Defaults follow the VACE 1.3B recipe: 480x832 (here portrait 480 wide, 832
tall), 81 frames, 16 fps, flow_shift 3.0, guidance 5.0. The umt5 text encoder
is loaded from the already downloaded Wan 2.2 Turbo snapshot.
"""

import argparse
import json
import time
from pathlib import Path

import cv2
import torch
from diffusers import AutoencoderKLWan, UniPCMultistepScheduler, WanVACEPipeline
from diffusers.utils import export_to_video
from huggingface_hub import snapshot_download
from PIL import Image
from transformers import AutoTokenizer, UMT5EncoderModel

MODEL = "Wan-AI/Wan2.1-VACE-1.3B-diffusers"
TEXT_ENCODER_REPO = "yetter-ai/Wan2.2-TI2V-5B-Turbo-Diffusers"
STYLE = ", 3D animated, Pixar style, glossy skin, expressive face, cinematic lighting, high detail"
NEGATIVE = "blurry, low quality, text, watermark, deformed, extra limbs, extra people, static"

_pipe = None


def get_pipe(offload):
    global _pipe
    if _pipe is not None:
        return _pipe
    te_path = snapshot_download(TEXT_ENCODER_REPO, allow_patterns=["text_encoder/*", "tokenizer/*"])
    text_encoder = UMT5EncoderModel.from_pretrained(te_path, subfolder="text_encoder", torch_dtype=torch.bfloat16)
    tokenizer = AutoTokenizer.from_pretrained(te_path, subfolder="tokenizer")
    vae = AutoencoderKLWan.from_pretrained(MODEL, subfolder="vae", torch_dtype=torch.float32)
    pipe = WanVACEPipeline.from_pretrained(MODEL, vae=vae, text_encoder=text_encoder, tokenizer=tokenizer,
                                           torch_dtype=torch.bfloat16)
    pipe.scheduler = UniPCMultistepScheduler.from_config(pipe.scheduler.config, flow_shift=3.0)
    if offload:
        pipe.enable_model_cpu_offload()
    else:
        pipe.to("cuda")
    _pipe = pipe
    return pipe


def read_frames(path, width, height, num_frames):
    cap = cv2.VideoCapture(str(path))
    frames = []
    while len(frames) < num_frames:
        ok, bgr = cap.read()
        if not ok:
            break
        frames.append(Image.fromarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)).resize((width, height), Image.BILINEAR))
    cap.release()
    if len(frames) < num_frames:
        raise SystemExit(f"{path}: {len(frames)} frames, need {num_frames}")
    return frames


def fit_image(path, width, height):
    im = Image.open(path).convert("RGB")
    scale = max(width / im.width, height / im.height)
    im = im.resize((round(im.width * scale), round(im.height * scale)), Image.LANCZOS)
    left, top = (im.width - width) // 2, (im.height - height) // 2
    return im.crop((left, top, left + width, top + height))


def run_job(job, offload):
    width, height = job.get("width", 480), job.get("height", 832)
    frames, steps = job.get("frames", 81), job.get("steps", 30)
    out = Path(job["out"])
    out.parent.mkdir(parents=True, exist_ok=True)
    pipe = get_pipe(offload)
    control = read_frames(job["control"], width, height, frames)
    kwargs = dict(
        prompt=job["prompt"] + STYLE, negative_prompt=NEGATIVE,
        video=control, conditioning_scale=job.get("conditioning_scale", 1.0),
        height=height, width=width, num_frames=frames,
        num_inference_steps=steps, guidance_scale=job.get("guidance", 5.0),
        generator=torch.Generator(device="cuda").manual_seed(job.get("seed", 0)),
    )
    if job.get("image"):
        kwargs["reference_images"] = [fit_image(job["image"], width, height)]
    t0 = time.time()
    with torch.inference_mode():
        video = pipe(**kwargs).frames[0]
    export_to_video(video, str(out), fps=16)
    meta = dict(job, seconds=round(time.time() - t0, 1), model=MODEL)
    out.with_suffix(".json").write_text(json.dumps(meta, indent=2))
    print(f"{out}  {meta['seconds']}s")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mode", nargs="?", default="single", choices=["single", "batch"])
    ap.add_argument("jobs", nargs="?")
    ap.add_argument("--control")
    ap.add_argument("--image")
    ap.add_argument("--prompt")
    ap.add_argument("--out")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--steps", type=int, default=30)
    ap.add_argument("--no-offload", action="store_true")
    args = ap.parse_args()
    if args.mode == "batch":
        jobs = json.loads(Path(args.jobs).read_text())
    else:
        jobs = [dict(control=args.control, image=args.image, prompt=args.prompt, out=args.out, seed=args.seed, steps=args.steps)]
    for job in jobs:
        run_job(job, offload=not args.no_offload)


if __name__ == "__main__":
    main()
