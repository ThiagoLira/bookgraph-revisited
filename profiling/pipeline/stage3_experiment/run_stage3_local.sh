#!/usr/bin/env bash
# Run only stage 3 (Goodreads agent) using local inference defaults.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Inputs (preprocessed citations from stage 2)
PRE_DIR="${PRE_DIR:-$SCRIPT_DIR/inputs/preprocessed_extracted_citations}"
PATTERN="${PATTERN:-*.json}"

# Outputs
OUTPUT_DIR="${OUTPUT_DIR:-$SCRIPT_DIR/outputs/final_citations_metadata_goodreads}"

# Agent (local llama.cpp/OpenAI-compatible server)
AGENT_BASE_URL="${AGENT_BASE_URL:-http://127.0.0.1:8080/v1}"
AGENT_API_KEY="${AGENT_API_KEY:-test}"
AGENT_MODEL="${AGENT_MODEL:-Qwen/Qwen3-30B-A3B}"
AGENT_MAX_WORKERS="${AGENT_MAX_WORKERS:-5}"

# Toggle trace logging by exporting TRACE_AGENT=true
TRACE_FLAG=""
if [[ "${TRACE_AGENT:-false}" == "true" ]]; then
  TRACE_FLAG="--agent-trace"
fi

uv run python "$SCRIPT_DIR/run_agent_stage3.py" \
  --pre-dir "$PRE_DIR" \
  --output-dir "$OUTPUT_DIR" \
  --pattern "$PATTERN" \
  --agent-base-url "$AGENT_BASE_URL" \
  --agent-api-key "$AGENT_API_KEY" \
  --agent-model "$AGENT_MODEL" \
  --agent-max-workers "$AGENT_MAX_WORKERS" \
  $TRACE_FLAG
