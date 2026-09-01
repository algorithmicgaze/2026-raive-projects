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

Runs in Figment today, 30 fps, no Figment changes.

1. Generate fruit-drama clips locally with Wan 2.2 TI2V-5B (Turbo, 4 steps).
   Use image-to-video from one reference frame per character so identity stays
   fixed across clips.
2. Run pose and face detection on every generated frame. Render the
   conditioning image in Figment style.
3. Build pairs: left = generated frame (target), right = conditioning (input).
4. Train pix2pix (`figmentapp/pix2pix`, CCM variant). Export ONNX.
5. Load the ONNX in Figment's `ONNX Image Model` node. Feed it the live
   `Detect Pose` + `Detect Faces` composite from the webcam.

Known limits:
- One character and one scene per model.
- pix2pix quality: soft detail, some flicker between frames.
- MediaPipe does not always find fruit faces. Frames with no face still train
  the pose part. Measure the detection rate per clip and drop bad clips.

Better data, next step: pose-controlled generation (Wan 2.1 VACE 1.3B or
Wan 2.2 Animate). We give the skeleton, the model follows it. Then the
conditioning is exact and we control the motion. This needs a human driving
video and more VRAM engineering. Do it after the baseline works.

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
