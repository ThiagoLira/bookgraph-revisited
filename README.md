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
    max_input_tokens=4096,
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
  --max-input-tokens 4096 \
  --max-completion-tokens 2048 \
  --base-url http://localhost:8080/v1
```

### Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--chunk-size` | 15 | Sentences per chunk |
| `--max-concurrency` | 50 | Parallel requests |
| `--max-input-tokens` | 4000 | Max prompt tokens |
| `--max-completion-tokens` | 2048 | Max response tokens |
| `--base-url` | localhost:8080/v1 | OpenAI-compatible API endpoint |
| `--model` | Qwen/Qwen3-30B-A3B | Model identifier |
| `--tokenizer-name` | Qwen/Qwen3-30B-A3B | HuggingFace tokenizer |
| `--debug-limit` | None | Limit chunks for testing |

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
INPUT_TXT:           test_book_subset.txt
CHUNK_SIZE:          50 sentences
MAX_CONCURRENCY:     30 parallel requests
MAX_INPUT_TOKENS:    4096
MAX_COMPLETION_TOKENS: 2048
MODEL_PATH:          Qwen3-30B-A3B-Q5_K_S.gguf
GPU_LAYERS:          -1 (all layers)
KV_CACHE:            q4_0 (quantized for VRAM efficiency)
```

### Server Parameters

The script automatically configures llama-server with optimized settings:

```bash
-c CONTEXT_SIZE              # (input+output) * concurrency
-np CONCURRENCY              # Parallel slots
-n MAX_COMPLETION_TOKENS     # Generation limit
-ngl -1                      # All layers on GPU
-ctk q4_0 -ctv q4_0         # Quantized KV cache (50% VRAM savings)
--repeat-penalty 1.2
--presence-penalty 0.4
--frequency-penalty 0.6
-fa on                       # Flash attention
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

### Test Results (600-line subset)

| Config | Concurrency | KV Cache | Time | GPU Util |
|--------|-------------|----------|------|----------|
| **Optimal** | 30 | q4_0 | 13.6s | 85-97% |
| Baseline | 20 | q8_0 | 14.4s | 70-85% |
| Small chunks | 25 | q8_0 | 15.8s | 65-80% |

### Full Book (680KB, ~106 chunks)

- **Time**: ~57 seconds
- **GPU utilization**: 85-95% sustained
- **Throughput**: ~30-40 tokens/sec per slot
- **VRAM usage**: ~24.5 GB (model + q4_0 KV cache)

### Key Optimization Findings

1. **KV cache quantization matters**: q4_0 outperforms q8_0 by enabling higher concurrency
2. **Optimal concurrency**: 30 parallel requests for this workload
3. **Larger chunks are faster**: 50 sentences > 25 sentences (less overhead)
4. **VRAM bottleneck**: Context must account for parallel slots: `(input+output) * concurrency`

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
