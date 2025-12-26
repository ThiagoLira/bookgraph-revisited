# 🕵️‍♂️ Web Search Agent Usage Guide

Welcome to the **Metadata Correction Agent**! This agent uses LLMs and live web search to fix missing birth/death dates and canonical names in your book dataset.

## 🚀 Quick Start

### 1. Start Services
First, spin up the required services (SearXNG for search, and the local MCP server).

```bash
./start_services.sh
```
*   **SearXNG**: `http://localhost:8080` (Web Interface)
*   **MCP Server**: `http://127.0.0.1:8000/sse`

### 2. Run the Agent
Run the agent on a specific JSON file.

**Using OpenRouter (Recommended for Quality)**:
```bash
python scripts/run_search_agent.py \
  frontend/data/28862.json \
  frontend/data/28862_corrected.json \
  --use-openrouter \
  --openrouter-model google/gemini-2.0-flash-exp:free
```

**Using Local LLM (Privileged/Offline)**:
*   Ensure your local OpenAI-compatible server (e.g., `llama.cpp`) is running on `http://ouroboros:8080/v1`.
*   Model must support tool calling or strong instruction following.
```bash
python scripts/run_search_agent.py \
  frontend/data/28862.json \
  frontend/data/28862_corrected.json \
  --base-url http://ouroboros:8080/v1 \
  --model Nemotron-3-Nano-30B-A3B-Q5_K_M.gguf
```

---

## 🛠️ Configuration

The agent is highly configurable via CLI arguments:

| Argument | Description | Default |
| :--- | :--- | :--- |
| `input_file` | Path to JSON file to process. | (Required) |
| `output_file` | Path to save corrected JSON. | (Required) |
| `--mcp-url` | URL of the MCP Search Server. | `http://127.0.0.1:8000/sse` |
| `--use-openrouter` | Switch to OpenRouter API. | `False` |
| `--openrouter-model` | Model ID for OpenRouter. | `google/gemini-2.0-flash-exp:free` |
| `--base-url` | Base URL for local LLM. | `http://localhost:8080/v1` |

## 🏗️ Architecture

The agent uses a **Llama Index Workflow**:

1.  **Validate**: Scans the book JSON for authors with missing birth years (`null`).
2.  **Search**: If missing data is found:
    *   Connects to **MCP Server** (Python/FastMCP).
    *   Queries **SearXNG** (Docker) for `"{Author} birth death date canonical name"`.
3.  **Correct**: LLM parses search results and extracts:
    *   `birth_year` (Negative for BC)
    *   `death_year`
    *   `name` (Canonical)
4.  **Update**: Writes changes back to the JSON structure.

## 🐛 Debugging

*   **Logs**: Check `mcp_server.log` in the root directory for search query logs.
*   **Trace**: Use `scripts/force_tool_call.py` to verify if the LLM is actually calling tools or hallucinating.
