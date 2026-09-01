#!/usr/bin/env bash
# Wait for the Wan Turbo download and a free GPU, then generate:
#   1. one reference clip per scene (t2v)
#   2. one skeleton-driven clip per scene (VACE, once its download is done)
#   3. four motion clips per scene from the reference frame (i2v)
set -euo pipefail
cd "$(dirname "$0")/../.."
D="$HOME/.cache/huggingface/hub/models--yetter-ai--Wan2.2-TI2V-5B-Turbo-Diffusers"
log() { echo "$(date +%H:%M:%S) $*"; }
log "waiting for model download"
until ls "$D"/snapshots/*/model_index.json >/dev/null 2>&1 \
      && ! ls "$D"/blobs/*.incomplete >/dev/null 2>&1 \
      && ! pgrep -f "[h]f download.*Turbo" >/dev/null; do sleep 60; done
log "model complete"
until ! pgrep -f "[t]rain_pix2pix" >/dev/null; do log "waiting for training to finish"; sleep 60; done
log "GPU free, generating"
uv run scripts/make_jobs.py t2v
log "batch jobs_scenes_t2v.json"
uv run scripts/generate_clips.py batch jobs_scenes_t2v.json || log "batch t2v FAILED"
uv run scripts/make_jobs.py i2v
if ls media/control/*.mp4 >/dev/null 2>&1; then
  until grep -q "VACE download done" media/download_vace.log 2>/dev/null; do log "waiting for VACE download"; sleep 60; done
  uv run scripts/make_jobs.py vace 1
  log "batch jobs_vace.json"
  uv run scripts/generate_vace.py batch jobs_vace.json || log "batch vace FAILED"
else
  log "no control clips in media/control, skipping VACE (add human videos to media/driving, run scripts/box/driving_to_control.sh)"
fi
for jobs in jobs_scenes_i2v.json jobs_pineapple_i2v.json; do
  log "batch $jobs"
  uv run scripts/generate_clips.py batch "$jobs" || log "batch $jobs FAILED"
done
log "all batches done"
