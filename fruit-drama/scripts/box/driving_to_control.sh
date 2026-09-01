#!/usr/bin/env bash
# Turn every human video in media/driving/ into VACE control clips.
#   media/driving/<name>.(mp4|mov|webm)  ->  media/driving_lm/<name>/  (MediaPipe landmarks, pairs preview)
#                                        ->  media/control/<name>_NNN.mp4 (+ .landmarks.jsonl, for the pairs)
#                                        ->  media/control_dw/<name>_NNN.mp4 (OpenPose detector render, for VACE)
# VACE follows the OpenPose detector drawing, not our MediaPipe render. Both
# clips cover the same source frames, so the pairs stay exact.
# Re-run any time; already processed videos and clips are skipped.
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
  uv run scripts/make_control_clips.py "$lm" media/control "$name" --stride "${STRIDE:-3}"
  for c in media/control/"$name"_*.mp4; do
    dw="media/control_dw/$(basename "$c")"
    [ -f "$dw" ] || uv run scripts/video_to_openpose.py "$v" "$dw" --landmarks "${c%.mp4}.landmarks.jsonl"
  done
done
echo "control clips: $(ls media/control_dw/*.mp4 2>/dev/null | wc -l)"
