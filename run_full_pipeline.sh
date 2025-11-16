#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

INPUT_DIR="$SCRIPT_DIR/books"
EXTRACT_URL="https://openrouter.ai/api/v1"
AGENT_URL="https://openrouter.ai/api/v1"

if [[ -f "$SCRIPT_DIR/.env" ]]; then
  # shellcheck disable=SC1090
  set -a; source "$SCRIPT_DIR/.env"; set +a
fi

if [[ -z "${OPENROUTER_API_KEY:-}" ]]; then
  echo "OPENROUTER_API_KEY is not set. Export it before running this script." >&2
  exit 1
fi

uv run python "$SCRIPT_DIR/process_citations_pipeline.py" \
  --extract-base-url "$EXTRACT_URL" \
  --extract-api-key "$OPENROUTER_API_KEY" \
  --agent-base-url "$AGENT_URL" \
  --agent-api-key "$OPENROUTER_API_KEY" \
  "$INPUT_DIR"
