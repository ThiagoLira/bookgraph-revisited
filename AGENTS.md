# Agent Guide

Two main entrypoints exist in this repo depending on the kind of “agent” you want to run—either a **local stress-testing agent** that spins up llama.cpp and records GPU stats, or a **remote-run agent** that only needs an OpenAI-compatible endpoint.

## Local Stress Agents

- **Single GPU (`profiling/single_gpu/run_profiled_single.sh`)**: end-to-end harness for load testing on one GPU. Launches `llama-server`, runs `run_single_file.py`, samples GPU utilization via `profiling/common/monitor_gpu_util.sh`, and emits logs/plots inside `profiling/single_gpu/profile_runs/<timestamp>/`.
- **Dual GPU (`profiling/dual_gpu/run_profiled_dual.sh`)**: sweeps through multiple `--max-concurrency` settings while running the server across GPUs 0/1 with row-split tensor parallelism. Drops outputs inside `profiling/dual_gpu/profile_runs/<timestamp>/np_*`.
- **Goodreads FTS builder (`scripts/build_goodreads_index.py`)**: preprocesses the Goodreads datasets into a SQLite FTS5 index (`goodreads_data/books_index.db`) with author names resolved and descriptions trimmed. Run once (or after updating the datasets) before using the metadata agent.
- **When to use**: you’re iterating on model quantization, batch sizes, or GPU placement and want automatic instrumentation without touching remote infra.
- **Inputs**: optional parameters for chunk size, concurrency, token budgets, GGUF path, GPU layers, etc. Defaults match the README table.
- **Outputs**: JSON citation file + `llama_server.log`, `run_single_file.log`, raw GPU log, and `gpu_utilization.png`.

## Remote/Headless Agent: `run_single_file.py`

- **Purpose**: lightweight CLI that just needs an OpenAI-compatible server URL (local or remote).
- **What it does**: reads a plaintext book, slices it into chunks, calls `extract_citations.process_book(...)`, and writes `<input>.json`. All server details are injected through flags (`--base-url`, `--api-key`, `--model`, token limits, etc.).
- **When to use**: the LLM is already running elsewhere (cloud llama.cpp, vLLM, OpenAI API, etc.) and you only want the citation extraction client.
- **How it fits with the stress agent**: `profiling/single_gpu/run_profiled_single.sh` simply wraps this script after launching the local server; you can also run it directly against any compatible endpoint without touching GPUs on this machine.

## Choosing the Right Agent

| Goal | Recommended Entry Point | Reason |
|------|------------------------|--------|
| Benchmark throughput on your RTX box | `profiling/single_gpu/run_profiled_single.sh` | Handles server boot, GPU logging, and cleanup automatically. |
| Explore multi-GPU concurrency scaling | `profiling/dual_gpu/run_profiled_dual.sh` | Sweeps `-np` (parallel slots) and records both GPU utilization plots. |
| Quick timing-only dual-GPU sweep | `profiling/dual_gpu/run_profiled_dual_timing.sh` | Runs the same server config but only writes duration metrics/CSV. |
| Precompute Goodreads FTS index | `uv run python scripts/build_goodreads_index.py --force` | Builds the SQLite FTS database so lookups are instant. |
| Use an already-running remote OpenAI-compatible server | `run_single_file.py` | Only depends on network endpoint + API key; zero GPU assumptions. |
| Integrate citation extraction into another pipeline | `run_single_file.py` or import `extract_citations` | Acts as a thin CLI/client; reusable config objects. |
| Tweak llama.cpp launch params | `profiling/single_gpu/run_profiled_single.sh` | Exposes model path, batch size, concurrency, token budgets via args. |

Both scripts ultimately call the same extraction codepath—the difference is whether you want the script to act as a **server+client profiler** or just a **client**. Pick the one that matches your deployment surface.

## Bibliography Agent: `lib/bibliography_agent`

- **Purpose**: answer “does this citation exist on Goodreads?” and use Wikipedia to disambiguate authors via a LlamaIndex FunctionAgent with multiprocessing search tools.
- **Key pieces**:
  - `agent.py` builds the agent, forcing tool-first reasoning and accepting any OpenAI-compatible endpoint.
  - `goodreads_tool.py` exposes three tools:
    - `goodreads_book_lookup`: memory-maps `goodreads_books.json`, splits it into 1 MB chunks, and spawns 20 processes that scan in parallel, returning up to 20 candidate editions (title-first, then author-only, then combined).
    - `goodreads_author_lookup`: loads the author dataset into memory so author-only citations can be disambiguated without touching the massive books file.
    - `wikipedia_person_lookup`: searches a prebuilt `wiki_people_index.db` to disambiguate author identities and roles.
  - `test_agent.py` is a CLI harness for running canned prompts; pass `--trace-tool` to log every lookup and the metadata payload.
  - `tests/test_agent_components.py` contains verbose unit tests and timing probes (both synthetic and real Goodreads datasets) so regressions are caught quickly.
- **When to use**: you want a deterministic, auditable check that a citation exists—e.g., validating `run_single_file.py` outputs or testing alternate prompts.
- **Returns**: either a full Goodreads metadata object (dict) for the best match or `{}` if nothing is found, so downstream code can format Markdown, YAML front matter, or agent responses without re-querying the dataset.
