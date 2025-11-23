#!/usr/bin/env bash
# Frontend for running run_single_file.py against OpenRouter (or any OpenAI-compatible API).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Load .env if present so OPENROUTER_API_KEY is available
if [[ -f "$PROJECT_ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$PROJECT_ROOT/.env"
  set +a
fi

if [[ -z "${OPENROUTER_API_KEY:-}" ]]; then
  echo "OPENROUTER_API_KEY is not set. Add it to .env or your shell env." >&2
  exit 1
fi

if [[ $# -gt 0 ]] && [[ "$1" == "-h" || "$1" == "--help" ]]; then
  cat <<'EOF'
Usage: ./pipeline_single_openrouter.sh [INPUT_TXT] [CHUNK_SIZE] [MAX_CONCURRENCY] [MAX_CONTEXT] [MAX_COMPLETION] [MODEL] [BASE_URL]

Defaults:
  INPUT_TXT       books/susan_sample.txt
  CHUNK_SIZE      50
  MAX_CONCURRENCY 20
  MAX_CONTEXT     6144
  MAX_COMPLETION  2048
  MODEL           qwen/qwen3-next-80b-a3b-instruct
  BASE_URL        https://openrouter.ai/api/v1

Reads OPENROUTER_API_KEY from the environment (load via .env automatically).
EOF
  exit 0
fi

INPUT_PATH="${1:-$PROJECT_ROOT/books/susan_sample.txt}"
CHUNK_SIZE="${2:-50}"
MAX_CONCURRENCY="${3:-20}"
MAX_CONTEXT="${4:-6144}"
MAX_COMPLETION="${5:-2048}"
MODEL_NAME="${6:-qwen/qwen3-next-80b-a3b-instruct}"
BASE_URL="${7:-https://openrouter.ai/api/v1}"

RUN_TS="$(date +%Y%m%d-%H%M%S)"
OUTPUT_DIR="$PROJECT_ROOT/openrouter_runs/$RUN_TS"
mkdir -p "$OUTPUT_DIR"
RUN_LOG="$OUTPUT_DIR/run_single_file.log"

echo "Running run_single_file.py against $BASE_URL" >&2
echo "  Input file:        $INPUT_PATH" >&2
echo "  Chunk size:        $CHUNK_SIZE" >&2
echo "  Max concurrency:   $MAX_CONCURRENCY" >&2
echo "  Max context:       $MAX_CONTEXT" >&2
echo "  Max completion:    $MAX_COMPLETION" >&2
echo "  Model:             $MODEL_NAME" >&2
echo "  Output directory:  $OUTPUT_DIR" >&2

set +e
uv run "$PROJECT_ROOT/run_single_file.py" "$INPUT_PATH" \
  --chunk-size "$CHUNK_SIZE" \
  --max-concurrency "$MAX_CONCURRENCY" \
  --max-context-per-request "$MAX_CONTEXT" \
  --max-completion-tokens "$MAX_COMPLETION" \
  --base-url "$BASE_URL" \
  --api-key "$OPENROUTER_API_KEY" \
  --model "$MODEL_NAME" \
  2>&1 | tee "$RUN_LOG"
RUN_STATUS=${PIPESTATUS[0]}
set -e

if [[ $RUN_STATUS -ne 0 ]]; then
  echo "run_single_file.py failed (status $RUN_STATUS). See $RUN_LOG" >&2
  exit $RUN_STATUS
fi

echo "Artifacts saved in $OUTPUT_DIR" >&2
echo "  - run_single_file output: $RUN_LOG" >&2
