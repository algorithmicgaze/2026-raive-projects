#!/usr/bin/env bash
# One-shot recovery after a network drop or reboot. Idempotent.
#   - restarts the Turbo download if no download process is running
#   - restarts the waiters (generation, post-generation pipeline, VACE download)
#   - resumes pix2pixHD training on the apple-CEO pairs if it is not running
set -uo pipefail
cd "$(dirname "$0")/../.."
log() { echo "$(date +%H:%M:%S) $*"; }
log "uptime: $(uptime -p)"
D="$HOME/.cache/huggingface/hub/models--yetter-ai--Wan2.2-TI2V-5B-Turbo-Diffusers"
if ls "$D"/snapshots/*/model_index.json >/dev/null 2>&1 && ! ls "$D"/blobs/*.incomplete >/dev/null 2>&1; then
  log "turbo model complete"
elif pgrep -f "[h]f download.*Turbo" >/dev/null; then
  log "turbo download running"
else
  bash scripts/box/restart_download.sh
fi
bash scripts/box/restart_waiters.sh
if pgrep -f "[t]rain_pix2pixhd" >/dev/null; then
  log "pix2pixHD training running"
elif [ -f media/train_apple_ceo_hd/generator_epoch_60.onnx ]; then
  log "pix2pixHD training finished"
else
  setsid nohup uv run scripts/train_pix2pixhd.py media/dataset_apple_ceo/pairs media/train_apple_ceo_hd \
    --epochs 60 --batch-size 4 --snapshot-interval 10 >> media/train_apple_ceo_hd/run.log 2>&1 < /dev/null &
  log "pix2pixHD training resumed"
fi
nvidia-smi --query-gpu=memory.used,utilization.gpu --format=csv,noheader
