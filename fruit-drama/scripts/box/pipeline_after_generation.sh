#!/usr/bin/env bash
# After generate_when_ready.sh finishes: conditioning for every generated clip,
# one paired dataset, one pix2pix training run. Unattended.
set -euo pipefail
cd "$(dirname "$0")/../.."
log() { echo "$(date +%H:%M:%S) $*"; }
until grep -q "all batches done" media/generate_when_ready.log 2>/dev/null; do sleep 60; done
log "clips ready: $(ls media/clips/*.mp4 | wc -l)"
OUT=media/dataset_pineapple
mkdir -p "$OUT"
for clip in media/clips/pineapple_*.mp4; do
  name=$(basename "$clip" .mp4)
  log "conditioning $name"
  uv run scripts/render_conditioning.py "$clip" "$OUT" --size 512x768 --skip-empty --prefix "${name}_" --num-poses 1 --num-faces 1 \
    > "$OUT/${name}.log" 2>&1 || log "conditioning $name FAILED"
done
log "pairs: $(ls "$OUT/pairs" | wc -l)"
cat "$OUT"/pineapple_*_.json
log "training"
uv run scripts/train_pix2pix.py "$OUT/pairs" media/train_pineapple --epochs 100 --batch-size 8 --sample-interval 100 --snapshot-interval 10 \
  > media/train_pineapple.log 2>&1 || log "training FAILED"
log "pipeline done"
