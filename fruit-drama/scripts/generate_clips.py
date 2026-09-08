"""Generate fruit-drama clips with Wan 2.2 TI2V-5B Turbo (4 steps).

Two modes:
  t2v   text → video
  i2v   reference image + text → video (keeps character identity)

Single job:
  uv run scripts/generate_clips.py t2v --prompt "..." --out media/clips/a.mp4
  uv run scripts/generate_clips.py i2v --image ref.png --prompt "..." --out media/clips/b.mp4

Batch (one model load for many clips):
  uv run scripts/generate_clips.py batch jobs.json
  jobs.json = [{"mode": "i2v", "image": "...", "prompt": "...", "out": "...", "seed": 1}, ...]

Memory: all prompts are encoded first, then the 11 GB text encoder is freed.
Transformer and VAE then run on the GPU without CPU offload. Needs about
12 GB of VRAM and 12 GB of RAM.
"""

import argparse
import gc
import json
import time
from pathlib import Path

import torch
from diffusers import UniPCMultistepScheduler, WanImageToVideoPipeline, WanPipeline
from diffusers.utils import export_to_video
from PIL import Image
from transformers import AutoTokenizer, UMT5EncoderModel

MODEL = "yetter-ai/Wan2.2-TI2V-5B-Turbo-Diffusers"
STYLE = (
    ", 3D animated, Pixar style, glossy skin, expressive face, cinematic lighting, "
    "shallow depth of field, high detail"
)
NEGATIVE = "blurry, low quality, text, watermark, deformed, extra limbs, static, jitter"
MAX_SEQ = 512

_pipe = None


def full_prompt(job):
    return job["prompt"] + (STYLE if job.get("style", True) else "")


def encode_prompts(texts):
    """Prompt text -> [1, 512, 4096] embedding on the GPU. Same recipe as WanPipeline."""
    tokenizer = AutoTokenizer.from_pretrained(MODEL, subfolder="tokenizer")
    encoder = UMT5EncoderModel.from_pretrained(MODEL, subfolder="text_encoder", torch_dtype=torch.bfloat16).to("cuda")
    embeds = {}
    with torch.inference_mode():
        for text in set(texts):
            tok = tokenizer(text, padding="max_length", max_length=MAX_SEQ, truncation=True,
                            add_special_tokens=True, return_attention_mask=True, return_tensors="pt")
            hidden = encoder(tok.input_ids.to("cuda"), tok.attention_mask.to("cuda")).last_hidden_state[0]
            n = int(tok.attention_mask.sum())
            embeds[text] = torch.cat([hidden[:n], hidden.new_zeros(MAX_SEQ - n, hidden.shape[-1])])[None]
    del encoder
    gc.collect()
    torch.cuda.empty_cache()
    return embeds


def get_pipe(mode):
    """One pipeline on the GPU at a time; a mode switch reloads (~10 s)."""
    global _pipe
    if _pipe is not None and _pipe[0] == mode:
        return _pipe[1]
    _pipe = None
    gc.collect()
    torch.cuda.empty_cache()
    cls = WanImageToVideoPipeline if mode == "i2v" else WanPipeline
    pipe = cls.from_pretrained(MODEL, text_encoder=None, tokenizer=None, torch_dtype=torch.bfloat16)
    pipe.scheduler = UniPCMultistepScheduler.from_config(pipe.scheduler.config, flow_shift=5.0)
    pipe.to("cuda")
    pipe.vae.enable_tiling()
    _pipe = (mode, pipe)
    return pipe


def fit_image(path, width, height):
    """Resize + center-crop the reference image to the target aspect ratio."""
    im = Image.open(path).convert("RGB")
    scale = max(width / im.width, height / im.height)
    im = im.resize((round(im.width * scale), round(im.height * scale)), Image.LANCZOS)
    left, top = (im.width - width) // 2, (im.height - height) // 2
    return im.crop((left, top, left + width, top + height))


def run_job(job, embeds):
    mode = job.get("mode", "t2v")
    width, height = job.get("width", 704), job.get("height", 1280)
    frames, steps, seed = job.get("frames", 121), job.get("steps", 4), job.get("seed", 0)
    prompt = full_prompt(job)
    out = Path(job["out"])
    out.parent.mkdir(parents=True, exist_ok=True)

    pipe = get_pipe(mode)
    kwargs = dict(
        prompt_embeds=embeds[prompt],
        negative_prompt_embeds=embeds[NEGATIVE],
        guidance_scale=1.0,
        num_inference_steps=steps,
        width=width,
        height=height,
        num_frames=frames,
        generator=torch.Generator(device="cuda").manual_seed(seed),
    )
    if mode == "i2v":
        kwargs["image"] = fit_image(job["image"], width, height)

    t0 = time.time()
    with torch.inference_mode():
        video = pipe(**kwargs).frames[0]
    export_to_video(video, str(out), fps=24)
    meta = dict(job, prompt_full=prompt, seconds=round(time.time() - t0, 1), model=MODEL)
    out.with_suffix(".json").write_text(json.dumps(meta, indent=2))
    print(f"{out}  {meta['seconds']}s", flush=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mode", choices=["t2v", "i2v", "batch"])
    ap.add_argument("jobs", nargs="?", help="jobs.json for batch mode")
    ap.add_argument("--prompt")
    ap.add_argument("--image")
    ap.add_argument("--out")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--width", type=int, default=704)
    ap.add_argument("--height", type=int, default=1280)
    ap.add_argument("--frames", type=int, default=121)
    ap.add_argument("--steps", type=int, default=4)
    ap.add_argument("--skip-existing", action="store_true", help="skip jobs whose output exists")
    args = ap.parse_args()

    if args.mode == "batch":
        jobs = json.loads(Path(args.jobs).read_text())
    else:
        jobs = [dict(mode=args.mode, prompt=args.prompt, image=args.image, out=args.out, seed=args.seed,
                     width=args.width, height=args.height, frames=args.frames, steps=args.steps)]
    if args.skip_existing:
        jobs = [j for j in jobs if not Path(j["out"]).exists()]
    if not jobs:
        print("nothing to do")
        return
    embeds = encode_prompts([full_prompt(j) for j in jobs] + [NEGATIVE])
    for job in jobs:
        run_job(job, embeds)


if __name__ == "__main__":
    main()
