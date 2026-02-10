Runners
=======

Wrapper scripts for common tasks, split by purpose.

Pipeline runners (`runners/pipeline/`)
--------------------------------------
- `pipeline_calibre_openrouter.sh` – drives `calibre_citations_pipeline.py` against OpenRouter with DeepSeek V3.2 for both extraction and Goodreads agent. Defaults to `~/OneDrive/Documents/calibre_goodreads`, forces Goodreads ID `61535`, and reads `OPENROUTER_API_KEY` (autoloads `.env`).
- `pipeline_full_openrouter.sh` – full three-stage pipeline over `books/` using OpenRouter for extraction + agent.
- `pipeline_single_openrouter.sh` – run `run_single_file.py` against OpenRouter for a single TXT file.
- `pipeline_extract_local.sh` – local llama.cpp extraction against `http://localhost:8080/v1` with test API key; handy for smoke tests.

Server runners (`runners/server/`)
----------------------------------
- `server_llamacpp_dual_gpu.sh` – launch llama-server with Qwen3-30B row-split across two GPUs.
- `server_llamacpp_5090.sh` – launch llama-server tuned for a single RTX 5090.
- `server_llamacpp_single.sh` – minimal single-GPU llama-server launcher with preset model path.

Notes
-----
- All scripts resolve the project root relative to their own path, so they can be invoked from anywhere.
- Adjust model paths, concurrency, and base URLs inline as needed. Environment variables in `.env` are loaded automatically when a script needs API keys.
