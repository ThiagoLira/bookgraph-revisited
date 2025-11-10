#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

INPUT_PATH="$SCRIPT_DIR/books/Where the Stress Falls (Penguin - Susan Sontag.txt"
CHUNK_SIZE=100
MAX_CONCURRENCY=4
BASE_URL="http://localhost:8080/v1"
API_KEY="test"
MODEL="Qwen/Qwen3-30B-A3B"
MAX_COMPLETION_TOKENS=1000
MAX_CONTEXT_PER_REQUEST=4000
TOKENIZER_NAME="Qwen/Qwen3-30B-A3B"
DEBUG_LIMIT=""

cmd=(
  uv run
  "$SCRIPT_DIR/run_single_file.py"
  "$INPUT_PATH"
  --chunk-size "$CHUNK_SIZE"
  --max-concurrency "$MAX_CONCURRENCY"
  --base-url "$BASE_URL"
  --api-key "$API_KEY"
  --model "$MODEL"
  --max-completion-tokens "$MAX_COMPLETION_TOKENS"
  --max-context-per-request "$MAX_CONTEXT_PER_REQUEST"
  --tokenizer-name "$TOKENIZER_NAME"
)

if [[ -n "$DEBUG_LIMIT" ]]; then
  cmd+=(--debug-limit "$DEBUG_LIMIT")
fi

exec "${cmd[@]}"
