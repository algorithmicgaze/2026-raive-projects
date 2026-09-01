# Diary

Working log for the fruit-drama project. Newest entry at the bottom.
Screenshots live in `diary/`.

## 2026-09-01 11:00 — Kick-off

- Read the reference blog post. Fruit drama = offline pipeline, small motion,
  Pixar-meets-telenovela look.
- Probed the 4090 box: RTX 4090 24 GB, CUDA 12.8, 62 GB RAM, `uv`, `ffmpeg`.
- Wrote `CLAUDE.md`, `STRATEGY.md` (two tracks), `prompts.md`.
- Found `train.fgmt`: Load Movie → Detect Pose (heavy, 2) + Detect Faces (2) →
  lighten → Stack → Save. 829 frames exported from `fruit-drama-apple-ceo.webm`
  (1080×1920, 30 fps).
- Read Figment's `detectPose.js` and `detectFaces.js`. Drawing defaults:
  pose points r=2, lines w=2, white on black; face contours w=1 white.
- MediaPipe Holistic: still exists in the Python Tasks API, not in the web
  Tasks API. Figment uses pose + face separately. Python does the same.
- Model choice for data generation: `yetter-ai/Wan2.2-TI2V-5B-Turbo-Diffusers`,
  4 steps, 1280×704, 121 frames at 24 fps. Supports image-to-video. Download
  started on the box.

Observation: in the exported frame `export/image-00100.jpg` Figment found a
partial skeleton and **no face** on either apple. The pineapple screenshot shows
face detection can work on fruit heads. Detection rate is the first thing to
measure.
