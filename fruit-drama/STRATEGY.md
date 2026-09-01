# Strategy: realtime fruit drama

Goal: a student performs at a webcam. The output is a fruit character in a
telenovela scene, in realtime, on our own hardware.

The reference format (see `CLAUDE.md`) is an offline pipeline: still image →
image-to-video → voiceover → edit. Motion is small: a head turn, a gesture, a
tear. We do not need a model that invents motion. We need a model that turns a
*performer* into a *character*, frame after frame. That is puppeteering.

We run two tracks. Both use the same conditioning signal and the same dataset.

## Conditioning signal

Full-body pose plus face contours, drawn the way Figment draws them:

- `Detect Pose` (MediaPipe pose landmarker, heavy): white points r=2 and white
  lines w=2 on black, `POSE_CONNECTIONS`.
- `Detect Faces` (MediaPipe face landmarker): white contour lines w=1 on black,
  `FACE_LANDMARKS_CONTOURS`.
- Both composited with `lighten`.

The Python renderer in `scripts/` reproduces this exactly. Training input must
match what Figment produces at inference time, or the model sees a distribution
it never learned.

MediaPipe Holistic still exists in the Python Tasks API
(`mp.tasks.vision.HolisticLandmarker`). It is not in the web Tasks API that
Figment uses. So we run pose and face as two separate models, like Figment.

## Track A: distill a video model into pix2pix

Runs in Figment today, 30 fps, no Figment changes. Two data paths feed it;
the skeleton path is primary (measured 2026-09-01, see `diary.md`).

**Skeleton path (primary).** A human performs; Figment `Detect Pose` exports
the landmarks. `make_control_clips.py` cuts them into 81-frame control videos.
Wan 2.1 VACE 1.3B animates a fruit character along them (reference image =
the scene's first frame). Pairs come from the landmarks that drove the clip:
no detection on the output, every frame usable. Measured: pose re-detected on
81/81 frames, joint error 2.6 % of the frame.

**Prompt path (references and variety).** Wan 2.2 TI2V-5B Turbo (4 steps)
makes one reference clip per scene from `scenes.json`, then motion clips from
the reference frame. Detection on the output keeps only usable frames. Prompt
rules: one character, standing, full body, facing the camera; say "a man
whose head is a big shiny red apple", not "an apple man"; plain settings, no
glass walls, city views or sparkling lights (they become confetti). The
negative prompt does nothing at guidance 1.0.

**Scene code.** The conditioning background color encodes the scene
(`scenes.json`). Figment's Detect Pose / Detect Faces `background` parameter
sets it at inference. One model, many scenes.

Then: `build_pairs.py` → `train_pix2pix.py` or `train_pix2pixhd.py` → ONNX →
Figment `ONNX Image Model`, fed by the live `Detect Pose` (+ `Detect Faces`)
composite from the webcam.

**Model choice.** pix2pixHD is clearly sharper on the same data; its ONNX is
730 MB and ~5–8× the compute of the U-Net (218 MB). Measure fps in Figment
before choosing; fp16 export or a lighter HD config are the middle ground.

Known limits:
- One character and one scene per model.
- pix2pix quality: soft detail, some flicker between frames.
- MediaPipe often finds nothing in fruit footage. Measured on the apple-CEO
  compilation (1645 frames): 37% with a pose, 28% with a face, 10% with both.
  Crowded or seated shots fail. Single character, frontal, full body works.
  Prompt for that. Curate with the per-frame CSV.

Open questions:
- OpenPose-style colored control (VACE's training format) versus our
  MediaPipe drawing: the MediaPipe drawing already works; test whether
  OpenPose follows tighter.
- Face contours: fruit faces rarely detect. Human driving data has no face
  landmarks in the pose export. If faces matter, export Figment `Detect Faces`
  landmarks from the human too and draw them on the same control frames.

## Track B: SD-Turbo img2img with a character LoRA

Prompt-driven, no dataset per character, 20+ fps on the 4090.

1. StreamDiffusion + SD-Turbo (or SD 1.5 + LCM-LoRA), img2img, 1–4 steps.
   Denoise strength 0.4–0.6 keeps the performer's pose and framing.
2. Train one small LoRA per character on 5–10 reference images (~10 min).
3. Run it as a server on the 4090. Output to a virtual camera (OBS or
   v4l2loopback). Figment's `Webcam Image` node picks it up. No Figment code.
4. Later, if the look is right: export UNet + VAE to ONNX and run inside
   Figment with onnxruntime-web WebGPU. Expect ~5–8 fps in the browser versus
   20+ fps with TensorRT. Prove the look server-side first.

Known limits:
- Identity drift between frames. The LoRA reduces it. It does not remove it.
- No temporal model. Flicker is visible. StreamDiffusion's RCFG and
  similar-image filter help.

## Ceiling: realtime video models

Self-Forcing, StreamDiffusionV2 and Causal Forcing (all on Wan 1.3B) give
coherent motion at 10–20 fps, 480p, on one 4090. Server only. Good for a demo.
Too slow to set up for students to iterate on. Not a track. A stretch goal.
