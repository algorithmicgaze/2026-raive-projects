# Using the participant assets

The paths below are relative to the private OneDrive **projects** folder.
For inference, open the supplied patch beside its ONNX file in OneDrive, or
select that model in Figment's ONNX Image Model node. Movie-based patches also
need a local input movie; the Secrets webcam patch needs no prerecorded movie.

| Model | Private path | Retention |
| --- | --- | --- |
| Fashion | `Fashion/finetune_epoch_6600_fp16.onnx` | Latest supplied fine-tuned export |
| Secrets face StyleGAN | `Secrets/faces/stylegan_new/generator_epoch_10_fp16.onnx` | Latest supplied run; recommended for Figment |
| Secrets face StyleGAN fp32 | `Secrets/faces/stylegan_new/generator_epoch_10.onnx` | Alternate precision of the same epoch |
| Secrets resumable checkpoint | `Secrets/faces/stylegan_new/snapshot_epoch_10.pth` | Latest supplied checkpoint; epoch 8 omitted |
| Secrets pix2pix baseline | `Secrets/faces/pix2pix/model.onnx` | Separate architecture, retained for reference |
| Emotion2vec web model | `Secrets/emo2vec/models/` | ONNX plus required label/head JSON |
| Emotion2vec Max package | `Secrets/emo2vec/emotion2vec-max/` | Compiled external and Core ML model |
| Brain Rot character | `Brain Rot/brainrot_figment/generator_epoch_700_fp16.onnx` | Latest supplied character export |
| Brain Rot scene U-Net | `Brain Rot/media/models/scenes_unet_epoch25.onnx` | Separate scene architecture |
| Brain Rot scene HD | `Brain Rot/media/models/scenes_hd_epoch10.onnx` | Separate scene architecture |
| Cars detector | `Cars/output-figment/repaired/models/yolo11n.pt` | Detector used by the repair pipeline |

**No Fashion or Brain Rot PTH checkpoint was present in the supplied folders.**
Those ONNX exports support inference, but do not replace resumable training
snapshots. Request the corresponding PTH from the training machine to resume
those runs. Never load untrusted PyTorch checkpoints.

For training and tools with relative paths, copy only the required private
subfolder into the matching source project locally (e.g. `Cars/media` →
`cars/media`, `Secrets/faces/media` → `faces/media`, `Brain Rot/media` →
`fruit-drama/media`). These paths are ignored by Git. Alternatively set the
script's input/output arguments to paths in the private share. Fashion's notebook
expects `datasets/fashion`; supply a paired training dataset there.

Historical `faces/stylegan` experiment templates remain as reusable code, but
older experimental weights and repeated exports are omitted from the share.
The private model manifest records retained model filenames, sizes and SHA-256.
Model compatibility has not been tested on a GPU or in Figment during this cleanup.
