#!/usr/bin/env bash
# Run calibre_citations_pipeline.py against OpenRouter using DeepSeek V3.2 for extraction and metadata agent.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

usage() {
  cat <<'EOF'
Usage: ./pipeline_calibre_openrouter.sh [CALIBRE_LIBRARY_DIR] [OUTPUT_DIR]

Environment:
  OPENROUTER_API_KEY   Required. Read from .env if present.
  OPENROUTER_BASE_URL  Optional. Defaults to https://openrouter.ai/api/v1
  EXTRACT_MODEL        Optional. Defaults to deepseek/deepseek-v3.2
  AGENT_MODEL          Optional. Defaults to deepseek/deepseek-v3.2
  AGENT_MAX_WORKERS    Optional. Defaults to 5
Defaults:
  CALIBRE_LIBRARY_DIR  $HOME/OneDrive/Documents/calibre_goodreads
EOF
}

if [[ "$#" -gt 0 && ( "$1" == "-h" || "$1" == "--help" ) ]]; then
  usage
  exit 0
fi

if [[ -f "$PROJECT_ROOT/.env" ]]; then
  # shellcheck disable=SC1091
  set -a; source "$PROJECT_ROOT/.env"; set +a
fi

if [[ -z "${OPENROUTER_API_KEY:-}" ]]; then
  echo "OPENROUTER_API_KEY is not set. Add it to .env or your shell env." >&2
  exit 1
fi

LIBRARY_DIR="${1:-/Users/thlira/Library/CloudStorage/OneDrive-Pessoal/Documentos/calibre_bookgraph/}"
OUTPUT_DIR="${2:-}"

BASE_URL="${OPENROUTER_BASE_URL:-https://openrouter.ai/api/v1}"
EXTRACT_MODEL="${EXTRACT_MODEL:-deepseek/deepseek-v3.2}"
AGENT_MODEL="${AGENT_MODEL:-deepseek/deepseek-v3.2}"
AGENT_MAX_WORKERS="${AGENT_MAX_WORKERS:-10}"
EXTRACT_CHUNK_SIZE="${EXTRACT_CHUNK_SIZE:-50}"
EXTRACT_MAX_CONTEXT="${EXTRACT_MAX_CONTEXT:-12288}"

CMD=(
  uv run python "$PROJECT_ROOT/calibre_citations_pipeline.py"
  --extract-base-url "$BASE_URL"
  --extract-api-key "$OPENROUTER_API_KEY"
  --extract-model "$EXTRACT_MODEL"
  --extract-chunk-size "$EXTRACT_CHUNK_SIZE"
  --extract-max-context-per-request "$EXTRACT_MAX_CONTEXT"
  --agent-base-url "$BASE_URL"
  --agent-api-key "$OPENROUTER_API_KEY"
  --agent-model "$AGENT_MODEL"
  --agent-max-concurrency "$AGENT_MAX_WORKERS"
#  --only-goodreads-ids "61535"
#  --debug-trace
)

if [[ -n "$OUTPUT_DIR" ]]; then
  CMD+=(--output-dir "$OUTPUT_DIR")
fi

CMD+=("$LIBRARY_DIR")

echo "Running calibre_citations_pipeline.py with OpenRouter + DeepSeek V3.2..."
echo "  Library dir     : $LIBRARY_DIR"
if [[ -n "$OUTPUT_DIR" ]]; then
  echo "  Output dir      : $OUTPUT_DIR"
fi
echo "  Base URL        : $BASE_URL"
echo "  Extract model   : $EXTRACT_MODEL"
echo "  Agent model     : $AGENT_MODEL"
echo "  Agent workers   : $AGENT_MAX_WORKERS"

exec "${CMD[@]}"
