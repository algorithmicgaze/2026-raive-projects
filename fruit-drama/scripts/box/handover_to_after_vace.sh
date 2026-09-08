#!/usr/bin/env bash
# Stop the pipeline waiter (parent bash only; the running generate_vace child
# keeps going) and start after_vace.sh in its place.
set -euo pipefail
cd "$(dirname "$0")/../.."
for p in $(pgrep -f "[b]ash scripts/box/pipeline_after_generation.sh" || true); do kill "$p" || true; done
sleep 1
echo "generate_vace still running: $(pgrep -fc "[g]enerate_vace.py")"
setsid nohup bash scripts/box/after_vace.sh > media/after_vace.log 2>&1 < /dev/null &
sleep 1
ps -eo pid,cmd | grep -E "[b]ash scripts/box/|[g]enerate_vace" | cut -c1-90
