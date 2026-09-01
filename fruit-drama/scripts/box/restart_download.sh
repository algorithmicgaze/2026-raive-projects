#!/usr/bin/env bash
# Restart the Wan Turbo download with hf_transfer (multi-connection).
set -euo pipefail
cd "$(dirname "$0")/../.."
REPO="yetter-ai/Wan2.2-TI2V-5B-Turbo-Diffusers"
for p in $(pgrep -f "[h]f download" || true); do kill "$p" || true; done
sleep 1
HF_HUB_DISABLE_XET=1 setsid nohup uvx --from huggingface_hub hf download "$REPO" \
  > media/hf_download_turbo.log 2>&1 < /dev/null &
echo "download restarted (pid $!)"
