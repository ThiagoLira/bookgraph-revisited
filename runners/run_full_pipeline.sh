#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

INPUT_DIR="$PROJECT_ROOT/books"
EXTRACT_URL="https://openrouter.ai/api/v1"
AGENT_URL="https://openrouter.ai/api/v1"

if [[ -f "$PROJECT_ROOT/.env" ]]; then
  # shellcheck disable=SC1090
  set -a; source "$PROJECT_ROOT/.env"; set +a
fi

if [[ -z "${OPENROUTER_API_KEY:-}" ]]; then
  echo "OPENROUTER_API_KEY is not set. Export it before running this script." >&2
  exit 1
fi

uv run python "$PROJECT_ROOT/process_citations_pipeline.py" \
  --extract-base-url "$EXTRACT_URL" \
  --extract-api-key "$OPENROUTER_API_KEY" \
  --agent-base-url "$AGENT_URL" \
  --agent-api-key "$OPENROUTER_API_KEY" \
  "$INPUT_DIR"
