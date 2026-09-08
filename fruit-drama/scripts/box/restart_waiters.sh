#!/usr/bin/env bash
# Restart the unattended waiters after a git pull. Safe to run any time:
# it never touches the download, a running training or a running generation.
set -euo pipefail
cd "$(dirname "$0")/../.."
for name in generate_when_ready pipeline_after_generation download_vace; do
  for p in $(pgrep -f "[b]ash scripts/box/${name}.sh" || true); do kill "$p" || true; done
done
sleep 1
setsid nohup bash scripts/box/generate_when_ready.sh > media/generate_when_ready.log 2>&1 < /dev/null &
setsid nohup bash scripts/box/pipeline_after_generation.sh > media/pipeline_after_generation.log 2>&1 < /dev/null &
setsid nohup bash scripts/box/download_vace.sh > media/download_vace.log 2>&1 < /dev/null &
sleep 1
echo "waiters: $(pgrep -fc "[b]ash scripts/box/")"
