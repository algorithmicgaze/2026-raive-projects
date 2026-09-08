#!/usr/bin/env bash
# Overnight variant queue for train_cstylegan.py. Safe to re-run after a
# power drop: each variant resumes from its newest snapshot, and a variant
# is skipped once its fp16 ONNX and its eval metrics exist.
#
#   nohup setsid scripts/box/run_experiments.sh [V3 V8 ...] > /dev/null 2>&1 < /dev/null &
#   tail -f output-exp/runner.log
#
# Variant names as arguments restrict the queue to those (in the given order),
# so two boxes can split it. EPOCHS (default 4) is the target epoch per
# variant. V0 is the reference: a symlink to output-cstylegan on the box that
# trained it, or a copy of its eval folders on another box.
cd "$(dirname "$0")/../.."
set -u
DATA=datasets/three_faces
OUT=output-exp
EPOCHS=${EPOCHS:-4}
mkdir -p "$OUT"
exec >> "$OUT/runner.log" 2>&1

PIDFILE=$OUT/runner.pid
if [ -e "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
  echo "$(date) runner already active (pid $(cat "$PIDFILE"))"
  exit 0
fi
echo $$ > "$PIDFILE"
[ -e "$OUT/V0" ] || [ ! -d output-cstylegan ] || ln -s ../output-cstylegan "$OUT/V0"

# name|flags. Order follows the plan: the channel plan first, then the
# combined trims, then the single trims and the depthwise candidate last.
VARIANTS=(
  "V0|"
  "V1|--channel-base 16384"
  "V3|--channel-base 16384 --skip add"
  "V8|--channel-base 16384 --skip add --enc-scale 0.5 --no-enc-top-conv"
  "V7|--synth-top 256 --out-refine 16"
  "V9|--channel-base 16384 --skip add --enc-scale 0.5 --no-enc-top-conv --conv1-max-res 128"
  "V1b|--channel-base 24576"
  "V2|--skip add"
  "V5|--enc-scale 0.5 --no-enc-top-conv"
  "V11|--channel-base 16384 --skip add --dw-levels 512,256"
  "V4|--skip-ch 512:16,256:32,128:64"
  "V6|--conv1-max-res 128"
)

# Synthetic depthwise-versus-dense models for the Figment micro-benchmark.
if [ ! -e "$OUT/dwbench/dense_fp16.onnx" ]; then
  echo "$(date) === depthwise micro-benchmark models"
  uv run scripts/export_dw_bench.py "$OUT/dwbench" && for m in dense dw; do
    uv run stylegan/to_fp16.py "$OUT/dwbench/$m.onnx" "$OUT/dwbench/${m}_fp16.onnx"
  done
fi

if [ $# -gt 0 ]; then
  selected=()
  for want in "$@"; do
    for entry in "${VARIANTS[@]}"; do [ "${entry%%|*}" = "$want" ] && selected+=("$entry"); done
  done
  VARIANTS=("${selected[@]}")
fi
echo "$(date) queue: $(for e in "${VARIANTS[@]}"; do printf '%s ' "${e%%|*}"; done)"

for entry in "${VARIANTS[@]}"; do
  name=${entry%%|*}
  flags=${entry#*|}
  dir=$OUT/$name
  if [ -s "$dir/generator_epoch_${EPOCHS}_fp16.onnx" ] && [ -s "$dir/eval_epoch_${EPOCHS}/metrics.json" ]; then
    continue
  fi
  echo "$(date) === $name: $flags"
  mkdir -p "$dir"
  echo "$flags" > "$dir/variant.txt"
  # shellcheck disable=SC2086
  if ! uv run scripts/train_cstylegan.py "$DATA" "$dir" --epochs "$EPOCHS" --snapshot-interval 2 $flags; then
    echo "$(date) $name: training failed, moving on"
    continue
  fi
  for e in $(seq 2 2 "$EPOCHS"); do
    onnx=$dir/generator_epoch_$e.onnx
    [ -e "$onnx" ] || continue
    [ -s "$dir/generator_epoch_${e}_fp16.onnx" ] || uv run stylegan/to_fp16.py "$onnx" "$dir/generator_epoch_${e}_fp16.onnx"
    if [ ! -s "$dir/eval_epoch_$e/metrics.json" ]; then
      ref=""
      [ "$name" != V0 ] && [ -e "$OUT/V0/eval_epoch_$e/metrics.json" ] && ref="--ref $OUT/V0/eval_epoch_$e"
      # shellcheck disable=SC2086
      uv run scripts/eval_variant.py "$onnx" "$DATA" "$dir/eval_epoch_$e" $ref
    fi
  done
  uv run python scripts/summarize_experiments.py "$OUT" --epoch "$EPOCHS" > "$OUT/summary.md"
  echo "$(date) === $name done"
done
echo "$(date) === queue finished"
rm -f "$PIDFILE"
