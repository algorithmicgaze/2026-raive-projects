# SPEC: Wan video models for fruit-drama data generation

Two open models, both Apache-2.0, both run on one 24 GB GPU. Together they
produce the training pairs for the realtime pix2pix models.

| Role | Model | Control | Output |
| --- | --- | --- | --- |
| Prompt-controlled | `yetter-ai/Wan2.2-TI2V-5B-Turbo-Diffusers` | text, or text + first frame | 704×1280, 121 frames, 24 fps |
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
- `HF_HUB_DISABLE_XET=1` matters on the Tailscale box. On slow links the Xet
  chunk protocol stalls at 0 B/s. Plain HTTPS works. On the RunPod box the
  link is fast and Xet + `hf_transfer` download both models in minutes
  (`scripts/box/runpod_setup.sh`).
- The Turbo model is the base Wan 2.2 TI2V-5B distilled to 4 steps, no CFG.
  Same weights layout as `Wan-AI/Wan2.2-TI2V-5B-Diffusers`; 10× faster.
- Both models use the same umt5-xxl text encoder (11 GB). `generate_vace.py`
  loads it from the Turbo snapshot, so VACE needs no second copy.
- Do not download `Wan2.2-I2V-A14B` or `Wan2.1-VACE-14B`. They need more than
  24 GB or heavy offloading. The 5B and 1.3B are the right size.

## Model 1: prompt-controlled (Wan 2.2 TI2V-5B Turbo)

- Script: `scripts/generate_clips.py`. Modes `t2v`, `i2v`, `batch jobs.json`.
- Settings: `num_inference_steps=4`, `guidance_scale=1.0`,
  `UniPCMultistepScheduler(flow_shift=5.0)`, bf16, VAE tiling on.
- Memory: the script encodes every prompt of the batch first, frees the 11 GB
  umt5-xxl, then loads transformer + VAE on the GPU with no CPU offload.
  Peak 20 GB VRAM, ~1.5 GB RSS. With `enable_model_cpu_offload` the text
  encoder and transformer stay in RAM (23 GB + page cache) and a 31 GB
  container gets OOM-killed on the second clip.
- Resolution: **704×1280** portrait, the grid the model was distilled on.
  Off-grid sizes (tested 768×1280 at 4, 6 and 8 steps) leave unconverged
  latent cells that decode to ~16 px colored fragments over the whole frame.
  `build_pairs.py` center-crops to 2:3 for the 512×768 training size, which
  drops 8.75 % at the top and bottom (see `STRATEGY.md`).
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
  `conditioning_scale=1.0`, bf16 with cpu offload. About 5 min per clip on
  the RunPod 4090 (`--no-offload` runs out of VRAM in the fp32 VAE).
- Control video: the drawing of the OpenPose detector itself
  (`controlnet_aux.OpenposeDetector`, body + hands + face) on the human
  frames, `scripts/video_to_openpose.py`. Tested: VACE ignores our own
  renders (MediaPipe white lines, and OpenPose colors drawn from MediaPipe
  landmarks), even without a reference image or at `conditioning_scale` 1.5.
  With the detector's drawing it follows the pose frame by frame.
- Pairs still use the MediaPipe landmarks of the same source frames
  (`media/control/<clip>.landmarks.jsonl`): Figment detects with MediaPipe at
  inference. `video_to_openpose.py --landmarks` renders exactly those frames,
  so the OpenPose clip and the landmarks pair by index.
- Reference image: the character. Use the first frame of the scene's
  reference clip from Model 1 (`media/refs/<scene>.png`).

### Where the skeletons come from

Human videos. Detection on fruit footage fails (tested: 37% of frames had a
pose, and those skeletons were fragments). MediaPipe on a person is near
perfect.

1. Put videos in `media/driving/`: one person, full body, facing the camera,
   telenovela gestures. Any fps, 10–60 s each.
2. `bash scripts/box/driving_to_control.sh` → MediaPipe landmarks per frame
   (`media/driving_lm/`), 81-frame landmark clips (`media/control/`, stride 3
   for 50 fps sources) and the OpenPose control clips for the same frames
   (`media/control_dw/`, about 4 min per clip on the CPU). Detection gaps
   ≤ 6 frames are interpolated; runs of 41–80 frames are extended by
   ping-pong.
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

- One 24 GB GPU is enough for both models. Model 1 runs GPU-resident and
  needs little RAM. Model 2 uses cpu offload for the text encoder (~14 GB RAM).
  A 31 GB container (RunPod) works.
- Disk: 22 GB + 3.5 GB models, plus ~1 GB per 10 clips.
- Time per clip on a 4090: Model 1 about 56 s at 704×1280×121 (4 steps,
  GPU-resident; 109 s with cpu offload);
  Model 2 about 2–3 min at 480×832×81 (30 steps).
- A 12-scene run (12 reference + 48 motion clips) is about 1.5–2 h.

## Unattended run on a fresh box

RunPod pod: `ssh runpod-4090 'bash -s' < scripts/box/runpod_setup.sh` does
all of the below (env, clone, `uv sync`, task files, both models). See
`CLAUDE.md` for the pod layout. Then start the batches by hand or with the
waiters.

```bash
git clone https://github.com/algorithmicgaze/2026-raive-projects.git
cd 2026-raive-projects/fruit-drama
uv sync
# downloads from "What to download" above
bash scripts/box/restart_waiters.sh   # waits for the model, then generates, then trains
```

Logs: `media/generate_when_ready.log`, `media/pipeline_after_generation.log`.
After a network drop or reboot: `bash scripts/box/recover.sh`.
