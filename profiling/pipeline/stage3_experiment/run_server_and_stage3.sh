#!/usr/bin/env bash
# Orchestrate: launch local llama-server on a single 5090, then run stage-3 agent experiment.
# Reads MODEL_PATH (arg or env) and reuses it for the server; agent hits the local server.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

MODEL_PATH="${1:-${MODEL_PATH:-}}"
if [[ -z "$MODEL_PATH" ]]; then
  echo "Usage: MODEL_PATH=/path/to/model.gguf $0 [MODEL_PATH] [AGENT_MODEL_ID]" >&2
  echo "Example: MODEL_PATH=/home/thiago/models/Qwen3-30B-A3B-Q5_K_S.gguf $0" >&2
  exit 1
fi

AGENT_MODEL="${2:-${AGENT_MODEL:-Qwen/Qwen3-30B-A3B}}"

# Server defaults (override via env)
MAX_CONCURRENCY="${MAX_CONCURRENCY:-20}"
MAX_INPUT_TOKENS="${MAX_INPUT_TOKENS:-2000}"
MAX_COMPLETION_TOKENS="${MAX_COMPLETION_TOKENS:-1000}"
BATCH_SIZE="${BATCH_SIZE:-2048}"
UBATCH_SIZE="${UBATCH_SIZE:-512}"
GPU_LAYERS="${GPU_LAYERS:--1}"
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8080}"
SERVER_BINARY="${SERVER_BINARY:-llama-server}"
CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-0}"

SERVER_LOG="$SCRIPT_DIR/server_${PORT}.log"
echo "Starting llama-server -> $SERVER_LOG" >&2
CUDA_VISIBLE_DEVICES="$CUDA_VISIBLE_DEVICES" \
  "$REPO_ROOT/launch_llama_server_5090.sh" \
  "$MODEL_PATH" \
  "$MAX_CONCURRENCY" \
  "$MAX_INPUT_TOKENS" \
  "$MAX_COMPLETION_TOKENS" \
  "$BATCH_SIZE" \
  "$UBATCH_SIZE" \
  "$GPU_LAYERS" \
  "$HOST" \
  "$PORT" \
  "$SERVER_BINARY" \
  >"$SERVER_LOG" 2>&1 &
SERVER_PID=$!

cleanup() {
  if ps -p "$SERVER_PID" >/dev/null 2>&1; then
    echo "Stopping llama-server (pid $SERVER_PID)" >&2
    kill "$SERVER_PID" >/dev/null 2>&1 || true
    sleep 2
    if ps -p "$SERVER_PID" >/dev/null 2>&1; then
      kill -9 "$SERVER_PID" >/dev/null 2>&1 || true
    fi
  fi
}
trap cleanup EXIT

SERVER_URL="http://${HOST}:${PORT}/v1"
echo "Waiting for server at ${SERVER_URL}/health ..." >&2
for _ in {1..120}; do
  if curl -s "${SERVER_URL%/v1}/health" 2>/dev/null | grep -q '"status":"ok"'; then
    echo "Server is ready." >&2
    break
  fi
  sleep 1
done

echo "Running stage-3 agent experiment against $SERVER_URL using model id '$AGENT_MODEL'." >&2
AGENT_BASE_URL="$SERVER_URL" \
AGENT_API_KEY="${AGENT_API_KEY:-test}" \
AGENT_MODEL="$AGENT_MODEL" \
  "$SCRIPT_DIR/run_stage3_local.sh"

echo "Done. Logs: $SERVER_LOG" >&2
