# Agent Guide

Two main entrypoints exist in this repo depending on the kind of “agent” you want to run—either a **local stress-testing agent** that spins up llama.cpp and records GPU stats, or a **remote-run agent** that only needs an OpenAI-compatible endpoint.

## Local Stress Agent: `run_profiled_single.sh`

- **Purpose**: end-to-end harness for load testing on local hardware.
- **What it does**: launches `llama-server` with high-concurrency settings, runs `run_single_file.py`, samples GPU utilization via `monitor_gpu_util.sh`, and emits logs/plots inside `profile_runs/<timestamp>/`.
- **When to use**: you’re iterating on model quantization, batch sizes, or GPU placement and want automatic instrumentation without touching remote infra.
- **Inputs**: optional parameters for chunk size, concurrency, token budgets, GGUF path, GPU layers, etc. Defaults match the README table.
- **Outputs**: JSON citation file + `llama_server.log`, `run_single_file.log`, raw GPU log, and `gpu_utilization.png`.

## Remote/Headless Agent: `run_single_file.py`

- **Purpose**: lightweight CLI that just needs an OpenAI-compatible server URL (local or remote).
- **What it does**: reads a plaintext book, slices it into chunks, calls `extract_citations.process_book(...)`, and writes `<input>.json`. All server details are injected through flags (`--base-url`, `--api-key`, `--model`, token limits, etc.).
- **When to use**: the LLM is already running elsewhere (cloud llama.cpp, vLLM, OpenAI API, etc.) and you only want the citation extraction client.
- **How it fits with the stress agent**: `run_profiled_single.sh` simply wraps this script after launching the local server; you can also run it directly against any compatible endpoint without touching GPUs on this machine.

## Choosing the Right Agent

| Goal | Recommended Entry Point | Reason |
|------|------------------------|--------|
| Benchmark throughput on your RTX box | `run_profiled_single.sh` | Handles server boot, GPU logging, and cleanup automatically. |
| Use an already-running remote OpenAI-compatible server | `run_single_file.py` | Only depends on network endpoint + API key; zero GPU assumptions. |
| Integrate citation extraction into another pipeline | `run_single_file.py` or import `extract_citations` | Acts as a thin CLI/client; reusable config objects. |
| Tweak llama.cpp launch params | `run_profiled_single.sh` | Exposes model path, batch size, concurrency, token budgets via args. |

Both scripts ultimately call the same extraction codepath—the difference is whether you want the script to act as a **server+client profiler** or just a **client**. Pick the one that matches your deployment surface.

## Goodreads Metadata Agent: `web-search-agent`

- **Purpose**: answer “does this citation exist on Goodreads?” by pairing a LlamaIndex FunctionAgent with a multiprocessing search tool.
- **Key pieces**:
  - `agent.py` builds the agent, forcing tool-first reasoning and accepting any OpenAI-compatible endpoint.
  - `goodreads_tool.py` memory-maps `goodreads_books.json`, splits it into 1 MB, line-aligned chunks, and spawns 16 processes that scan in parallel. The first process that finds a match returns the **entire metadata JSON**; everyone else terminates immediately.
  - `test_agent.py` is a CLI harness for running canned prompts; pass `--trace-tool` to log every lookup and the metadata payload.
  - `tests/test_agent_components.py` contains verbose unit tests and timing probes (both synthetic and real Goodreads datasets) so regressions are caught quickly.
- **When to use**: you want a deterministic, auditable check that a citation exists—e.g., validating `run_single_file.py` outputs or testing alternate prompts.
- **Returns**: either a full Goodreads metadata object (dict) for the best match or `{}` if nothing is found, so downstream code can format Markdown, YAML front matter, or agent responses without re-querying the dataset.
