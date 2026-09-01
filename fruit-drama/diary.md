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

## 2026-09-01 11:30 — Infrastructure

- Committed and pushed the scaffold (`7930dd4`): `STRATEGY.md`, `prompts.md`,
  `scripts/render_conditioning.py`, `scripts/generate_clips.py`,
  `scripts/train_pix2pix.py`, `pyproject.toml`.
- `scripts/render_conditioning.py` reproduces the Figment drawing: pose points
  r=2 with the DrawingUtils default 4 px stroke (effective r≈4), lines w=2, face
  contours w=1, lighten composite, `[target | input]` stack.
- `scripts/train_pix2pix.py` is the CCM notebook as a CLI. Same architecture,
  same losses. ONNX export uses the dataset's own width × height, so portrait
  pairs work.
- **The box's internet is slow: ~1–5 MB/s.** The Wan Turbo model is ~22 GB and
  `uv sync` pulls ~5 GB of torch + CUDA. Expect 1–2 hours before the first
  clip. Started both, plus a MediaPipe-only env to test detection on
  `fruit-drama-apple-ceo.webm` in the meantime.
- Lesson: never put the string `hf download` in an ssh command line that also
  runs `pkill -f`. It kills its own shell. Use `scripts/box/restart_download.sh`.
- `.gitignore`: `export/`, `*.webm`, `.venv/`. The 829 exported frames (242 MB)
  and the source video are synced to the box with rsync, not git.

## 2026-09-01 11:45 — Resolution decision

The pix2pix U-Net has 8 down-samplings, so width and height must divide by
256. Portrait options: 512×768, 512×1024, 768×1280.

- Generate at **768×1280** (aspect 0.60, close to 9:16). Wan needs multiples
  of 32; this fits.
- Train at **512×768** per half. Inference cost in Figment scales with pixels;
  512×768 is 3.75× cheaper than 768×1280. That is where "realtime" is won.
- `render_conditioning.py --size 512x768` center-crops to 2:3 *before*
  detection, then resizes. No squash, and landmark coordinates stay aligned.
- The same crop + resize must happen in Figment at inference. Add a Crop node
  before Detect Pose / Detect Faces.

## 2026-09-01 12:05 — Why it is slow

- The box is on **Wi-Fi** (`wlp5s0`). The Ethernet port `enp6s0` has no
  carrier. Total inbound is ~3 MB/s. A cable would fix this.
- The uv cache on the box already holds torch 2.8.0 (PyPI build, CUDA 12.8
  bundled). My first `pyproject.toml` asked for the newest cu128 build
  (2.11.0), which would download ~4 GB again. Pinned `torch==2.8.0`,
  `torchvision==0.23.0`, dropped the custom index, restarted `uv sync`.
- OpenCV cannot decode the AV1 webm. Transcoded to H.264 with ffmpeg
  (`media/apple_ceo.mp4`, 1645 frames). Detection test restarted on that file,
  every 3rd frame, at 512×768.
- Diary is also published as a phone-readable page:
  https://claude.ai/code/artifact/d0a973f2-34c6-4124-b07f-a2667a01c219

## 2026-09-01 12:30 — First detection results on the apple-CEO video

![Four sampled frames with MediaPipe pose + face drawn over them](diary/01_apple_ceo_overlay.jpg)

Three of the four sampled frames have **no detection at all**. The video is a
compilation of crowded group shots: seated characters, backs turned, huge
fruit heads, phones in the foreground. MediaPipe was trained on humans and
gives up.

![Training pair: pineapple mother scene, source left, conditioning right](diary/02_apple_ceo_pair.jpg)

The pineapple "MOM" scene works: one character, frontal, full body, face
found. This is the shape every training frame needs.

Consequences:
- Train only on frames with a pose (`--skip-empty`). The renderer now writes a
  per-frame CSV (`poses,faces` per frame) so we can curate.
- Generated clips must be **single character, frontal, full body, medium or
  wide shot**. Two people at a table will not detect.
- Saved the pineapple frame as `media/refs/pineapple_mom.png` (768×1280). It is
  a known-good image-to-video reference.
- Environment is ready (torch 2.8 + CUDA, diffusers 0.40, MediaPipe 1.0.1).
  Detection runs at ~20 fps on CPU.
- Started pix2pix training on the apple-CEO pairs while the Wan model
  downloads. This validates the whole chain end to end.

## 2026-09-01 13:00 — Download stalled; Wi-Fi is not the whole story

- Correction to the earlier note: `iwconfig` shows the Wi-Fi link at 400 Mb/s,
  signal −51 dBm, quality 59/70. The radio is fine. The ~3 MB/s ceiling is
  upstream of the box (router or ISP). A cable may not change it.
- The HF download process died once and, after restart, wrote 0 bytes for
  minutes while holding three `.incomplete` blobs open. The client uses the
  Xet chunk protocol (`~/.cache/huggingface/xet/logs`). Restarted with
  `HF_HUB_DISABLE_XET=1` to force plain HTTPS from the CDN.
- Meanwhile: training on the 603 apple-CEO pairs continues (~12 s/epoch).
  Wrote `scripts/check_onnx.py` (runs the exported ONNX with onnxruntime,
  prints the input shape Figment will read) and `inference.fgmt` (webcam →
  crop 2:3 → resize 512×768 → pose + face → lighten → ONNX → out).
