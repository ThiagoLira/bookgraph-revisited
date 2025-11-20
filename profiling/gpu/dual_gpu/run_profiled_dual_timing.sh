#!/usr/bin/env bash
# Minimal dual-GPU profiler that only measures wall-clock duration per concurrency.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

usage() {
  cat <<EOF >&2
Usage: $0 [INPUT_TXT] [CONCURRENCY_LIST] [CHUNK_SIZE] [MAX_INPUT_TOKENS] [MAX_COMPLETION_TOKENS] [MODEL_PATH] [GPU_LAYERS] [SERVER_BINARY] [BATCH_SIZE] [UBATCH_SIZE] [TENSOR_SPLIT] [MAIN_GPU]

Defaults:
  INPUT_TXT         - \$REPO_ROOT/books_samples/freud.txt
  CONCURRENCY_LIST  - 10,20,30
  CHUNK_SIZE        - 50
  MAX_INPUT_TOKENS  - 4096
  MAX_COMPLETION    - 2048
  MODEL_PATH        - /home/thiago/models/Qwen3-30B-A3B-Q5_K_S.gguf
  GPU_LAYERS        - -1
  SERVER_BINARY     - llama-server
  BATCH_SIZE        - 2048
  UBATCH_SIZE       - 512
  TENSOR_SPLIT      - 70,30
  MAIN_GPU          - 0

Example:
  $0 "\$PWD/books_samples/sandel.txt" 12,20,28
EOF
}

if [[ ${1:-} == "-h" || ${1:-} == "--help" ]]; then
  usage
  exit 0
fi

INPUT_PATH="${1:-$REPO_ROOT/books_samples/freud.txt}"
CONCURRENCY_ARG="${2:-10,20,30}"
CHUNK_SIZE="${3:-200}"
MAX_INPUT_TOKENS="${4:-8000}"
MAX_COMPLETION_TOKENS="${5:-2048}"
MODEL_PATH="${6:-/home/thiago/models/Qwen3-30B-A3B-Q5_K_S.gguf}"
GPU_LAYERS="${7:--1}"
SERVER_BINARY="${8:-llama-server}"
BATCH_SIZE="${9:-2048}"
UBATCH_SIZE="${10:-512}"
TENSOR_SPLIT="${11:-100,0}"
MAIN_GPU="${12:-0}"

if [[ ! -f "$INPUT_PATH" ]]; then
  echo "Input file not found: $INPUT_PATH" >&2
  exit 1
fi

IFS=' ' read -r -a CONCURRENCY_VALUES <<<"$(echo "$CONCURRENCY_ARG" | tr ',' ' ')"
if [[ "${#CONCURRENCY_VALUES[@]}" -eq 0 ]]; then
  echo "No concurrency values parsed from '$CONCURRENCY_ARG'" >&2
  exit 1
fi

RUN_TS="$(date +%Y%m%d-%H%M%S)"
BASE_OUTPUT="$SCRIPT_DIR/profile_runs/${RUN_TS}_timings"
mkdir -p "$BASE_OUTPUT"

SERVER_HOST="127.0.0.1"
SERVER_PORT="8080"
SERVER_URL="http://${SERVER_HOST}:${SERVER_PORT}"

SUMMARY_FILE="$BASE_OUTPUT/timings.csv"
echo "concurrency,duration_seconds" >"$SUMMARY_FILE"

cleanup() {
  if [[ -n "${SERVER_PID:-}" ]] && ps -p "$SERVER_PID" >/dev/null 2>&1; then
    kill "$SERVER_PID" >/dev/null 2>&1 || true
    sleep 2
    if ps -p "$SERVER_PID" >/dev/null 2>&1; then
      kill -9 "$SERVER_PID" >/dev/null 2>&1 || true
    fi
  fi
}
trap cleanup EXIT

for CONCURRENCY in "${CONCURRENCY_VALUES[@]}"; do
  if ! [[ "$CONCURRENCY" =~ ^[0-9]+$ ]]; then
    echo "Skipping invalid concurrency value: $CONCURRENCY" >&2
    continue
  fi

  CONTEXT_PER_REQUEST=$((MAX_INPUT_TOKENS + MAX_COMPLETION_TOKENS))
  TOTAL_CONTEXT_SIZE=$((CONTEXT_PER_REQUEST * CONCURRENCY))

  EXP_DIR="$BASE_OUTPUT/np_${CONCURRENCY}"
  mkdir -p "$EXP_DIR"
  RUN_LOG="$EXP_DIR/run_single_file.log"
  SERVER_LOG="$EXP_DIR/llama_server.log"

  echo ""
  echo "=== Timing concurrency ${CONCURRENCY} (context ${TOTAL_CONTEXT_SIZE}) ===" >&2

  CUDA_VISIBLE_DEVICES=0,1 "$SERVER_BINARY" \
    -m "$MODEL_PATH" \
    -c "$TOTAL_CONTEXT_SIZE" \
    -np "$CONCURRENCY" \
    -n "$MAX_COMPLETION_TOKENS" \
    -b "$BATCH_SIZE" \
    -ub "$UBATCH_SIZE" \
    -ngl "$GPU_LAYERS" \
    -ctk q4_0 \
    -ctv q4_0 \
    -sm row \
    --main-gpu "$MAIN_GPU" \
    --tensor-split "$TENSOR_SPLIT" \
    --override-tensor "token_embd.weight=CUDA${MAIN_GPU}" \
    --override-tensor "output.weight=CUDA${MAIN_GPU}" \
    --host "$SERVER_HOST" \
    --port "$SERVER_PORT" \
    --no-webui \
    --repeat-penalty 1.2 \
    --repeat-last-n 128 \
    --presence-penalty 0.4 \
    --frequency-penalty 0.6 \
    --jinja \
    >"$SERVER_LOG" 2>&1 &
  SERVER_PID=$!

  MAX_WAIT=150
  WAIT_COUNT=0
  until curl -sf "$SERVER_URL/health" >/dev/null 2>&1; do
    sleep 1
    WAIT_COUNT=$((WAIT_COUNT + 1))
    if [[ $WAIT_COUNT -ge $MAX_WAIT ]]; then
      echo "Server failed to start for concurrency $CONCURRENCY (see $SERVER_LOG)" >&2
      kill "$SERVER_PID" >/dev/null 2>&1 || true
      continue 2
    fi
  done

  START_TIME="$(date +%s)"
  set +e
  uv run "$REPO_ROOT/run_single_file.py" "$INPUT_PATH" \
    --chunk-size "$CHUNK_SIZE" \
    --max-concurrency "$CONCURRENCY" \
    --max-context-per-request "$CONTEXT_PER_REQUEST" \
    --max-completion-tokens "$MAX_COMPLETION_TOKENS" \
    --base-url "${SERVER_URL}/v1" \
    2>&1 | tee "$RUN_LOG"
  RUN_STATUS=${PIPESTATUS[0]}
  set -e
  END_TIME="$(date +%s)"
  DURATION=$((END_TIME - START_TIME))

  cleanup
  SERVER_PID=

  if [[ $RUN_STATUS -ne 0 ]]; then
    echo "run_single_file.py failed for concurrency $CONCURRENCY (see $RUN_LOG)" >&2
    continue
  fi

  echo "${CONCURRENCY},${DURATION}" >>"$SUMMARY_FILE"
  echo "  Duration: ${DURATION}s" >&2
done

trap - EXIT

echo ""
echo "Timing sweep complete. Summary -> $SUMMARY_FILE" >&2
