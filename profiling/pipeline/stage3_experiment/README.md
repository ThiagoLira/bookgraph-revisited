Agent-only experiment for stage 3 of `process_citations_pipeline.py`.

- Input: preprocessed citation JSON files copied from `books_samples/preprocessed_extracted_citations` into `inputs/preprocessed_extracted_citations/`.
- Script: `run_agent_stage3.py` mirrors the pipeline's Goodreads metadata stage and writes JSONL outputs to `outputs/final_citations_metadata_goodreads/`.
- Requirements: OpenAI-compatible endpoint + API key (e.g., OpenRouter), and local Goodreads datasets already present in `goodreads_data/`.

Usage
-----

```bash
# Local inference defaults (llama.cpp at 127.0.0.1:8080)
profiling/pipeline/stage3_experiment/run_stage3_local.sh

# Launch server (single 5090) and run stage 3 with a chosen model path
MODEL_PATH=/home/thiago/models/Qwen3-30B-A3B-Q5_K_S.gguf \
profiling/pipeline/stage3_experiment/run_server_and_stage3.sh

# From repo root
uv run python profiling/pipeline/stage3_experiment/run_agent_stage3.py \
  --agent-api-key "$OPENROUTER_API_KEY" \
  --agent-base-url "${OPENROUTER_BASE_URL:-https://openrouter.ai/api/v1}" \
  --agent-model "qwen/qwen3-next-80b-a3b-instruct" \
  --agent-max-workers 3 \
  --agent-trace
```

You can drop additional stage-two outputs into `inputs/preprocessed_extracted_citations/` (or point `--pre-dir` elsewhere with `--pattern` filters) to reuse the exact agent-stage logic without running the earlier extraction/preprocess steps.
