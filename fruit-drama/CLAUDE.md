# Fruit Drama

Tools for students to make "fruit drama" videos: anthropomorphic fruit and
vegetable characters in soap-opera scenes. Reference format:
https://www.flashloop.app/blog/how-to-make-ai-fruit-drama-videos

Goal: a roughly realtime, local pipeline. Not a cloud service.

## Repository layout

The git repo root is the parent directory `2026-raive-projects/`
(remote: `algorithmicgaze/2026-raive-projects`). This project is the
subdirectory `fruit-drama/`. Commit from the repo root.

`media/` and `tmp/` are git-ignored. Put datasets, model weights and
rendered video there.

## GPU machine

All model training and inference runs on the remote RTX 4090 box:

```
ssh codespace@100.91.215.104
cd /home/codespace/Work/2026-raive-projects/fruit-drama
```

- Host: `codespace-4090`, RTX 4090 24 GB, CUDA 12.8, 62 GB RAM, 32 cores
- Tools: `uv`, `ffmpeg`, `node` 24, Python 3.12
- The remote directory is a clone of the same git repo. Sync with git.
  Do not `scp` source files.
- Keep large downloads (HF models) in `~/.cache/huggingface`, not in the repo.

## Conventions

- Python: `uv run`, never bare `python`. Use PEP 723 inline metadata for
  standalone scripts.
- Export models to ONNX with static shapes. Figment reads input and output
  dimensions from the ONNX metadata.

## Related work

- Figment (WebGPU node editor, runs ONNX via onnxruntime-web):
  https://github.com/figmentapp/figment
- pix2pix training and ONNX export: https://github.com/figmentapp/pix2pix
- Earlier pix2pix experiments on the 4090 box:
  `~/Work/pix2pix-benchmark`, `~/Work/2024-pix2pix-implementations`
