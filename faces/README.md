# Faces — face-mesh image translation (Secrets)

Convert a webcam face mesh into a generated face image using a conditional
StyleGAN or pix2pix model. This project belongs to the **Secrets** group.

## Components

- `stylegan_new/`: current webcam and prerecorded-input Figment patches.
- `scripts/train_cstylegan.py`: train conditional StyleGAN and export ONNX.
- `train_pix2pix_ccm.ipynb`: alternative pix2pix training notebook.
- `scripts/check_onnx.py` and evaluation scripts: inspect exports and compare results.
- `stylegan/`: older experiment patches, conversion and benchmark helpers.

## What you need and how to run

For live inference, you need **Figment**, a **webcam** and
`generator_epoch_10_fp16.onnx` from the private **Secrets/faces/stylegan_new** folder.
Keep it beside `three_faces_stylegan_v8_webcam.fgmt`, open the patch and allow camera
access. The ONNX node can also be pointed to the model manually. No video file is
needed for this patch. The other current patch, `three_faces_stylegan_v8_inference.fgmt`,
requires a **prerecorded conditioning video** selected in its Load Movie node.

For training, you need **Python 3.12+**, **uv**, a **CUDA-capable GPU** and a dataset
of paired images: target photo on the left, matching face-mesh render on the right.
Run `uv sync` from `faces/`, then use the trainer or open the notebook with
`uv run jupyter lab`. The private share also contains `snapshot_epoch_10.pth` for
resuming compatible training. Historical patches may reference omitted models.

Models and personal imagery are excluded from Git. See [asset locations](../ASSETS.md).
