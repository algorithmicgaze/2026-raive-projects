#!/usr/bin/env bash
# Mac side of the variant experiments: pull the fp16 exports from the box,
# time each one in Figment (onnx-image:inference-total, PR 109 timing plus
# ORT's kernel profile), render 40 frames of the test clip per variant, and
# compare the frames with V0's. Re-runnable: finished steps are skipped.
#
#   stylegan/bench_variants.sh            # epoch 4 (default)
#   EPOCH=2 stylegan/bench_variants.sh
#
# Needs: the Figment build under ~/Projects/figment/dist (PR 109 merged, fp16
# branch), bench.mjs in ~/Desktop/pix2pix-research-log/scripts/figment-bench.
cd "$(dirname "$0")"
set -u
# Both training boxes; the queue is split between them.
REMOTES=(fdb@100.106.183.123:/home/fdb/Work/2026-raive-projects/secrets/faces/output-exp
         codespace@100.91.215.104:/home/codespace/Work/2026-raive-projects/secrets/faces/output-exp)
EPOCH=${EPOCH:-4}
FRAMES=${FRAMES:-40}
BENCH_DIR=$HOME/Desktop/pix2pix-research-log/scripts/figment-bench
FIGMENT=$HOME/Projects/figment/dist/mac-arm64/Figment.app/Contents/MacOS/Figment
TEMPLATE=three_faces_stylegan_inference.fgmt

echo "=== pull from the boxes"
for remote in "${REMOTES[@]}"; do
  rsync -aL --info=progress2 \
    --include='*/' --include="generator_epoch_${EPOCH}_fp16.onnx" --include='variant.txt' \
    --include='training_log.txt' --include='sample_epoch_*.jpg' --include='eval_epoch_*/metrics.json' \
    --include='eval_epoch_*/sheet.jpg' --include='dwbench/*_fp16.onnx' \
    --include='model.onnx' --include='eval/metrics.json' --include='eval/sheet.jpg' \
    --exclude='*' "$remote/" exp/ || echo "pull from $remote failed, continuing with what is here"
done

[ -e "$BENCH_DIR/node_modules" ] || ln -s "$HOME/Projects/figment/node_modules" "$BENCH_DIR/node_modules"

# One project per variant: the inference project with the model swapped.
projects=()
for dir in exp/*/; do
  name=$(basename "$dir")
  model=$dir/generator_epoch_${EPOCH}_fp16.onnx
  [ -e "$model" ] || model=$dir/model.onnx  # external baseline (pix2pix), one fixed file
  [ -e "$model" ] || continue
  project=exp_${name}_e${EPOCH}.fgmt
  python3 - "$TEMPLATE" "$project" "$model" <<'EOF'
import json, sys
template, out, model = sys.argv[1:]
p = json.load(open(template))
for n in p["nodes"]:
    if n["type"] == "ml.onnxImageModel":
        n["values"]["model"]["value"] = model
json.dump(p, open(out, "w"), indent=2)
EOF
  projects+=("$project")
done
for m in dense dw; do
  if [ -e "exp/dwbench/${m}_fp16.onnx" ]; then
    python3 - "$TEMPLATE" "exp_dwbench_${m}.fgmt" "exp/dwbench/${m}_fp16.onnx" <<'EOF'
import json, sys
template, out, model = sys.argv[1:]
p = json.load(open(template))
for n in p["nodes"]:
    if n["type"] == "ml.onnxImageModel":
        n["values"]["model"]["value"] = model
json.dump(p, open(out, "w"), indent=2)
EOF
    projects+=("exp_dwbench_${m}.fgmt")
  fi
done

echo "=== Figment timing (${#projects[@]} projects)"
bench_txt=exp/bench_epoch_${EPOCH}.txt
node "$BENCH_DIR/bench.mjs" "${projects[@]}" | tee "$bench_txt"
python3 - "$bench_txt" "$EPOCH" <<'EOF'
import json, re, sys, os
text, epoch = open(sys.argv[1]).read(), sys.argv[2]
for block in text.split("\n=== ")[1:]:
    name = re.match(r"exp_(.+?)_e\d+\.fgmt", block)
    m = re.search(r"onnx-image:inference-total\s+(\{.*\})", block)
    if not name or not m:
        continue
    stats = json.loads(m[1])
    kernels = re.findall(r"^\s+([\d.]+) ms\s+(\S+)\s+(\S+)", block.split("top kernels:")[-1], re.M)[:5]
    out = {"ms": stats["p50"], "fps": round(1000 / stats["p50"], 1), "stats": stats,
           "top_kernels": [{"ms": float(k[0]), "type": k[1], "program": k[2]} for k in kernels]}
    json.dump(out, open(f"exp/{name[1]}/bench_epoch_{epoch}.json", "w"), indent=1)
    print(f"{name[1]:6s} {stats['p50']:7.1f} ms  {1000 / stats['p50']:5.1f} fps")
EOF

echo "=== frames"
for project in "${projects[@]}"; do
  case $project in exp_dwbench_*) continue;; esac
  name=${project#exp_}; name=${name%_e${EPOCH}.fgmt}
  frames=exp/$name/frames_e${EPOCH}
  if [ "$(ls "$frames"/*.png 2>/dev/null | wc -l)" -lt "$FRAMES" ]; then
    mkdir -p "$frames"
    "$FIGMENT" --render "$project" --frames "$FRAMES" -o "$frames/frame-####.png"
  fi
done
for dir in exp/*/; do
  name=$(basename "$dir")
  [ "$name" = V0 ] && continue
  frames=$dir/frames_e${EPOCH}
  [ -e "exp/V0/frames_e${EPOCH}" ] && [ -d "$frames" ] || continue
  uv run "$BENCH_DIR/compare_frames.py" "exp/V0/frames_e${EPOCH}" "$frames" "$dir/vs_V0_e${EPOCH}.png" > "$dir/vs_V0_e${EPOCH}.txt"
  tail -2 "$dir/vs_V0_e${EPOCH}.txt" | head -1 | sed "s/^/$name: /"
done

echo "=== results"
uv run python ../scripts/summarize_experiments.py exp --epoch "$EPOCH" > exp/results.md
cat exp/results.md
