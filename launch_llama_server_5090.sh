#!/usr/bin/env bash
# Launch llama-server on a single RTX 5090 (CUDA_VISIBLE_DEVICES=0 by default).
# Args:
#   1: MODEL_PATH (default: /home/thiago/models/Qwen3-30B-A3B-Q5_K_S.gguf)
#   2: MAX_CONCURRENCY / slots (-np)
#   3: MAX_INPUT_TOKENS
#   4: MAX_COMPLETION_TOKENS
#   5: BATCH_SIZE (-b)
#   6: UBATCH_SIZE (-ub)
#   7: GPU_LAYERS (-ngl)
#   8: HOST
#   9: PORT
#  10: SERVER_BINARY
set -euo pipefail

MODEL_PATH="${1:-/home/thiago/models/Qwen3-30B-A3B-Q5_K_S.gguf}"
MAX_CONCURRENCY="${2:-20}"
MAX_INPUT_TOKENS="${3:-2000}"
MAX_COMPLETION_TOKENS="${4:-1000}"
BATCH_SIZE="${5:-2048}"
UBATCH_SIZE="${6:-512}"
GPU_LAYERS="${7:--1}"
HOST="${8:-127.0.0.1}"
PORT="${9:-8080}"
SERVER_BINARY="${10:-llama-server}"

CONTEXT_PER_REQUEST=$((MAX_INPUT_TOKENS + MAX_COMPLETION_TOKENS))
TOTAL_CONTEXT_SIZE=$((CONTEXT_PER_REQUEST * MAX_CONCURRENCY))

CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-0}"
echo "Launching llama-server on GPU ${CUDA_VISIBLE_DEVICES} (single GPU)..." >&2
echo "  Model path            : ${MODEL_PATH}" >&2
echo "  Total context (-c)    : ${TOTAL_CONTEXT_SIZE} tokens" >&2
echo "  Concurrency (-np)     : ${MAX_CONCURRENCY}" >&2
echo "  Context / request     : ${CONTEXT_PER_REQUEST} (input ${MAX_INPUT_TOKENS} + output ${MAX_COMPLETION_TOKENS})" >&2
echo "  Batch size (-b)       : ${BATCH_SIZE}" >&2
echo "  Micro-batch (-ub)     : ${UBATCH_SIZE}" >&2
echo "  GPU layers (-ngl)     : ${GPU_LAYERS}" >&2
echo "  Host:Port             : ${HOST}:${PORT}" >&2

SERVER_ARGS=(
  -m "${MODEL_PATH}"
  -c "${TOTAL_CONTEXT_SIZE}"
  -np "${MAX_CONCURRENCY}"
  -n "${MAX_COMPLETION_TOKENS}"
  -b "${BATCH_SIZE}"
  -ub "${UBATCH_SIZE}"
  -ngl "${GPU_LAYERS}"
  --host "${HOST}"
  --port "${PORT}"
  --no-webui
  --repeat-penalty 1.2
  --repeat-last-n 128
  --presence-penalty 0.4
  --frequency-penalty 0.6
  -fa on
  --chat-template-file nothink.jinja
  --jinja
)

CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES}" "${SERVER_BINARY}" "${SERVER_ARGS[@]}"
