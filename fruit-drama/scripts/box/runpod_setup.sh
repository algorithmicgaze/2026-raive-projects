#!/usr/bin/env bash
# One-shot setup of a fresh RunPod pod (RTX 4090, /workspace volume). Idempotent.
#   ssh runpod-4090 'bash -s' < scripts/box/runpod_setup.sh
# Direct sshd sessions do not inherit the container env, so HF_HOME, UV_CACHE_DIR
# and the CUDA paths are written to /workspace/env.sh and sourced from .bashrc.
# Everything large lives on /workspace (persistent); / is a 30 GB ephemeral overlay.
set -euo pipefail
cat > /workspace/env.sh <<'ENV'
export HF_HOME=/workspace/.cache/huggingface
export UV_CACHE_DIR=/workspace/.cache/uv
export HF_XET_HIGH_PERFORMANCE=1
export PATH=/usr/local/cuda/bin:$PATH
export LD_LIBRARY_PATH=/usr/local/cuda/lib64
export PYTHONUNBUFFERED=1
ENV
grep -q "workspace/env.sh" /root/.bashrc || sed -i '1i [ -f /workspace/env.sh ] && . /workspace/env.sh' /root/.bashrc
. /workspace/env.sh

cd /workspace
[ -d 2026-raive-projects ] || git clone -q https://github.com/algorithmicgaze/2026-raive-projects.git
cd 2026-raive-projects && git pull -q --ff-only && cd fruit-drama
uv sync

mkdir -p media/models && cd media/models
for f in pose_landmarker/pose_landmarker_heavy/float16/latest/pose_landmarker_heavy.task \
         face_landmarker/face_landmarker/float16/latest/face_landmarker.task; do
  [ -f "$(basename "$f")" ] || curl -sSLO "https://storage.googleapis.com/mediapipe-models/$f"
done
cd ../..

# Fast link: Xet works here, no HF_HUB_DISABLE_XET.
uvx --from huggingface_hub hf download yetter-ai/Wan2.2-TI2V-5B-Turbo-Diffusers
uvx --from huggingface_hub hf download Wan-AI/Wan2.1-VACE-1.3B-diffusers --exclude "text_encoder/*"
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
df -h /workspace | tail -1
