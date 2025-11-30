# bookgraph-revisited

High-performance book citation extraction and visualization system.

## Overview

This project extracts book and author citations from text files (specifically Calibre libraries) using LLMs. It features:

- **Async parallel processing** with configurable concurrency
- **Structured JSON output** via JSON schema constraints
- **Goodreads & Wikipedia Resolution** for metadata enrichment
- **Interactive Graph Visualization** (D3.js)

## Quick Start

### 1. Install Dependencies
```bash
uv sync
```

### 2. Run the Calibre Pipeline
This is the main entry point. It processes a Calibre library export (metadata.db + TXT files).

```bash
uv run python calibre_citations_pipeline.py /path/to/calibre/library \
  --extract-base-url http://localhost:8080/v1 \
  --agent-base-url https://openrouter.ai/api/v1 \
  --agent-api-key $OPENROUTER_API_KEY \
  --agent-model "qwen/qwen3-next-80b-a3b-instruct"
```

Outputs are saved to `calibre_outputs/<library_name>/`.

### 3. Visualize
Open `frontend/index.html` in a browser (or serve it via a static server) to explore the generated citation graph.

---

**Running Local LLMs?**
See [README_LOCAL_LLAMA.md](README_LOCAL_LLAMA.md) for detailed instructions on setting up `llama.cpp`, profiling performance on GPUs, and optimizing throughput.

---

## Project Structure

```
bookgraph-revisited/
├── calibre_citations_pipeline.py # Main pipeline for Calibre libraries
├── process_citations_pipeline.py # Generic pipeline for text files
├── extract_citations.py          # Core library for LLM extraction
├── frontend/                     # D3.js visualization
│   ├── index.html
│   └── data/                     # Graph data (JSONs)
├── goodreads_data/               # Data sources (Goodreads/Wiki indices)
├── lib/
│   ├── bibliography_agent/       # Agent for metadata resolution
│   └── goodreads_scraper.py      # Scraper for original publication dates
├── profiling/                    # Performance profiling scripts
└── scripts/                      # Utility scripts (index building, etc.)
```

## Core Components

### 1. Calibre Pipeline (`calibre_citations_pipeline.py`)
**Main Entry Point.** Designed to process a Calibre library export (metadata.db + TXT files).
- Reads book metadata from Calibre's SQLite DB.
- Extracts citations using `extract_citations.py`.
- Resolves metadata using the new **Bibliography Workflow**.
- Outputs graph-ready JSON files.

### 2. Extraction Library (`extract_citations.py`)
Python library for extracting book citations from text using local LLMs.
- **Chunked processing**: Splits text into manageable chunks.
- **Token-aware**: Respects context limits.
- **Async/await**: Parallel processing.
- **Schema validation**: Ensures correct JSON output.

### 3. Bibliography Workflow (`lib/bibliography_agent/citation_workflow.py`)
The new, robust event-driven workflow for resolving citations.
- **Replaces the old FunctionAgent** (which is now archived in `lib/bibliography_agent/old/`).
- **Logic**:
  - **Search**: Queries Goodreads/Wikipedia indices.
  - **Validate**: Uses LLM to verify matches against the citation context.
  - **Enrich**: Fetches full metadata (covers, dates, etc.).
- **State Management**: Uses `llama_index.core.workflow` for reliable, step-by-step execution.

### 4. Full Pipeline (`process_citations_pipeline.py`)
Legacy/Generic pipeline for processing raw text files without Calibre metadata.
1. **Extraction**: Fan-out chunked prompts.
2. **Preprocess**: Deduplicate and normalize.
3. **Workflow**: Concurrently resolve citations using the new workflow.

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
