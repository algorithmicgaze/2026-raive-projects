#!/usr/bin/env bash
# After generate_when_ready.sh: pairs for every clip (scene color as
# background), then pix2pix and pix2pixHD on the same dataset. Unattended.
set -euo pipefail
cd "$(dirname "$0")/../.."
log() { echo "$(date +%H:%M:%S) $*"; }
until grep -q "all batches done" media/generate_when_ready.log 2>/dev/null; do sleep 60; done
log "clips ready: $(ls media/clips/*.mp4 | wc -l)"
OUT=media/dataset_scenes
uv run scripts/build_pairs.py "$OUT" jobs_scenes_i2v.json jobs_scenes_t2v.json jobs_pineapple_i2v.json 2>&1 | tail -40
log "training pix2pix"
uv run scripts/train_pix2pix.py "$OUT/pairs" media/train_scenes --epochs 60 --batch-size 8 --sample-interval 200 --snapshot-interval 10 \
  > media/train_scenes.log 2>&1 || log "pix2pix FAILED"
log "training pix2pixHD"
uv run scripts/train_pix2pixhd.py "$OUT/pairs" media/train_scenes_hd --epochs 40 --batch-size 4 --sample-interval 200 --snapshot-interval 10 \
  > media/train_scenes_hd.log 2>&1 || log "pix2pixHD FAILED"
log "pipeline done"
