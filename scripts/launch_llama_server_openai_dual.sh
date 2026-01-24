#!/usr/bin/env bash
# Launch llama-server for a large OpenAI-style model on two GPUs.
# Args (all optional):
#   1: MODEL_PATH (default: /home/thiago/models/gpt-oss-120b-Q5_K_S-00001-of-00002.gguf)
#   2: MAX_CONCURRENCY (-np, default: 20)
#   3: MAX_INPUT_TOKENS (default: 4096)
#   4: MAX_COMPLETION_TOKENS (default: 1024)
#   5: BATCH_SIZE (-b, default: 2048)
#   6: UBATCH_SIZE (-ub, default: 512)
#   7: GPU_LAYERS (-ngl, default: -1)
#   8: HOST (default: 127.0.0.1)
#   9: PORT (default: 8080)
#  10: SERVER_BINARY (default: llama-server)
#  11: TENSOR_SPLIT weights (default: 50,50)
#  12: MAIN_GPU index (default: 0)
#  13: PIN_HEAVY_TENSORS (1 to pin token/output to MAIN_GPU, default: 1)

set -euo pipefail

MODEL_PATH="${1:-/home/thiago/models/gpt-oss-120b-Q5_K_S-00001-of-00002.gguf}"
MAX_CONCURRENCY="${2:-1}"
MAX_INPUT_TOKENS="${3:-2096}"
MAX_COMPLETION_TOKENS="${4:-1024}"
BATCH_SIZE="${5:-2048}"
UBATCH_SIZE="${6:-512}"
GPU_LAYERS="${7:-25}"
HOST="${8:-127.0.0.1}"
PORT="${9:-8080}"
SERVER_BINARY="${10:-llama-server}"
TENSOR_SPLIT="${11:-55,45}"
MAIN_GPU="${12:-0}"
PIN_HEAVY_TENSORS="${13:-1}"

CONTEXT_PER_REQUEST=$((MAX_INPUT_TOKENS + MAX_COMPLETION_TOKENS))
TOTAL_CONTEXT_SIZE=$((CONTEXT_PER_REQUEST * MAX_CONCURRENCY))

CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-0,1}"
IFS=',' read -r -a GPU_IDS <<< "$CUDA_VISIBLE_DEVICES"
if [[ "${#GPU_IDS[@]}" -ne 2 ]]; then
  echo "Expected exactly two GPUs in CUDA_VISIBLE_DEVICES (e.g. 0,1). Current: ${CUDA_VISIBLE_DEVICES}" >&2
  exit 1
fi

echo "Launching llama-server across GPUs ${CUDA_VISIBLE_DEVICES}..." >&2
echo "  Model path            : ${MODEL_PATH}" >&2
echo "  Total context (-c)    : ${TOTAL_CONTEXT_SIZE} tokens" >&2
echo "  Concurrency (-np)     : ${MAX_CONCURRENCY}" >&2
echo "  Context / request     : ${CONTEXT_PER_REQUEST} (input ${MAX_INPUT_TOKENS} + output ${MAX_COMPLETION_TOKENS})" >&2
echo "  Batch size (-b)       : ${BATCH_SIZE}" >&2
echo "  Micro-batch (-ub)     : ${UBATCH_SIZE}" >&2
echo "  GPU layers (-ngl)     : ${GPU_LAYERS}" >&2
echo "  Split mode            : row (tensor parallel)" >&2
echo "  Tensor split weights  : ${TENSOR_SPLIT}" >&2
echo "  Main GPU              : ${MAIN_GPU}" >&2
echo "  Host:Port             : ${HOST}:${PORT}" >&2

SERVER_ARGS=(
  -m "${MODEL_PATH}"
  -c "${TOTAL_CONTEXT_SIZE}"
  -np "${MAX_CONCURRENCY}"
  -n "${MAX_COMPLETION_TOKENS}"
  -b "${BATCH_SIZE}"
  -ub "${UBATCH_SIZE}"
  -ngl "${GPU_LAYERS}"
  -sm row
  --tensor-split "${TENSOR_SPLIT}"
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

if [[ "${PIN_HEAVY_TENSORS}" != "0" ]]; then
  SERVER_ARGS+=(
    --override-tensor "token_embd.weight=CUDA${MAIN_GPU}"
    --override-tensor "output.weight=CUDA${MAIN_GPU}"
  )
fi

echo "Command: CUDA_VISIBLE_DEVICES=${CUDA_VISIBLE_DEVICES} ${SERVER_BINARY} ${SERVER_ARGS[*]}" >&2
CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES}" "${SERVER_BINARY}" "${SERVER_ARGS[@]}"
