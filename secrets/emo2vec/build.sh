#!/usr/bin/env bash
# Assemble a self-contained static site in dist/.
set -euo pipefail
cd "$(dirname "$0")"

ort=node_modules/onnxruntime-web/dist
for f in "$ort/ort.webgpu.min.mjs" models/emotion2vec_plus_base.onnx models/emotion2vec_head.json; do
  [[ -f "$f" ]] || { echo "missing $f (run bun install / see README)" >&2; exit 1; }
done

rm -rf dist
mkdir -p dist/ort dist/models
cp index.html pcm-worklet.js coi-serviceworker.js dist/
sed 's|./node_modules/onnxruntime-web/dist/|./ort/|' app.js > dist/app.js
cp "$ort"/ort.webgpu.min.mjs "$ort"/ort-wasm-simd-threaded.asyncify.{mjs,wasm} dist/ort/
cp models/emotion2vec_plus_base.onnx models/emotion2vec_head.json dist/models/

echo "dist/ ready ($(du -sh dist | cut -f1))"
