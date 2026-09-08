# Fashion — pose-driven image generation

Use a person's webcam pose to drive a trained image-to-image model, producing
fashion imagery in real time in Figment.

## Components

- `fashion_inference.fgmt`: webcam → pose detection → ONNX model, with a comparison view.
- `train_stylegan2_conditional.ipynb`: conditional StyleGAN2 training, checkpoints
  and ONNX export.

## What you need and how to run

For the demo, you need **Figment**, a **webcam** and the trained
`finetune_epoch_6600_fp16.onnx` file from the private **Fashion** share.
Place the model beside `fashion_inference.fgmt`, open the patch and allow camera
access. If necessary, select the model in the ONNX Image Model node.
**No prerecorded video is required** for live inference.

To train your own model, you need a **CUDA-capable GPU**, **Python/Jupyter** and the
notebook's dependencies: PyTorch, torchvision, NumPy, Pillow, matplotlib, tqdm,
ONNX, ONNX Runtime and onnxconverter-common. Supply **paired training images**
(target on the left, matching pose render on the right) in `datasets/fashion`, or
change `input_dir` in the notebook. Review its settings and run the cells in order.
A raw video alone is not a paired training dataset.

The share includes the latest ONNX export but **no Fashion PTH checkpoint**, so
resuming that exact training run requires obtaining its checkpoint separately.
See [asset locations](../ASSETS.md).
