# BookGraph Revisited

A high-performance pipeline for extracting, resolving, and visualizing book and author citations from large text corpora.

## Overview

This system processes raw text files (books) to find citations of other books and authors. It uses LLMs for extraction, a specialized validation agent to resolve citations against Goodreads/Wikipedia, and an automatic web fallback for obscure references.

**Key Features:**
*   **Pipeline Architecture**: Modular `BookPipeline` that handles extraction, preprocessing, and resolution.
*   **LLM Extraction**: Uses prompt-based extraction (compatible with OpenAI-like APIs).
*   **Agentic Resolution**: A `CitationWorkflow` (LlamaIndex-based) that searches fuzzy matches and validates them with an LLM.
*   **Web Resolution Fallback**: Automatic fallback to agentic web search (using LLM knowledge) when local resolution fails.
*   **Calibre Integration**: Native support for processing Calibre libraries, leveraging existing metadata.
*   **Checkpointing**: Pipeline saves progress and can resume from interruptions.
*   **Visualization**: D3.js frontend with focus mode for exploring dense citation networks.

## Architecture

```mermaid
graph TD
    A[Input: Calibre Library / Text Files] --> B(BookPipeline)

    subgraph Pipeline Stages
        B --> C[Step 1: LLM Extraction]
        C -->|Raw JSON| D[Step 2: Preprocessing]
        D -->|Clean List| E[Step 3: Citation Workflow]
    end

    subgraph Resolution Process
        E --> F{Search Indices}
        F -->|Candidates| G[LLM Validation]
        G -->|Match| H[Metadata Enrichment]
        G -->|No Match| I[Web Resolution Fallback]
        I -->|Resolved| H
    end

    H --> J[Output: Final JSON]
    J --> K[Frontend Visualization]
```

## Setup

### Prerequisites
*   Python 3.10+
*   `uv` (Universal Python Package Manager)
*   LLM API Provider (e.g., OpenRouter)

### Installation

1.  **Clone & Install**:
    ```bash
    git clone https://github.com/thiago-lira/bookgraph-revisited.git
    cd bookgraph-revisited
    uv sync
    ```

2.  **Environment Variables**:
    Create a `.env` file:
    ```bash
    OPENROUTER_API_KEY="sk-..."
    OPENROUTER_BASE_URL="https://openrouter.ai/api/v1"
    ```

---

## Standard Workflows

### Workflow 1: From Calibre to Visualization (Recommended)

This is the most common workflow for processing your personal library.

#### Step 1: Export books from Calibre

1. Open Calibre and select the books you want to analyze
2. Right-click → **Convert books** → **Bulk convert**
3. Set **Output format: TXT**
4. Click OK and wait for conversion

#### Step 2: Prepare input files

Create a folder and rename your files to include Goodreads IDs:

```bash
mkdir -p input_books/libraries/my_library_$(date +%Y%m%d)
```

**Important:** Name files as `Title_GOODREADS_ID.txt`:
```
The_Republic_30289.txt
Beyond_Good_and_Evil_7529.txt
Meditations_30659.txt
```

The Goodreads ID is the number from the book's URL: `goodreads.com/book/show/30289`

#### Step 3: Run the pipeline

```bash
# Preview what will be processed
uv run python run_folder.py input_books/libraries/my_library_20260128 --dry-run

# Run with 5 parallel workers
uv run python run_folder.py input_books/libraries/my_library_20260128 --workers 5
```

#### Step 4: Register for frontend

```bash
uv run python scripts/register_dataset.py \
    outputs/folder_runs/run_20260128-123456 \
    --name "My Personal Library"
```

#### Step 5: View the visualization

```bash
cd frontend && python -m http.server 8000
# Open http://localhost:8000
```

---

### Workflow 2: Single File Experiment

Best for testing extraction on a specific book or essay.

```bash
uv run python run_single_file.py evaluation/DFW-PLURIBUS.txt \
  --output-dir outputs/single_runs/dfw_pluribus \
  --book-title "E Unibus Pluram" \
  --author "David Foster Wallace" \
  --goodreads-id 6751
```

---

### Workflow 3: Folder Batch (Quick)

Process any folder of `.txt` files:

```bash
uv run python run_folder.py datasets/test_books/ --workers 5
```

**Options:**
| Flag | Description |
|------|-------------|
| `--workers N` | Parallel file processing (default: 1) |
| `--dry-run` | Preview without processing |
| `--verbose` | Debug logging to console |
| `--pattern "*.md"` | Change file pattern |
| `--model "gpt-4o"` | Use different LLM |

---

## Output Structure

After running the pipeline:

```
outputs/folder_runs/run_YYYYMMDD-HHMMSS/
├── pipeline.log                              # Full debug log
├── raw_extracted_citations/                  # Step 1: Raw LLM output
│   └── Book_Title_12345.json
├── preprocessed_extracted_citations/         # Step 2: Cleaned
│   └── Book_Title_12345.json
└── final_citations_metadata_goodreads/       # Step 3: Final (for frontend)
    └── Book_Title_12345.json
```

### Checkpoint Recovery

If the pipeline is interrupted, a `.checkpoint.json` file is saved. Simply re-run the same command to resume from where it left off.

---

## Frontend Visualization

### Features

- **Timeline View**: Authors arranged chronologically (ancient at bottom, modern at top)
- **Focus Mode**: Click any author to see a radial view of their citations
- **Drag to Pan**: In focus mode, drag to explore large networks
- **Citation Cards**: Click books/authors to see AI-extracted commentary
- **Search**: Find authors or books by name

### Adding Datasets Manually

1. Create `frontend/data/my_dataset/`
2. Copy final JSON files from pipeline output
3. Create `manifest.json`:
   ```json
   ["book1.json", "book2.json"]
   ```
4. Update `frontend/datasets.json`:
   ```json
   {
       "name": "My Dataset",
       "path": "./data/my_dataset",
       "covers": ["covers/cover.jpg"]
   }
   ```

### Adding Book Covers

1. Create `frontend/data/my_dataset/covers/`
2. Add images named like: `book_title_slugified.jpg`
3. Reference in `datasets.json` `"covers"` array

---

## Configuration

### Pipeline Config (`run_folder.py`)

| Option | Default | Description |
|--------|---------|-------------|
| `--workers` | 1 | Parallel file processing |
| `--chunk-size` | 50 | Sentences per extraction chunk |
| `--model` | qwen/qwen3-next-80b | LLM model ID |
| `--base-url` | OpenRouter | API endpoint |

### Author Aliases (`datasets/author_aliases.json`)

Maps variant spellings to canonical names for better matching:

```json
{
  "Laozi": ["Lao-Tze", "Lao Tzu", "Lao-tzu"],
  "Plato": ["Platon"],
  "Fyodor Dostoevsky": ["Dostoyevsky", "Dostoevski"]
}
```

---

## Development

### Key Files

| File | Purpose |
|------|---------|
| `run_folder.py` | Main CLI for batch processing |
| `lib/main_pipeline.py` | Pipeline orchestration, checkpointing |
| `lib/extract_citations.py` | LLM extraction prompts |
| `lib/bibliography_agent/citation_workflow.py` | Resolution agent |
| `lib/metadata_enricher.py` | Goodreads/Wikipedia enrichment |
| `frontend/index.html` | D3.js visualization (single file) |
| `scripts/register_dataset.py` | Frontend data registration |

### Frontend Customization

Edit CSS variables in `frontend/index.html`:

```css
:root {
    --bg: #0a0a0c;           /* Background */
    --accent: #d4a574;        /* Highlight color */
    --book-source: #c45c4a;   /* Source books (red) */
    --book-cited: #4a6fa5;    /* Cited books (blue) */
}
```

---

## Troubleshooting

### "No ID in filename" warning
Add Goodreads IDs to filenames: `Book_Title_12345.txt`

### Pipeline rate limited
Reduce workers: `--workers 2`

### Empty frontend graph
1. Check `manifest.json` lists your files
2. Verify JSON has non-empty `"citations"` array
3. Check browser console for errors

### Focus mode shows nothing
The selected author needs outbound citations to display a network.

---

## For AI Agents

See **[AGENTS.md](AGENTS.md)** for a quick-reference guide optimized for AI agents working with this codebase.
