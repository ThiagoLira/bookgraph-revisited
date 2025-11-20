#!/usr/bin/env bash
set -euo pipefail
. .venv/bin/activate
python -m cProfile -o profiling/mock_profile.prof \
  process_citations_pipeline.py books_samples \
  --pattern mock_short.txt \
  --extract-base-url http://127.0.0.1:8080/v1 \
  --agent-base-url http://127.0.0.1:8080/v1 \
  --extract-api-key test --agent-api-key test \
  --extract-model Qwen/Qwen3-30B-A3B \
  --agent-model Qwen/Qwen3-30B-A3B \
  --agent-trace
