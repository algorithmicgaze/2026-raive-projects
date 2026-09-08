#!/usr/bin/env bash
# After generate_when_ready.sh: pairs for every clip (scene color as
# background), then pix2pix and pix2pixHD on the same dataset. Unattended.
set -euo pipefail
cd "$(dirname "$0")/../.."
log() { echo "$(date +%H:%M:%S) $*"; }
until grep -q "all batches done" media/generate_when_ready.log 2>/dev/null; do sleep 60; done
log "clips ready: $(ls media/clips/*.mp4 | wc -l)"
if [ -f jobs_ab_apple_ceo.json ] && [ ! -d media/clips_ab ]; then
  log "A/B batch jobs_ab_apple_ceo.json"
  uv run scripts/generate_clips.py batch jobs_ab_apple_ceo.json || log "A/B FAILED"
fi
if ls media/control/*.mp4 >/dev/null 2>&1; then
  until grep -q "VACE download done" media/download_vace.log 2>/dev/null; do log "waiting for VACE download"; sleep 60; done
  uv run scripts/make_jobs.py vace "${VACE_PER_SCENE:-2}"
  log "VACE batch jobs_vace.json ($(python3 -c "import json;print(len(json.load(open('jobs_vace.json'))))") clips)"
  uv run scripts/generate_vace.py batch jobs_vace.json > media/generate_vace.log 2>&1 || log "VACE FAILED (see media/generate_vace.log)"
  ls media/clips_vace/*.mp4 2>/dev/null | wc -l | xargs -I{} log "VACE clips: {}"
else
  log "no control clips, skipping VACE"
fi
OUT=media/dataset_scenes
uv run scripts/build_pairs.py "$OUT" jobs_scenes_i2v.json jobs_scenes_t2v.json jobs_vace.json jobs_pineapple_i2v.json 2>&1 | tail -40
log "training pix2pix"
uv run scripts/train_pix2pix.py "$OUT/pairs" media/train_scenes --epochs 60 --batch-size 8 --sample-interval 200 --snapshot-interval 10 \
  > media/train_scenes.log 2>&1 || log "pix2pix FAILED"
log "training pix2pixHD"
uv run scripts/train_pix2pixhd.py "$OUT/pairs" media/train_scenes_hd --epochs 40 --batch-size 4 --sample-interval 200 --snapshot-interval 10 \
  > media/train_scenes_hd.log 2>&1 || log "pix2pixHD FAILED"
log "pipeline done"
