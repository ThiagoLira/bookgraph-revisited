#!/usr/bin/env bash
# Run run_single_file.py with GPU utilization tracking and produce a plot.
# Launches llama-server automatically with matching parameters.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ $# -gt 0 ]] && [[ "$1" == "-h" || "$1" == "--help" ]]; then
  echo "Usage: $0 [INPUT_TXT] [CHUNK_SIZE] [MAX_CONCURRENCY] [MAX_INPUT_TOKENS] [MAX_COMPLETION_TOKENS] [MODEL_PATH] [GPU_LAYERS] [SERVER_BINARY] [INTERVAL] [BATCH_SIZE]" >&2
  echo "" >&2
  echo "All parameters are optional with defaults:" >&2
  echo "  INPUT_TXT             - Path to text file (default: test_book_subset.txt)" >&2
  echo "  CHUNK_SIZE            - Sentences per chunk (default: 50)" >&2
  echo "  MAX_CONCURRENCY       - Max concurrent requests (default: 20)" >&2
  echo "  MAX_INPUT_TOKENS      - Max input tokens (default: 4096)" >&2
  echo "  MAX_COMPLETION_TOKENS - Max completion tokens (default: 2048)" >&2
  echo "  MODEL_PATH            - GGUF model path (default: Qwen3-30B-A3B-Q5_K_S.gguf)" >&2
  echo "  GPU_LAYERS            - GPU layers, -1 for all (default: -1)" >&2
  echo "  SERVER_BINARY         - llama-server binary (default: llama-server)" >&2
  echo "  INTERVAL              - GPU monitoring interval (default: 1)" >&2
  echo "  BATCH_SIZE            - Batch size for parallel token processing (default: 2048)" >&2
  echo "" >&2
  echo "Examples:" >&2
  echo "  $0                    # Quick test with all defaults" >&2
  echo "  $0 mybook.txt         # Use custom book, other defaults" >&2
  echo "  $0 mybook.txt 50 40   # Custom book, 40 concurrency" >&2
  echo "" >&2
  echo "Server settings:" >&2
  echo "  --repeat-penalty 1.2, --repeat-last-n 128" >&2
  echo "  --presence-penalty 0.4, --frequency-penalty 0.6" >&2
  echo "  -fa on, CUDA_VISIBLE_DEVICES=0" >&2
  exit 0
fi

INPUT_PATH="${1:-$SCRIPT_DIR/test_book_subset.txt}"
CHUNK_SIZE="${2:-50}"
MAX_CONCURRENCY="${3:-20}"
MAX_INPUT_TOKENS="${4:-4096}"
MAX_COMPLETION_TOKENS="${5:-2048}"
MODEL_PATH="${6:-/home/thiago/models/Qwen3-30B-A3B-Q5_K_S.gguf}"
GPU_LAYERS="${7:--1}"
SERVER_BINARY="${8:-llama-server}"
INTERVAL="${9:-1}"
BATCH_SIZE="${10:-2048}"
RUN_TS="$(date +%Y%m%d-%H%M%S)"
OUTPUT_DIR="$SCRIPT_DIR/profile_runs/$RUN_TS"
mkdir -p "$OUTPUT_DIR"

GPU_LOG="$OUTPUT_DIR/${MAX_CONCURRENCY}_${CHUNK_SIZE}_${MAX_INPUT_TOKENS}_${MAX_COMPLETION_TOKENS}.log"
PLOT_PATH="$OUTPUT_DIR/gpu_utilization.png"
RUN_LOG="$OUTPUT_DIR/run_single_file.log"
SERVER_LOG="$OUTPUT_DIR/llama_server.log"

# Calculate context sizes
# Context per request = input budget + output budget
# Total server context = context_per_request * concurrency (llama.cpp divides by -np)
CONTEXT_PER_REQUEST=$((MAX_INPUT_TOKENS + MAX_COMPLETION_TOKENS))
TOTAL_CONTEXT_SIZE=$((CONTEXT_PER_REQUEST * MAX_CONCURRENCY))

# Server configuration
SERVER_HOST="127.0.0.1"
SERVER_PORT="8080"
SERVER_URL="http://${SERVER_HOST}:${SERVER_PORT}"

# Launch llama-server
echo "Starting llama-server..." >&2
echo "  Model: $MODEL_PATH" >&2
echo "  Total context size (-c): $TOTAL_CONTEXT_SIZE" >&2
echo "  Context per request: $CONTEXT_PER_REQUEST (input budget: $MAX_INPUT_TOKENS + output budget: $MAX_COMPLETION_TOKENS)" >&2
echo "  Parallel requests (-np): $MAX_CONCURRENCY" >&2
echo "  Effective context per slot: $CONTEXT_PER_REQUEST (total / np)" >&2
echo "  Batch size (-b): $BATCH_SIZE" >&2
echo "  GPU layers (-ngl): $GPU_LAYERS" >&2
echo "  Log: $SERVER_LOG" >&2

CUDA_VISIBLE_DEVICES=0 "$SERVER_BINARY" \
  -m "$MODEL_PATH" \
  -c "$TOTAL_CONTEXT_SIZE" \
  -np "$MAX_CONCURRENCY" \
  -n "$MAX_COMPLETION_TOKENS" \
  -b "$BATCH_SIZE" \
  -ngl "$GPU_LAYERS" \
  -ctk q4_0 \
  -ctv q4_0 \
  --host "$SERVER_HOST" \
  --port "$SERVER_PORT" \
  --no-webui \
  --repeat-penalty 1.2 \
  --repeat-last-n 128 \
  --presence-penalty 0.4 \
  --frequency-penalty 0.6 \
  >"$SERVER_LOG" 2>&1 &
SERVER_PID=$!

# Wait for server to be ready
echo "Waiting for server to be ready..." >&2
MAX_WAIT=120
WAIT_COUNT=0
while [[ $WAIT_COUNT -lt $MAX_WAIT ]]; do
  HEALTH_RESPONSE=$(curl -s "$SERVER_URL/health" 2>/dev/null || echo "")
  if echo "$HEALTH_RESPONSE" | grep -q '"status":"ok"'; then
    echo "Server is ready!" >&2
    break
  fi
  if [[ $((WAIT_COUNT % 10)) -eq 0 ]] && [[ $WAIT_COUNT -gt 0 ]]; then
    echo "  Still waiting... (${WAIT_COUNT}s elapsed)" >&2
  fi
  sleep 1
  WAIT_COUNT=$((WAIT_COUNT + 1))
done

if [[ $WAIT_COUNT -ge $MAX_WAIT ]]; then
  echo "Server failed to start within ${MAX_WAIT}s. Check $SERVER_LOG" >&2
  kill "$SERVER_PID" >/dev/null 2>&1 || true
  exit 1
fi

echo "Starting GPU monitor (GPU 1) -> $GPU_LOG" >&2
bash "$SCRIPT_DIR/monitor_gpu_util.sh" "$GPU_LOG" "$INTERVAL" &
MONITOR_PID=$!

cleanup() {
  echo "Cleaning up..." >&2
  if ps -p "$MONITOR_PID" >/dev/null 2>&1; then
    kill "$MONITOR_PID" >/dev/null 2>&1 || true
  fi
  if ps -p "$SERVER_PID" >/dev/null 2>&1; then
    echo "Stopping llama-server..." >&2
    kill "$SERVER_PID" >/dev/null 2>&1 || true
    # Give it a moment to shut down gracefully
    sleep 2
    # Force kill if still running
    if ps -p "$SERVER_PID" >/dev/null 2>&1; then
      kill -9 "$SERVER_PID" >/dev/null 2>&1 || true
    fi
  fi
}
trap cleanup EXIT

echo "Running run_single_file.py..." >&2
START_TIME="$(date +%s)"
set +e
uv run "$SCRIPT_DIR/run_single_file.py" "$INPUT_PATH" \
  --chunk-size "$CHUNK_SIZE" \
  --max-concurrency "$MAX_CONCURRENCY" \
  --max-context-per-request "$CONTEXT_PER_REQUEST" \
  --max-completion-tokens "$MAX_COMPLETION_TOKENS" \
  --base-url "${SERVER_URL}/v1" \
  2>&1 | tee "$RUN_LOG"
RUN_STATUS=${PIPESTATUS[0]}
set -e
END_TIME="$(date +%s)"
TOTAL_SECONDS=$((END_TIME - START_TIME))

cleanup
trap - EXIT

if [[ $RUN_STATUS -ne 0 ]]; then
  echo "run_single_file.py failed (status $RUN_STATUS). See $RUN_LOG" >&2
  exit $RUN_STATUS
fi

echo "Generating GPU utilization plot -> $PLOT_PATH" >&2
gnuplot <<EOF
set terminal pngcairo size 1280,720
set output "$PLOT_PATH"
set title "GPU 1 Utilization - $(basename "$INPUT_PATH") (${TOTAL_SECONDS}s, ctx:${CONTEXT_PER_REQUEST}, conc:${MAX_CONCURRENCY}, chunk:${CHUNK_SIZE})"
set xdata time
set timefmt "%Y-%m-%dT%H:%M:%S%z"
set format x "%H:%M:%S"
set xlabel "Time"
set ylabel "Utilization (%)"
set yrange [0:100]
set grid
plot "$GPU_LOG" using 1:2 with lines title "GPU 1"
EOF

echo "Artifacts saved in $OUTPUT_DIR" >&2
echo "  - GPU log: $GPU_LOG"
echo "  - Plot: $PLOT_PATH"
echo "  - run_single_file output: $RUN_LOG"
echo "  - llama-server log: $SERVER_LOG"
