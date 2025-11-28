# bookgraph-revisited

High-performance book citation extraction using local LLMs with llama.cpp.

## Overview

This project extracts book and author citations from text files using a local LLM (Qwen3-30B-A3B). It features:

- **Async parallel processing** with configurable concurrency
- **Structured JSON output** via JSON schema constraints
- **GPU profiling** with utilization monitoring
- **Optimized for speed** - processes books in ~1 minute on RTX 5090

## Quick Start

```bash
# Install dependencies
uv sync

# Process a book (uses default test subset)
./profiling/single_gpu/run_profiled_single.sh

# Process a custom book
./profiling/single_gpu/run_profiled_single.sh "your_book.txt"

# Full control
./profiling/single_gpu/run_profiled_single.sh "book.txt" 50 30 4096 2048
```

## Requirements

- Python 3.10+
- [llama.cpp server](https://github.com/ggml-org/llama.cpp)
- CUDA-capable GPU (tested on RTX 5090)
- ~20GB VRAM for 30B model

## Project Structure

```
bookgraph-revisited/
├── extract_citations.py        # Core library for extraction
├── process_citations_pipeline.py # Generic pipeline
├── calibre_citations_pipeline.py # Calibre-specific pipeline
├── run_single_file.py          # CLI tool
├── profiling/                  # Profiling scripts
├── scripts/
│   ├── build_goodreads_index.py
│   ├── build_wiki_people_index.py
│   └── debug/                  # Debugging scripts (workflow, failures, retries)
├── lib/
│   └── bibliography_agent/     # Citation workflow & agent
└── ...
```

## Calibre Pipeline: `calibre_citations_pipeline.py`

Designed to process a Calibre library export (metadata.db + TXT files).

```bash
uv run python calibre_citations_pipeline.py /path/to/calibre/library \
  --extract-base-url http://localhost:8080/v1 \
  --agent-base-url https://openrouter.ai/api/v1 \
  --agent-api-key $OPENROUTER_API_KEY \
  --agent-model "qwen/qwen3-next-80b-a3b-instruct" \
  --debug-trace
```

Outputs are saved to `calibre_outputs/<library_name>/`.


## Core Library: `extract_citations.py`

Python library for extracting book citations from text using local LLMs.

### Key Features

- **Chunked processing** - splits text into manageable chunks
- **Token-aware** - respects context limits with automatic trimming
- **Async/await** - parallel processing with configurable concurrency
- **Schema validation** - Pydantic models ensure correct output format

### Example Usage

```python
from pathlib import Path
from extract_citations import ExtractionConfig, process_book, write_output

config = ExtractionConfig(
    input_path=Path("book.txt"),
    chunk_size=50,
    max_concurrency=30,
    max_context_per_request=6144,  # Total context window (input + output)
    max_completion_tokens=2048,
    base_url="http://localhost:8080/v1",
)

result = await process_book(config)
write_output(result, Path("book.txt.json"))
```

### Data Models

**BookCitation**
```python
{
  "title": str | null,        # Book title (null for author-only refs)
  "author": str,              # Author name (required)
  "note": str | null          # Optional clarification
}
```

**ChunkExtraction**
```python
{
  "chunk_index": int,
  "start_sentence": int,
  "end_sentence": int,
  "citations": List[BookCitation]
}
```

## CLI Tool: `run_single_file.py`

Command-line interface for processing text files.

```bash
uv run python run_single_file.py book.txt \
  --chunk-size 50 \
  --max-concurrency 30 \
  --max-context-per-request 6144 \
  --max-completion-tokens 2048 \
  --base-url http://localhost:8080/v1
```

### Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--chunk-size` | 15 | Sentences per chunk |
| `--max-concurrency` | 50 | Parallel requests |
| `--max-context-per-request` | 6144 | Total context window per request (input + output) |
| `--max-completion-tokens` | 2048 | Max response tokens |
| `--base-url` | localhost:8080/v1 | OpenAI-compatible API endpoint |
| `--model` | Qwen/Qwen3-30B-A3B | Model identifier |
| `--tokenizer-name` | Qwen/Qwen3-30B-A3B | HuggingFace tokenizer |
| `--debug-limit` | None | Limit chunks for testing |

## Metadata Agent: `lib/bibliography_agent`

Need to validate citations against Goodreads and Wikipedia? Use the agent under `lib/bibliography_agent/`:

- `agent.py` builds a LlamaIndex **FunctionAgent** that branches:
  - **Author + Title present**: prompt steers the LLM to use `goodreads_book_lookup` (title-first, then author if needed) and return the best match.
  - **Author-only**: prompt steers the LLM to call `wikipedia_person_lookup` first to disambiguate the person (role/domain match), then `goodreads_author_lookup` to attach an author_id; if Goodreads is missing but Wikipedia is confident, return Wikipedia metadata only.
- Tools in `bibliography_tool.py`:
  - `goodreads_book_lookup` queries a SQLite FTS5 index (built once via `uv run python scripts/build_goodreads_index.py --force`).
  - `goodreads_author_lookup` loads `goodreads_book_authors.json` in memory to surface author candidates.
  - `wikipedia_person_lookup` searches a prebuilt `wiki_people_index.db` (built via `scripts/filter_wiki_people.py` → `scripts/build_wiki_people_index.py`) to disambiguate identities/roles.
- `test_bibliography_agent.py` is a smoke harness that feeds prompts from `susan_sample.txt.json` and prints the JSON metadata (or `{}` when nothing matches).
- `tests/test_agent_components.py` includes unit tests for the agent runner, synthetic catalogs, and timing checks against real Goodreads data.
- **One-time setup**:
  - `uv run python scripts/build_goodreads_index.py --force` to build/refresh `goodreads_data/books_index.db`.
  - `uv run python scripts/filter_wiki_people.py` then `uv run python scripts/build_wiki_people_index.py` to build `goodreads_data/wiki_people_index.db`.

Example:

```bash
uv run python -m lib.bibliography_agent.test_bibliography_agent \
  --citations-json susan_sample.txt.json \
  --limit 5 \
  --trace-tool
```

`--trace-tool` logs every Goodreads lookup plus the full metadata JSON returned by the multiprocessing tool, making it easy to inspect what the agent saw.

## Full Pipeline: `process_citations_pipeline.py`

`process_citations_pipeline.py` stitches extraction, preprocessing, and Goodreads validation together. Each stage is asynchronous and reports progress:

1. **Extraction** – fan-out chunked prompts against your LLM server via `process_book` (async with per-chunk progress bars).
2. **Preprocess** – collapse duplicates and normalize citation dictionaries.
3. **Goodreads agent** – now async too: up to `--agent-max-workers` agent runners share a single SQLite catalog and concurrently resolve citations. Timings per citation appear whenever `--agent-trace` is set.

Key CLI flags:

| Flag | Description |
| ---- | ----------- |
| `--pattern` | Glob to pick a subset of `.txt` sources (great for mock docs or profiling) |
| `--agent-max-workers` | Number of concurrent Goodreads agent calls (default 5). Each worker reuses the same LlamaIndex workflow |
| `--agent-trace` | Emits the system prompt, tool calls, timings, and final JSON for every citation |
| `--extract-*` / `--agent-*` | OpenAI-compatible endpoint + model pair for each stage |

Example (single mock doc, local llama.cpp endpoints):

```bash
uv run python process_citations_pipeline.py books_samples \
  --pattern mock_short.txt \
  --extract-base-url http://127.0.0.1:8080/v1 \
  --agent-base-url http://127.0.0.1:8080/v1 \
  --extract-api-key test --agent-api-key test \
  --extract-model Qwen/Qwen3-30B-A3B \
  --agent-model qwen/qwen3-next-80b-a3b-instruct \
  --agent-max-workers 8 \
  --agent-trace
```

Outputs land in:

```
books_samples/
├── raw_extracted_citations/                 # Stage 1 JSON
├── preprocessed_extracted_citations/        # Stage 2 deduped results
└── final_citations_metadata_goodreads/      # Stage 3 JSONL w/ metadata
```

## Profiling Scripts

### Single-GPU Stress Harness (`profiling/single_gpu/run_profiled_single.sh`)

Automates everything for one-GPU experiments: spins up `llama-server`, launches `run_single_file.py`, records GPU utilization, and produces a PNG plot.

**Usage**

```bash
# Quick test with defaults
./profiling/single_gpu/run_profiled_single.sh

# Custom book
./profiling/single_gpu/run_profiled_single.sh "mybook.txt"

# Full control
./profiling/single_gpu/run_profiled_single.sh INPUT CHUNK CONCURRENCY \
    MAX_INPUT MAX_COMPLETION [MODEL_PATH] [GPU_LAYERS] [SERVER_BINARY] [INTERVAL]
```

**Default configuration**

```
INPUT_TXT:             test_book_subset.txt
CHUNK_SIZE:            50 sentences
MAX_CONCURRENCY:       30 parallel requests
MAX_INPUT_TOKENS:      4096
MAX_COMPLETION_TOKENS: 2048
CONTEXT_PER_REQUEST:   6144 (4096 input + 2048 output)
BATCH_SIZE:            2048  (logical)
MODEL_PATH:            Qwen3-30B-A3B-Q5_K_S.gguf
GPU_LAYERS:            -1 (all layers)
KV_CACHE:              q4_0 (quantized for VRAM efficiency)
```

The harness writes artifacts to `profiling/single_gpu/profile_runs/<timestamp>/`:

```
├── gpu_utilization.png      # GPU 0 plot
├── *_metrics.log            # Raw utilization samples
├── run_single_file.log      # Extraction logs
└── llama_server.log         # Server logs
```

### Dual-GPU Parallel Sweep (`profiling/dual_gpu/run_profiled_dual.sh`)

New experiment focused on 2×GPU launches. It:

- Boots a row-split, tensor-parallel `llama-server` across GPUs `0,1`
- Processes a single book from `books_samples/` (default: `freud.txt`)
- Sweeps through multiple `--max-concurrency` values in one run
- Logs/plots utilization for **both GPUs** per experiment

**Usage**

```bash
# Profile freud.txt at 12, 20, and 28 concurrent slots
./profiling/dual_gpu/run_profiled_dual.sh \
  "$PWD/books_samples/freud.txt" 12,20,28

# Override tensor split + batch size
./profiling/dual_gpu/run_profiled_dual.sh \
  "$PWD/books_samples/sandel.txt" 16,24 \
  50 4096 2048 /home/thiago/models/Qwen3-30B-A3B-Q5_K_S.gguf \
  -1 llama-server 1 2048 512 65,35 0
```

Output lives under `profiling/dual_gpu/profile_runs/<timestamp>/np_<parallel>/` with:

```
├── gpu0.log / gpu0_util.png        # GPU 0 raw + plot
├── gpu1.log / gpu1_util.png        # GPU 1 raw + plot
├── run_single_file.log             # Extraction logs
└── llama_server.log                # Server stdout/stderr
```

The default server launch mirrors the recommendations in `launch_llama_server_2_gpus.sh`: row split, tensor split `70,30`, heavy tensors pinned to GPU 0, `-np` sweeping over the provided list.

### Dual-GPU Timing-Only Sweep (`profiling/dual_gpu/run_profiled_dual_timing.sh`)

Same launch mechanics as the full profiler but stripped down to a single datapoint: wall-clock seconds per concurrency. No GPU logs, just run/server logs and a CSV summary.

```bash
./profiling/dual_gpu/run_profiled_dual_timing.sh \
  "$PWD/books_samples/susan.txt" 8,16,24
```

Results land under `profiling/dual_gpu/profile_runs/<timestamp>_timings/` with:

```
├── timings.csv                 # concurrency,duration_seconds
├── np_<N>/run_single_file.log  # extraction log per sweep
└── np_<N>/llama_server.log     # server stdout/stderr
```

### Agent & Database micro-benchmarks

For latency hunts we keep a few focused utilities under `profiling/`:

- `profiling/mock_run.sh` – spins up a virtualenv, runs `process_citations_pipeline.py` against `books_samples/mock_short.txt`, and records a cProfile trace at `profiling/mock_profile.prof`.
- `profiling/query_goodreads.py` – lightweight CLI that issues direct `goodreads_book_lookup` calls without the full agent stack.
- `profiling/bench_goodreads_queries.sh` – bash harness that times a suite of known-good queries (title-only and author-only) against the SQLite FTS index, logging milliseconds per lookup so you can validate DB build quality or hardware differences quickly.

Each script accepts the same `--base-url`, `--api-key`, or database overrides used elsewhere, so you can experiment without touching the core pipeline.

## Performance Benchmarks

Tested on RTX 5090 (32GB VRAM) with Qwen3-30B-A3B-Q5_K_S (20GB model):

### Test Results (733-sentence subset, 15 chunks)

| Config | Batch Size | Time | GPU Util |
|--------|-----------|------|----------|
| **Optimal** | 2048 | 13.5s | 70-75% |
| Medium | 1024 | 14.0s | 63% |
| Small | 512 | 14.5s | 68% |
| Tiny | 256 | 16.2s | 74% |

### Full Book (680KB, 104 chunks)

- **Time**: ~55 seconds
- **GPU utilization**: 70-75% sustained
- **Throughput**: ~30-40 tokens/sec per slot
- **VRAM usage**: ~24.5 GB (model + q4_0 KV cache)
- **Chunks**: 104 (50 sentences each, 4096 input tokens utilized)

### Key Optimization Findings

1. **Batch size matters**: 2048 optimal for full books, 1024 for small workloads
2. **KV cache quantization**: q4_0 enables higher concurrency with 50% VRAM savings
3. **Optimal concurrency**: 30 parallel requests saturates GPU efficiently
4. **Larger chunks = faster**: 50 sentences optimal (1-sentence chunks 5.6x slower!)
5. **Context calculation**: Total context = (input+output) × concurrency, llama.cpp divides by -np
6. **Parameter clarity**: Renamed max_input_tokens → max_context_per_request to fix double-reservation bug

## Troubleshooting

### Out of Memory (OOM)

```bash
cudaMalloc failed: out of memory
```

**Solutions:**
1. Reduce concurrency: `--max-concurrency 20`
2. Use q4_0 KV cache (default in profiling script)
3. Reduce context: `--max-input-tokens 2048`

### Slow Performance

**Check GPU utilization:**
```bash
watch -n 1 nvidia-smi
```

If GPU util < 80%:
- Increase concurrency
- Check for Python event loop bottleneck
- Verify batch-size in server config

### Server Won't Start

**Check logs:**
```bash
tail -100 profile_runs/TIMESTAMP/llama_server.log
```

Common issues:
- Model not found - verify `MODEL_PATH`
- Port already in use - kill existing server
- Insufficient VRAM - reduce context/concurrency

## Development

```bash
# Install dev dependencies
uv sync --all-extras

# Run tests
pytest

# Format code
black .
isort .

# Type check
mypy extract_citations.py
```

## License

MIT
### Mock profiling

`profiling/mock_run.sh` bundles the cProfile flow above. After running it, inspect `profiling/mock_profile.prof` via `snakeviz` or `python -m pstats profiling/mock_profile.prof`. This keeps the pipeline focused on the tiny test document while cProfile records timing.
