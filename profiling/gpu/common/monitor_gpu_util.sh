#!/usr/bin/env bash
# Log GPU utilization every interval to the specified text file.

set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 OUTPUT_FILE [INTERVAL_SECONDS] [GPU_INDEX]" >&2
  exit 1
fi

OUTPUT_FILE="$1"
INTERVAL="${2:-1}"
GPU_INDEX="${3:-0}"

if ! [[ "$INTERVAL" =~ ^[0-9]+(\.[0-9]+)?$ ]]; then
  echo "Invalid interval: $INTERVAL" >&2
  exit 1
fi
if ! [[ "$GPU_INDEX" =~ ^[0-9]+$ ]]; then
  echo "Invalid GPU index: $GPU_INDEX" >&2
  exit 1
fi

mkdir -p "$(dirname "$OUTPUT_FILE")"

echo "Logging GPU ${GPU_INDEX} utilization to $OUTPUT_FILE every ${INTERVAL}s (Ctrl+C to stop)" >&2

while true; do
  timestamp="$(date --iso-8601=seconds)"
  if util="$(nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader,nounits -i "${GPU_INDEX}" 2>/dev/null)"; then
    printf "%s\t%s\n" "$timestamp" "$util" >>"$OUTPUT_FILE"
  else
    printf "%s\tNaN\n" "$timestamp" >>"$OUTPUT_FILE"
  fi
  sleep "$INTERVAL"
done
