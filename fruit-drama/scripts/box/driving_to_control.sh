#!/usr/bin/env bash
# Turn every human video in media/driving/ into VACE control clips.
#   media/driving/<name>.(mp4|mov|webm)  ->  media/driving_lm/<name>/  (landmarks, pairs preview)
#                                        ->  media/control/<name>_NNN.mp4 (+ .landmarks.jsonl)
# Re-run any time; already processed videos are skipped.
set -euo pipefail
cd "$(dirname "$0")/../.."
shopt -s nullglob
for v in media/driving/*.mp4 media/driving/*.mov media/driving/*.MOV media/driving/*.webm; do
  name=$(basename "${v%.*}")
  lm="media/driving_lm/$name/${name}_landmarks.jsonl"
  if [ ! -f "$lm" ]; then
    echo "== landmarks for $name"
    uv run scripts/render_conditioning.py "$v" "media/driving_lm/$name" --size 480x832 --prefix "${name}_" --skip-empty
  fi
  echo "== control clips for $name"
  uv run scripts/make_control_clips.py "$lm" media/control "$name"
done
echo "control clips: $(ls media/control/*.mp4 2>/dev/null | wc -l)"
