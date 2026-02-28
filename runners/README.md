Runners
=======

Wrapper scripts for common tasks, split by purpose.

Pipeline runners (`runners/pipeline/`)
--------------------------------------
- `pipeline_calibre_openrouter.sh` -- drives `calibre_citations_pipeline.py` against OpenRouter with DeepSeek V3.2 for both extraction and resolution agent. Defaults to `~/OneDrive/Documents/calibre_goodreads`, forces Goodreads ID `61535`, and reads `OPENROUTER_API_KEY` (autoloads `.env`).
- `pipeline_full_openrouter.sh` -- full pipeline over `books/` using OpenRouter for extraction + agent.
- `pipeline_single_openrouter.sh` -- run `run_single_file.py` against OpenRouter for a single TXT file.

Notes
-----
- All scripts resolve the project root relative to their own path, so they can be invoked from anywhere.
- Adjust model names, concurrency, and base URLs inline as needed. Environment variables in `.env` are loaded automatically when a script needs API keys.
- All LLM calls go through OpenRouter. The default model is `deepseek/deepseek-v3.2`.
