#!/usr/bin/env bash
# Restart only the post-generation waiter. Leaves a running generation alone.
set -euo pipefail
cd "$(dirname "$0")/../.."
for p in $(pgrep -f "[b]ash scripts/box/pipeline_after_generation.sh" || true); do kill "$p" || true; done
sleep 1
setsid nohup bash scripts/box/pipeline_after_generation.sh > media/pipeline_after_generation.log 2>&1 < /dev/null &
sleep 1
ps -eo pid,cmd | grep "[b]ash scripts/box/"
