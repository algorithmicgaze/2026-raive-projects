#!/usr/bin/env bash
# Takes over from pipeline_after_generation.sh once the VACE batch is running:
# waits for generate_vace to finish, then pairs and both trainings with epochs
# sized for a ~8000-pair dataset.
set -euo pipefail
cd "$(dirname "$0")/../.."
log() { echo "$(date +%H:%M:%S) $*"; }
until ! pgrep -f "[g]enerate_vace.py" >/dev/null; do sleep 60; done
log "VACE clips: $(ls media/clips_vace/*.mp4 2>/dev/null | wc -l)"
OUT=media/dataset_scenes
uv run scripts/build_pairs.py "$OUT" jobs_scenes_i2v.json jobs_scenes_t2v.json jobs_vace.json jobs_pineapple_i2v.json 2>&1 | tail -40
log "pairs: $(ls $OUT/pairs | wc -l)"
log "training pix2pix"
uv run scripts/train_pix2pix.py "$OUT/pairs" media/train_scenes --epochs "${UNET_EPOCHS:-25}" --batch-size 8 --sample-interval 400 --snapshot-interval 5 \
  > media/train_scenes.log 2>&1 || log "pix2pix FAILED"
log "training pix2pixHD"
uv run scripts/train_pix2pixhd.py "$OUT/pairs" media/train_scenes_hd --epochs "${HD_EPOCHS:-10}" --batch-size 4 --sample-interval 400 --snapshot-interval 2 \
  > media/train_scenes_hd.log 2>&1 || log "pix2pixHD FAILED"
log "pipeline done"
