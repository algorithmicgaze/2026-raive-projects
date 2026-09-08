# Fruit Drama

Run Python with `uv run`. Use a CUDA GPU for video generation and training.
Configure your own SSH aliases (`training-gpu` and optionally `runpod-4090`).
The shell helpers assume a checkout at `/workspace/2026-raive-projects` on a
remote GPU machine; adjust those paths to your installation.

Media, datasets and trained models belong in the private participant share.
Use local paths or restore the relevant assets before running training or inference.
Export ONNX with static shapes and fp32 input/output for Figment.
