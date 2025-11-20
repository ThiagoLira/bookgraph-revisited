Goodreads index probes
======================

Benchmark and inspect the local Goodreads SQLite/FTS index without involving the LLM agent.

- `bench_goodreads_queries.sh`: small timing harness with representative title/author lookups.
- `query_goodreads.py`: CLI to query the index directly (`--title/--author --limit`).

Examples (run from repo root):
```bash
profiling/goodreads_index/bench_goodreads_queries.sh
python profiling/goodreads_index/query_goodreads.py --title "The Hero With a Thousand Faces" --limit 3
```
