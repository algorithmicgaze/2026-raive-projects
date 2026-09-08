#!/usr/bin/env bash
# Builds externals/emotion2vec~.mxo (macOS arm64, Core ML) and the emo_test CLI.
# Fetches the Max SDK into deps/ and converts the model on first run.
set -euo pipefail
cd "$(dirname "$0")"

SRC=source/emotion2vec~
MODEL=models/emotion2vec.mlmodelc

if [[ ! -d deps/max-sdk-base ]]; then
  git clone -q --depth 1 https://github.com/Cycling74/max-sdk-base.git deps/max-sdk-base
fi
if [[ ! -d "$MODEL" ]]; then
  echo "converting model (downloads ~1.1 GB of weights on first run)"
  (cd convert && uv run convert.py "../$MODEL")
fi

cmake -S "$SRC" -B build -DCMAKE_BUILD_TYPE=Release > /dev/null
cmake --build build --config Release
echo "built externals/emotion2vec~.mxo"
