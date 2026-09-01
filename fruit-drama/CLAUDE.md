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

## RunPod box (fallback when the 4090 box is offline)

```
ssh runpod-4090          # alias in ~/.ssh/config: root@47.47.180.47 -p 19754
cd /workspace/2026-raive-projects/fruit-drama
```

- RTX 4090 24 GB, CUDA 12.8, 12 vCPU, 31 GB RAM limit, Ubuntu 24.04.
- Use the direct TCP port for commands, `scp` and `rsync`. The
  `ssh.runpod.io` proxy only opens an interactive shell.
- `/workspace` (50 GB) persists; `/` (30 GB) is wiped when the pod restarts.
  Repo, models (`HF_HOME`) and the uv cache live on `/workspace`.
- Direct SSH sessions do not get the container env. `/workspace/env.sh`
  (sourced from `.bashrc`) sets `HF_HOME`, `UV_CACHE_DIR` and the CUDA paths.
  Fresh pod: `ssh runpod-4090 'bash -s' < scripts/box/runpod_setup.sh`.
- Fast network: models download in minutes, Xet works. The clock is UTC.
- The pod IP and port change when the pod is recreated. Update the alias.

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
