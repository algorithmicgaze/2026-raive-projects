#!/usr/bin/env bash
# Wait for the Wan Turbo download and the GPU, then run the generation batches.
set -euo pipefail
cd "$(dirname "$0")/../.."
D="$HOME/.cache/huggingface/hub/models--yetter-ai--Wan2.2-TI2V-5B-Turbo-Diffusers"
log() { echo "$(date +%H:%M:%S) $*"; }
log "waiting for model download"
until ls "$D"/snapshots/*/model_index.json >/dev/null 2>&1 \
      && ! ls "$D"/blobs/*.incomplete >/dev/null 2>&1 \
      && ! pgrep -f "[h]f download" >/dev/null; do sleep 60; done
log "model complete"
until ! pgrep -f "[t]rain_pix2pix" >/dev/null; do log "waiting for training to finish"; sleep 60; done
log "GPU free, generating"
for jobs in jobs_pineapple_i2v.json jobs_pineapple.json jobs_apple_ceo.json; do
  log "batch $jobs"
  uv run scripts/generate_clips.py batch "$jobs" || log "batch $jobs FAILED"
done
log "all batches done"
