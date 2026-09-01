# SPEC: Wan video models for fruit-drama data generation

Two open models, both Apache-2.0, both run on one 24 GB GPU. Together they
produce the training pairs for the realtime pix2pix models.

| Role | Model | Control | Output |
| --- | --- | --- | --- |
| Prompt-controlled | `yetter-ai/Wan2.2-TI2V-5B-Turbo-Diffusers` | text, or text + first frame | 768×1280, 121 frames, 24 fps |
| Skeleton-controlled | `Wan-AI/Wan2.1-VACE-1.3B-diffusers` | skeleton video + reference image + text | 480×832, 81 frames, 16 fps |

Prompt-controlled gives new scenes and characters. Skeleton-controlled gives
exact pose pairs. Use both: the prompt model makes the reference image of a
character, the skeleton model animates that character along a human
performance.

## What to download

Run on the box, in this directory, after `uv sync`:

```bash
# 1. Prompt-controlled. ~22 GB. transformer 5B bf16 + umt5-xxl text encoder + VAE.
HF_HUB_DISABLE_XET=1 uvx --from huggingface_hub hf download yetter-ai/Wan2.2-TI2V-5B-Turbo-Diffusers

# 2. Skeleton-controlled. ~3.5 GB without the text encoder (shared with 1).
HF_HUB_DISABLE_XET=1 uvx --from huggingface_hub hf download Wan-AI/Wan2.1-VACE-1.3B-diffusers --exclude "text_encoder/*"

# 3. MediaPipe task files (35 MB).
mkdir -p media/models && cd media/models
curl -sSLO https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_heavy/float16/latest/pose_landmarker_heavy.task
curl -sSLO https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/latest/face_landmarker.task
```

Notes:
- `HF_HUB_DISABLE_XET=1` matters. On slow links the Xet chunk protocol stalls
  at 0 B/s. Plain HTTPS works.
- The Turbo model is the base Wan 2.2 TI2V-5B distilled to 4 steps, no CFG.
  Same weights layout as `Wan-AI/Wan2.2-TI2V-5B-Diffusers`; 10× faster.
- Both models use the same umt5-xxl text encoder (11 GB). `generate_vace.py`
  loads it from the Turbo snapshot, so VACE needs no second copy.
- Do not download `Wan2.2-I2V-A14B` or `Wan2.1-VACE-14B`. They need more than
  24 GB or heavy offloading. The 5B and 1.3B are the right size.

## Model 1: prompt-controlled (Wan 2.2 TI2V-5B Turbo)

- Script: `scripts/generate_clips.py`. Modes `t2v`, `i2v`, `batch jobs.json`.
- Settings: `num_inference_steps=4`, `guidance_scale=1.0`,
  `UniPCMultistepScheduler(flow_shift=5.0)`, bf16, `enable_model_cpu_offload`
  (fits 24 GB with room), VAE tiling on.
- Resolution: multiples of 32. We use **768×1280** portrait: near 9:16 and it
  resizes cleanly to the 512×768 training size (see `STRATEGY.md`).
- Frames: 121 at 24 fps = 5 s. Fewer frames run faster; keep 4k+1.
- Prompts: `scenes.json` is the single source. `make_jobs.py t2v` writes one
  reference clip per scene; `make_jobs.py i2v` takes each reference clip's
  first frame and writes four motion clips per scene. Character identity stays
  fixed inside a scene because every motion clip starts from the same frame.
- Prompt rules that matter for detection later: one character, standing, full
  body visible, facing the camera, medium-wide shot, no other people. Describe
  the character by appearance, not by name.

## Model 2: skeleton-controlled (Wan 2.1 VACE 1.3B)

- Script: `scripts/generate_vace.py`. Inputs per job: `control` (skeleton
  video), `image` (reference image of the character), `prompt`, `landmarks`
  (the landmarks used to draw the control video, for exact pairing).
- Pipeline class: `diffusers.WanVACEPipeline`. Settings: 480×832 portrait,
  81 frames, 16 fps, `flow_shift=3.0`, `guidance_scale=5.0`, 30 steps,
  `conditioning_scale=1.0`, bf16 with cpu offload. About 2–3 min per clip on
  a 4090.
- Control video: white skeleton + face contours on black, drawn by
  `render_conditioning.render_landmarks`. VACE was trained with OpenPose-style
  pose videos; our MediaPipe drawing is close enough to test first. If the
  model ignores it, render OpenPose colors from the same landmarks.
- Reference image: the character. Use the first frame of the scene's
  reference clip from Model 1 (`media/refs/<scene>.png`).

### Where the skeletons come from

Human videos. Detection on fruit footage fails (tested: 37% of frames had a
pose, and those skeletons were fragments). MediaPipe on a person is near
perfect.

1. Put videos in `media/driving/`: one person, full body, facing the camera,
   telenovela gestures. Any fps, 10–60 s each.
2. `bash scripts/box/driving_to_control.sh` → landmarks per frame
   (`media/driving_lm/`) and 81-frame control clips (`media/control/`).
   Detection gaps ≤ 6 frames are interpolated; runs of 41–80 frames are
   extended by ping-pong.
3. `uv run scripts/make_jobs.py vace 2` → `jobs_vace.json` (2 control clips
   per scene).
4. `uv run scripts/generate_vace.py batch jobs_vace.json`.
5. `uv run scripts/build_pairs.py media/dataset_vace jobs_vace.json` → pairs
   drawn from the stored landmarks. No detection on the output.

## From clips to training pairs

`scripts/build_pairs.py` reads job files, finds the clips, and writes
`[target | conditioning]` pairs at 512×768 per half:

- Model 1 clips: detect pose + face on each frame (`num_poses=1`,
  `num_faces=1`), skip frames without a pose.
- Model 2 clips: use the landmarks that drove the clip. Every frame is a pair.
- Conditioning background = the scene color from `scenes.json`. Same color in
  Figment's Detect Pose / Detect Faces `background` parameter at inference.

Then `scripts/train_pix2pix.py` (U-Net, 30 fps in Figment) or
`scripts/train_pix2pixhd.py` (sharper, ~8× heavier) on the `pairs/` folder.

## Hardware and time

- One 24 GB GPU is enough for both models with cpu offload. 62 GB RAM helps
  offload; 32 GB works.
- Disk: 22 GB + 3.5 GB models, plus ~1 GB per 10 clips.
- Time per clip on a 4090: Model 1 about 1–2 min at 768×1280×121 (4 steps);
  Model 2 about 2–3 min at 480×832×81 (30 steps).
- A 12-scene run (12 reference + 48 motion clips) is about 1.5–2 h.

## Unattended run on a fresh box

```bash
git clone https://github.com/algorithmicgaze/2026-raive-projects.git
cd 2026-raive-projects/fruit-drama
uv sync
# downloads from "What to download" above
bash scripts/box/restart_waiters.sh   # waits for the model, then generates, then trains
```

Logs: `media/generate_when_ready.log`, `media/pipeline_after_generation.log`.
After a network drop or reboot: `bash scripts/box/recover.sh`.
