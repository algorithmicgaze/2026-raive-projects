#!/usr/bin/env bash
# Download Wan 2.1 VACE 1.3B without its text encoder (shared with the Turbo model).
# Waits for the Turbo download to finish first so the two do not share the link.
set -euo pipefail
cd "$(dirname "$0")/../.."
D="$HOME/.cache/huggingface/hub/models--yetter-ai--Wan2.2-TI2V-5B-Turbo-Diffusers"
until ls "$D"/snapshots/*/model_index.json >/dev/null 2>&1 && ! ls "$D"/blobs/*.incomplete >/dev/null 2>&1; do sleep 60; done
echo "$(date +%H:%M:%S) turbo complete, downloading VACE"
HF_HUB_DISABLE_XET=1 uvx --from huggingface_hub hf download Wan-AI/Wan2.1-VACE-1.3B-diffusers --exclude "text_encoder/*"
echo "$(date +%H:%M:%S) VACE download done"
