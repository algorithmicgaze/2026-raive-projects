# Handoff: RunPod session 2026-09-01 → local RTX 4090

State of the fruit-drama Wan pipeline after one day on a RunPod 4090 pod, and
how to continue on `codespace-4090`. Details and pictures: `diary.md` from
"Second box: RunPod 4090" onward. Spec: `SPEC_WAN.md`.

## What we know now

1. **Turbo (Model 1) must run at 704×1280.** 768×1280 gives colored
   fragments over the whole frame at any step count. Default is now 704×1280.
2. **Turbo needs no CPU offload.** `generate_clips.py` encodes all prompts,
   frees the text encoder, runs transformer + VAE on the GPU. 60 s per clip,
   1.4 GB RSS, 20 GB VRAM peak.
3. **VACE (Model 2) follows only the OpenPose detector drawing.** Our own
   skeleton renders (MediaPipe lines, OpenPose colors from MediaPipe
   landmarks) are ignored. `scripts/video_to_openpose.py` makes the control
   clips with `controlnet_aux.OpenposeDetector` (body + hands + face).
   Pairs use the MediaPipe landmarks of the same source frames.
4. **The 31 GB RunPod container OOM-kills silently.** Irrelevant on the
   local box (62 GB), but the fixes stay: they are faster anyway.

## What is in `media/` (synced from the pod, git-ignored)

On the Mac these sit directly in `fruit-drama/media/`. On `codespace-4090`
they are under `media/runpod/` (same layout), so nothing there overwrites the
box's own `media/clips`, `media/control`, `media/clips_vace` from its parallel
run. Merge by hand: the 704 reference clips replace the box's 768 ones
(same file names), the `control/*.landmarks.jsonl` and `control_dw/` clips are
new.

| Path | Content |
| --- | --- |
| `clips/` | 704×1280 Turbo clips: 12 `<scene>_ref.mp4` + the i2v motion clips finished before shutdown (`<scene>_NN.mp4`). Clean. |
| `clips_768/` | The first 768×1280 run. Fragments in several scenes. Keep for reference only. |
| `refs/<scene>.png` | First frame of each 704 reference clip. VACE reference images. |
| `clips_vace/` | VACE tests. `pineapple_hallway__dw1000.mp4` is the one that follows the pose. `*_op*`, `*__myrthe_000.mp4`: the ignored controls. |
| `driving/myrthe-ai-control.mp4` | The human driving video, 1024×1024, 50 fps, 39,328 frames (13 min). |
| `skeletons/myrthe-ai-control/` | MediaPipe landmarks for the first 23,106 frames (`video_to_skeleton.py` output) + skeleton preview. |
| `control/myrthe_NNN.mp4` + `.landmarks.jsonl` | 95 clips × 81 frames, stride 3, MediaPipe render at 480×832. The `.landmarks.jsonl` files are what `build_pairs.py` needs. |
| `control_dw/myrthe_NNN.mp4` | OpenPose detector control clips for the same frames. Only the first few exist (4 min each). `myrthe_1000.mp4` was the ad-hoc test (frames 1000..1240, no landmarks file). |
| `control_op/` | OpenPose colors drawn from MediaPipe landmarks. VACE ignores these. Delete. |
| `abtest/` | Old-vs-new script A/B (identical) and the resolution sweep. |
| `runpod_tmp/` | The queue scripts and job files used on the pod, plus `env.sh`. Reference only. |
| `*.log` | Pod logs: `vace_dw.log` (704 regeneration), `control_dw.log`, `vace_batch.log`, `abtest.log`, `ab_settings.log`. |

## Continue on `codespace-4090`

```bash
ssh codespace@100.91.215.104
cd ~/Work/2026-raive-projects/fruit-drama
git pull && uv sync                      # controlnet-aux is a new dependency
# pod material is in media/runpod/ (rsynced from the Mac); models are in ~/.cache/huggingface
```

Then, in this order:

1. Finish the Turbo clips that the pod did not reach:
   `uv run scripts/generate_clips.py batch jobs_scenes_i2v.json --skip-existing`
   (`jobs_scenes_i2v.json` is git-ignored: regenerate with
   `uv run scripts/make_jobs.py i2v`, it reads `media/clips/*_ref.mp4`.)
2. OpenPose control clips for the first 12 segments (CPU, ~4 min each):
   ```bash
   for k in $(seq -f "%03g" 0 11); do
     uv run scripts/video_to_openpose.py media/driving/myrthe-ai-control.mp4 media/control_dw/myrthe_$k.mp4 \
         --landmarks media/control/myrthe_$k.landmarks.jsonl
   done
   ```
   Or for every clip: `bash scripts/box/driving_to_control.sh` (it skips what
   exists; it will also re-detect MediaPipe landmarks into `media/driving_lm/`,
   which duplicates `media/skeletons/` — harmless).
3. VACE, one clip per scene, then pairs:
   ```bash
   uv run scripts/make_jobs.py vace 1
   uv run scripts/generate_vace.py batch jobs_vace.json          # ~5 min per clip with offload
   uv run scripts/build_pairs.py media/dataset_vace jobs_vace.json
   ```
   Check the first VACE clip against its control before running all 12.
4. Train: `scripts/train_pix2pix.py media/dataset_vace/pairs media/train_vace --epochs 60`.

## Open decisions

- **Aspect.** Turbo 704×1280 (0.55) and VACE 480×832 (0.58) both get a 2:3
  center-crop for 512×768 pairs, ~9 % off top and bottom. Alternative: train
  at 512×1024 and change the Figment crop.
- **Face and hands in the control.** `--no-hand-face` is 2–3× faster. Test
  whether the face dots improve fruit faces before dropping them.
- **VACE speed.** 5 min per clip with CPU offload. `--no-offload` runs out of
  VRAM in the fp32 VAE; encoding the prompt first and freeing the text
  encoder (as in `generate_clips.py`) would let it run GPU-resident.
- **Bigger model.** If VACE 1.3B quality is not enough: Wan 2.2 Animate 14B
  (character image + pose video), needs an 80 GB GPU.

## Pod details (for the record)

RunPod pod `tbff3m8bruuqbb`, direct SSH `root@47.47.180.47 -p 19754`, alias
`runpod-4090` in `~/.ssh/config` on the Mac. Everything lived on
`/workspace`. See `CLAUDE.md` for the env quirks if a new pod is created
(`scripts/box/runpod_setup.sh` does the setup).
