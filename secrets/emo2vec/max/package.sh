#!/usr/bin/env bash
# Assembles the distributable Max package in ../emotion2vec-max and zips it.
set -euo pipefail
cd "$(dirname "$0")"

OUT=../emotion2vec-max
for f in "externals/emotion2vec~.mxo" models/emotion2vec.mlmodelc "help/emotion2vec~.maxhelp" package-info.json; do
  [[ -e "$f" ]] || { echo "missing $f (run ./build.sh first)" >&2; exit 1; }
done

rm -rf "$OUT" "$OUT.zip"
mkdir -p "$OUT/externals" "$OUT/models" "$OUT/help"
cp -R "externals/emotion2vec~.mxo" "$OUT/externals/"
cp -R models/emotion2vec.mlmodelc "$OUT/models/"
cp "help/emotion2vec~.maxhelp" "$OUT/help/"
cp package-info.json "$OUT/"
cat > "$OUT/README.md" <<'EOF'
# emotion2vec~ for Max

Realtime speech emotion recognition. `emotion2vec~` runs emotion2vec+ base as a
Core ML model on the GPU (CPU fallback is automatic).

Requirements: Max 9, macOS 14 or later, Apple Silicon.

## Install

1. Copy this folder to `~/Documents/Max 9/Packages/emotion2vec`.
2. If you downloaded this package, clear the quarantine flag once:
   `xattr -dr com.apple.quarantine ~/Documents/Max\ 9/Packages/emotion2vec`
3. Restart Max and open `help/emotion2vec~.maxhelp`.

## Object

`emotion2vec~ @hop 0.25 @gate -45.`

- Inlet: signal at any sample rate.
- Outlets, left to right: probability list (angry disgusted fearful happy
  neutral other sad surprised unknown), top emotion, top probability, info
  messages (`db <level>`, `ms <inference time>`).
- `@hop`: seconds between inferences. `@gate`: dBFS below which a window is
  skipped. `@model`: path to another `.mlmodelc` (the bundled model uses a 3 s
  window).
EOF

ditto -c -k --keepParent "$OUT" "$OUT.zip"
echo "$(du -sh "$OUT" | cut -f1) $OUT, $(du -sh "$OUT.zip" | cut -f1) $OUT.zip"
