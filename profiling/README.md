Profiling & experiments directory
=================================

- `gpu/`: llama.cpp throughput/latency profiling on local GPUs (single- and dual-GPU harnesses + GPU monitor helpers).
- `pipeline/`: end-to-end or stage-specific pipeline probes (mock runs, cProfile captures, stage-3 agent-only experiment).
- `goodreads_index/`: direct Goodreads SQLite/FTS query benchmarks and helpers.

Each subfolder has its own README with usage examples. Paths in scripts are relative to this repo root; run from the repo root for best results.
