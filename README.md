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
./run_profiled_single.sh

# Process a custom book
./run_profiled_single.sh "your_book.txt"

# Full control
./run_profiled_single.sh "book.txt" 50 30 4096 2048
```

## Requirements

- Python 3.10+
- [llama.cpp server](https://github.com/ggml-org/llama.cpp)
- CUDA-capable GPU (tested on RTX 5090)
- ~20GB VRAM for 30B model

## Project Structure

```
bookgraph-revisited/
├── extract_citations.py      # Core library for citation extraction
├── run_single_file.py         # CLI tool for processing books
├── run_profiled_single.sh     # Profiling script with GPU monitoring
├── monitor_gpu_util.sh        # GPU utilization monitor
├── plot_gpu_util.py          # GPU utilization plotter
└── profile_runs/              # Profiling results (gitignored)
```

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

## Metadata Agent: `web-search-agent`

Need to validate citations against Goodreads? Use the agent under `web-search-agent/`:

- `agent.py` builds a LlamaIndex **FunctionAgent** that forces every turn through the `goodreads_book_lookup` tool.
- Two complementary tools power the agent:
  - `goodreads_book_lookup` scans `goodreads_books.json` with **20 multiprocessing workers** by title-only (then author-only) searches, returning the first 20 distinct matches so the agent can judge author alignment.
  - `goodreads_author_lookup` loads `goodreads_book_authors.json` in memory and surfaces author candidates when only an author name is cited.
- `test_agent.py` is a smoke harness that feeds prompts from `susan_sample.txt.json` and prints the agent verdict (`FOUND`/`NOT FOUND`).
- `tests/test_agent_components.py` includes unit tests for the agent runner, synthetic catalogs, and timing checks against real Goodreads data.

Example:

```bash
uv run python web-search-agent/test_agent.py \
  --citations-json susan_sample.txt.json \
  --limit 5 \
  --trace-tool
```

`--trace-tool` logs every Goodreads lookup plus the full metadata JSON returned by the multiprocessing tool, making it easy to inspect what the agent saw.

## Profiling Script: `run_profiled_single.sh`

Automated profiling with llama.cpp server management and GPU monitoring.

### Features

- **Automatic server management** - launches/stops llama-server
- **GPU utilization tracking** - monitors GPU usage in real-time
- **Performance plots** - generates utilization graphs
- **Optimized defaults** - production-ready configuration

### Usage

```bash
# Quick test with defaults
./run_profiled_single.sh

# Custom book
./run_profiled_single.sh "mybook.txt"

# Full control
./run_profiled_single.sh INPUT_TXT CHUNK_SIZE CONCURRENCY \
                         MAX_INPUT MAX_COMPLETION \
                         [MODEL_PATH] [GPU_LAYERS] [SERVER_BINARY] [INTERVAL]
```

### Default Configuration

```bash
INPUT_TXT:             test_book_subset.txt
CHUNK_SIZE:            50 sentences
MAX_CONCURRENCY:       30 parallel requests
MAX_INPUT_TOKENS:      4096
MAX_COMPLETION_TOKENS: 2048
CONTEXT_PER_REQUEST:   6144 (4096 input + 2048 output)
BATCH_SIZE:            2048
MODEL_PATH:            Qwen3-30B-A3B-Q5_K_S.gguf
GPU_LAYERS:            -1 (all layers)
KV_CACHE:              q4_0 (quantized for VRAM efficiency)
```

### Server Parameters

The script automatically configures llama-server with optimized settings:

```bash
-c CONTEXT_SIZE              # (input+output) * concurrency
-np CONCURRENCY              # Parallel slots
-n MAX_COMPLETION_TOKENS     # Generation limit
-b BATCH_SIZE                # Batch size for token processing (default: 2048)
-ngl -1                      # All layers on GPU
-ctk q4_0 -ctv q4_0         # Quantized KV cache (50% VRAM savings)
--repeat-penalty 1.2
--presence-penalty 0.4
--frequency-penalty 0.6
```

### Output

```
profile_runs/TIMESTAMP/
├── gpu_utilization.png      # GPU usage plot
├── 30_50_4096_2048.log      # GPU utilization data
├── run_single_file.log      # Processing log
├── llama_server.log         # Server log
└── book.txt.json            # Extracted citations
```

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
