# Fruit Drama — Brain Rot characters

Turn body movement into animated fruit characters. The project combines video
generation, pose conditioning and image-to-image models for live use in Figment.
It belongs to the **Brain Rot** group.

## Components

- `brainrot_figment/brainrot_inference.fgmt`: current pose-driven character demo.
- `inference.fgmt`, `train.fgmt`, `create-skeleton-video.fgmt`: other live inference,
  paired-data capture and skeleton-video workflows.
- `scripts/`: generate clips, extract poses, build image pairs, train pix2pix/HD
  models and check/convert ONNX exports.
- `jobs_*.json`, `scenes.json`, `prompts.md`: generation inputs and scene descriptions.
- `figment/`: custom node code, application patches and benchmark helpers.

## What you need and how to run

For the current demo, you need **Figment**, a **webcam** and
`generator_epoch_700_fp16.onnx` from **Brain Rot/brainrot_figment** in the private
share. Keep the model beside `brainrot_inference.fgmt`, open it and allow camera
access. The connected output uses the webcam; its separate Load Movie branch is
unused, so **no video file is needed for this demo**.

To build training data, supply **source videos** or generate character clips from
prompts (image-to-video jobs also need their referenced **still images**). The
capture patches require selecting a video in Load Movie. Training needs paired
target/conditioning images, **Python 3.12**, **uv**, **FFmpeg**, downloaded generation
models where applicable, and a **CUDA-capable GPU**. There is no supplied Brain Rot
PTH checkpoint for resuming the workshop run.

See [the training and generation guide](RUNNING.md), [the project plan](STRATEGY.md)
and [private asset locations](../ASSETS.md).
