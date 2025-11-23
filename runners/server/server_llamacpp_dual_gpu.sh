#!/usr/bin/env bash
# Launch llama-server with Qwen3-30B-A3B sharded across two GPUs using row-split tensor parallelism.
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
#  11: TENSOR_SPLIT weights (e.g. "70,30")
#  12: MAIN_GPU index
#  13: PIN_HEAVY_TENSORS flag (1 = pin token/output tensors to main GPU)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

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
TENSOR_SPLIT="${11:-100,0}"
MAIN_GPU="${12:-0}"
PIN_HEAVY_TENSORS="${13:-1}"

CONTEXT_PER_REQUEST=$((MAX_INPUT_TOKENS + MAX_COMPLETION_TOKENS))
TOTAL_CONTEXT_SIZE=$((CONTEXT_PER_REQUEST * MAX_CONCURRENCY))

CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-0,1}"
IFS=',' read -r -a GPU_IDS <<< "$CUDA_VISIBLE_DEVICES"
if [[ "${#GPU_IDS[@]}" -ne 2 ]]; then
  echo "Expected exactly two GPUs in CUDA_VISIBLE_DEVICES (e.g. 0,1). Current value: ${CUDA_VISIBLE_DEVICES}" >&2
  exit 1
fi

echo "Launching llama-server with Qwen3-30B-A3B across GPUs ${CUDA_VISIBLE_DEVICES}..." >&2
echo "  Model path            : ${MODEL_PATH}" >&2
echo "  Total context (-c)    : ${TOTAL_CONTEXT_SIZE} tokens" >&2
echo "  Concurrency (-np)     : ${MAX_CONCURRENCY}" >&2
echo "  Context / request     : ${CONTEXT_PER_REQUEST} (input ${MAX_INPUT_TOKENS} + output ${MAX_COMPLETION_TOKENS})" >&2
echo "  Host:Port             : ${HOST}:${PORT}" >&2
echo "  Split mode            : row (2-way tensor parallelism)" >&2
echo "  Tensor split weights  : ${TENSOR_SPLIT}" >&2
echo "  Main GPU              : ${MAIN_GPU}" >&2

SERVER_ARGS=(
  -m "${MODEL_PATH}"
  -c "${TOTAL_CONTEXT_SIZE}"
  -np "${MAX_CONCURRENCY}"
  -n "${MAX_COMPLETION_TOKENS}"
  -b "${BATCH_SIZE}"
  -ub "${UBATCH_SIZE}"
  -ngl "${GPU_LAYERS}"
  -sm row
  --main-gpu "${MAIN_GPU}"
  --host "${HOST}"
  --port "${PORT}"
  --no-webui
  --repeat-penalty 1.2
  --repeat-last-n 128
  --presence-penalty 0.4
  --frequency-penalty 0.6
  -fa on
  --jinja
)

if [[ -n "${TENSOR_SPLIT}" ]]; then
  SERVER_ARGS+=(--tensor-split "${TENSOR_SPLIT}")
fi

if [[ "${PIN_HEAVY_TENSORS}" != "0" ]]; then
  SERVER_ARGS+=(
    --override-tensor "token_embd.weight=CUDA${MAIN_GPU}"
    --override-tensor "output.weight=CUDA${MAIN_GPU}"
  )
fi

CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES}" "${SERVER_BINARY}" "${SERVER_ARGS[@]}"
