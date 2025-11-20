#!/usr/bin/env bash
# Benchmark direct Goodreads FTS queries without involving the agent.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNNER=(python "$SCRIPT_DIR/query_goodreads.py")

measure() {
  local label="$1"
  shift
  echo "=== $label ==="
  local start
  start="$(date +%s.%N)"
  local output
  if ! output=$("${RUNNER[@]}" "$@" 2>&1); then
    echo "$output"
    return 1
  fi
  local end
  end="$(date +%s.%N)"
  local duration
  duration=$(python - <<'PY' "$start" "$end"
import sys
start, end = map(float, sys.argv[1:])
print(f"{end - start:.3f}")
PY
)
  echo "$output"
  printf "Duration: %ss\n\n" "$duration"
}

measure "Exact title" --title "The Hero With a Thousand Faces" --limit 3 --quiet
measure "Author only" --author "Sigmund Freud" --limit 3 --quiet
measure "Missing title" --title "This Book Definitely Does Not Exist 12345" --limit 3 --quiet
