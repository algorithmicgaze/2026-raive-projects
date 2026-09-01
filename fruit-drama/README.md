# Fruit Drama generator

Realtime fruit-drama characters driven by a webcam. See `STRATEGY.md` for the
plan and `diary.md` for the working log.

All heavy work runs on the 4090 box (`CLAUDE.md`). Paths below are relative to
this directory on that box.

## Scripts

| Script | What it does |
| --- | --- |
| `scripts/generate_clips.py` | Wan 2.2 TI2V-5B Turbo, text-to-video or image-to-video, single job or a `jobs_*.json` batch. Output 768×1280, 121 frames, 24 fps. |
| `scripts/render_conditioning.py` | MediaPipe pose + face drawn the way Figment draws them. Writes `[target \| input]` pairs, a per-frame CSV and a stats JSON. |
| `scripts/train_pix2pix.py` | pix2pix (CCM recipe from `figmentapp/pix2pix`) on a pairs folder. Exports ONNX at each snapshot. |
| `scripts/check_onnx.py` | Runs an exported ONNX with onnxruntime. Prints the input shape Figment reads. |
| `scripts/box/restart_download.sh` | Restarts the model download. Xet disabled: it stalls on this network. |
| `scripts/box/generate_when_ready.sh` | Waits for the model and a free GPU, then runs all job lists. |
| `scripts/box/pipeline_after_generation.sh` | Waits for the clips, builds `media/dataset_pineapple`, trains a model. |

## Typical run

```bash
# 1. clips
uv run scripts/generate_clips.py batch jobs_pineapple_i2v.json

# 2. conditioning + pairs (512x768 per half, frames without a pose skipped)
uv run scripts/render_conditioning.py media/clips/pineapple_01.mp4 media/dataset_pineapple \
    --size 512x768 --skip-empty --prefix pineapple_01_ --num-poses 1 --num-faces 1

# 3. train
uv run scripts/train_pix2pix.py media/dataset_pineapple/pairs media/train_pineapple --epochs 100 --batch-size 8

# 4. check the ONNX
uv run scripts/check_onnx.py media/train_pineapple/generator_epoch_100.onnx media/dataset_pineapple/pairs/pineapple_01_00010.jpg out.jpg --pair
```

## Figment

`inference.fgmt`: Webcam → Crop 480×720 → Resize 512×768 → Detect Pose +
Detect Faces → Composite (lighten) → ONNX Image Model → Stack → Out.
Copy the trained ONNX next to it as `generator.onnx`.

`train.fgmt` is the original Figment-only dataset network (Load Movie →
detect → stack → save). `render_conditioning.py` does the same on the box.

## Rules learned

- Training frames need one character, frontal, full body, medium or wide
  shot. MediaPipe finds nothing in crowded fruit group shots.
- Sides must divide by 256 (U-Net with 8 down-samplings). Portrait: 512×768.
- Crop to 2:3 *before* detection. Do the same crop in Figment.
