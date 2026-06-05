# AGENTS.md - Quick Reference for AI Agents

This document helps AI agents quickly understand how to work with BookGraph.

## Project Overview

BookGraph extracts citations from books (who does the author reference?) and visualizes them as an interactive graph. The pipeline has 4 stages:

0. **Enrich** source book metadata (author, publication year)
1. **Extract** citations from text using LLM
2. **Clean** citations (heuristics + LLM validation, single stage)
3. **Resolve** citations against Goodreads/Wikipedia, enrich, deduplicate

All LLM calls go through **OpenRouter** (no local models).

---

## Quick Start Commands

### Process books from a folder
```bash
uv run python run_folder.py <INPUT_FOLDER> --workers 5
```

### Dry-run (see what would be processed)
```bash
uv run python run_folder.py <INPUT_FOLDER> --dry-run
```

### Process a single file
```bash
uv run python run_single_file.py path/to/book.txt \
    --book-title "Title" --author "Author" --goodreads-id 12345
```

### Process a Calibre library directly
```bash
uv run python calibre_citations_pipeline.py /path/to/calibre/library
```

### Register output for frontend visualization
```bash
uv run python scripts/register_dataset.py <OUTPUT_DIR> --name "Display Name" --build
# --build runs the offline bake. Without it, bake manually:
#   node frontend/build/build.mjs --dataset <slug>     (or --all)
```

### Serve the frontend
```bash
cd frontend && python -m http.server 8000          # → http://localhost:8000/  (open /frontend/ if served from repo root)
# or: python scripts/serve.py 8011                 # threaded + gzip, binds 0.0.0.0
```

### Run tests
```bash
uv run pytest lib/bibliography_agent/tests/ -x -q
```

---

## Getting Books from Calibre

### Step 1: Export books as TXT from Calibre

1. Open Calibre
2. Select the books you want to process
3. Right-click → "Convert books" → "Bulk convert"
4. Set **Output format: TXT**
5. Convert and note the output location

### Step 2: Prepare the input folder

Create a folder with your exported `.txt` files. **Important filename format:**

```
Book_Title_Here_GOODREADS_ID.txt
```

Examples:
```
The_Republic_30289.txt
Beyond_Good_and_Evil_7529.txt
What_I_Believe_67354.txt
```

The Goodreads ID is the number in the book's Goodreads URL (e.g., `goodreads.com/book/show/30289`).

If you don't include an ID, the pipeline will attempt to look it up by title (less reliable).

### Step 3: Run the pipeline

```bash
# Create a timestamped library folder (recommended)
mkdir -p input_books/libraries/my_library_$(date +%Y%m%d)

# Copy your txt files there
cp /path/to/calibre/exports/*.txt input_books/libraries/my_library_$(date +%Y%m%d)/

# Run the pipeline
uv run python run_folder.py input_books/libraries/my_library_$(date +%Y%m%d) --workers 5
```

---

## Pipeline Output Structure

After running `run_folder.py`, outputs go to `outputs/folder_runs/run_YYYYMMDD-HHMMSS/`:

```
outputs/folder_runs/run_20260128-123456/
├── pipeline.log                          # Full debug log
├── raw_extracted_citations/              # Stage 1: Raw LLM extraction
│   └── 12345.json
├── cleaned_citations/                    # Stage 2: Cleaned + validated
│   └── 12345.json
└── final_citations_metadata_goodreads/   # Stage 3: Resolved with metadata
    └── 12345.json                        #   ← This is what the frontend uses
```

---

## Code Architecture

### Entry Points (all use `lib/cli_common.py` for shared config)

| Script | Purpose |
|--------|---------|
| `run_single_file.py` | Single book processing |
| `run_folder.py` | Batch folder processing with parallel workers |
| `calibre_citations_pipeline.py` | Calibre library processing (reads metadata.db) |

### Core Pipeline

| Module | Purpose |
|--------|---------|
| `lib/main_pipeline.py` | `BookPipeline` + `PipelineConfig` — orchestrates 4 stages |
| `lib/cli_common.py` | Shared CLI args, `build_config_from_args()`, `setup_logging()` |
| `lib/llm_client.py` | `LLMConfig` dataclass, `build_llama_llm()`, `build_async_openai()` |

### Stage 1: Extraction
| Module | Purpose |
|--------|---------|
| `lib/extract_citations.py` | Chunk text, call LLM, parse structured citations |

### Stage 2: Cleaning
| Module | Purpose |
|--------|---------|
| `lib/clean_citations.py` | Heuristic filters + LLM validation (merged stage) |

### Stage 3: Resolution & Enrichment
| Module | Purpose |
|--------|---------|
| `lib/bibliography_agent/citation_workflow.py` | LlamaIndex Workflow: query → search → validate → aggregate |
| `lib/bibliography_agent/deterministic_queries.py` | Rule-based query generation (attempt 0, no LLM) |
| `lib/bibliography_agent/bibliography_tool.py` | `SQLiteGoodreadsCatalog`, `GoodreadsAuthorCatalog`, `SQLiteWikiPeopleIndex` |
| `lib/bibliography_agent/events.py` | Workflow event types |
| `lib/metadata_enricher.py` | 4-source cascade: cache → scraper → Wikipedia → LLM |
| `lib/goodreads_scraper.py` | Web scraper for original publication dates |
| `lib/wikipedia_agent.py` | Wikipedia lookup for dates and bios |

### Shared Utilities
| Module | Purpose |
|--------|---------|
| `lib/text_utils.py` | `normalize_author()`, `normalize_title()`, `fuzzy_ratio()`, `is_similar()` |
| `lib/author_aliases.py` | `AuthorAliasRegistry`: canonical ↔ variants lookup |
| `lib/checkpoint.py` | `CheckpointManager`: save/load/remove crash-recovery state |
| `lib/author_cache.py` | `AuthorCache`: per-book cache for author-only citations |
| `lib/dedup.py` | `dedup_resolved_citations()`: merge duplicate editions post-resolution |
| `lib/edge_builder.py` | `build_result_dict()`: structured output with edge metadata |

### Data Files

| File | Size | Purpose | Read by | Written by |
|------|------|---------|---------|------------|
| `datasets/books_index.db` | 20 GB | Goodreads FTS5 index | `SQLiteGoodreadsCatalog` | `build_goodreads_index.py` (one-time) |
| `datasets/wiki_people_index.db` | 2.7 GB | Wikipedia people FTS5 + `author_overrides` table | `SQLiteWikiPeopleIndex` | `build_wiki_people_index.py` + `MetadataEnricher.save()` |
| `datasets/goodreads_books.json` | 9.2 GB | Raw Goodreads book catalog | Index builder | External (UCSD dataset) |
| `datasets/goodreads_book_authors.json` | 105 MB | Author ID → name mapping | `GoodreadsAuthorCatalog` | External |
| `datasets/author_aliases.json` | 42 KB | Name variants → canonical | `AuthorAliasRegistry`, `DeterministicQueryGenerator` | Hand-edited |
| `datasets/authors_metadata.json` | 725 KB | Author bios (grows per run) | `MetadataEnricher` | `MetadataEnricher.save()` |
| `datasets/original_publication_dates.json` | 71 KB | Book dates (grows per run) | `MetadataEnricher` | `MetadataEnricher.save()` |

### SQL Tables Inside the DBs

**`books_index.db`**:
- `books_fts` — FTS5 virtual table (title, authors, book_id, data)
- `books` — Regular table (book_id, data JSON, original_publication_year)
- `publication_dates` — Enrichment cache (book_id, year, source)

**`wiki_people_index.db`**:
- `people_fts` — FTS5 virtual table (title, data JSON)
- `author_overrides` — Birth/death/genre/nationality overrides (synced from authors_metadata.json)

---

## Adding to Frontend

### Option 1: Use register_dataset.py (recommended)

```bash
uv run python scripts/register_dataset.py \
    outputs/folder_runs/run_20260128-123456 \
    --name "My Book Collection"
```

This automatically:
- Copies JSON files to `frontend/data/my_book_collection/`
- Creates `manifest.json`
- Updates `frontend/datasets.json`

**Then BAKE the dataset** (required — the frontend only loads baked datasets):
```bash
node frontend/build/build.mjs --dataset my_book_collection
# or pass --build to register_dataset.py to do it automatically:
uv run python scripts/register_dataset.py <DIR> --name "My Books" --build
```

### Option 2: Manual setup

1. Create folder: `frontend/data/my_dataset/`
2. Copy final stage-3 JSON files there
3. Create `manifest.json`: `["book1.json", "book2.json"]`
4. Add to `frontend/datasets.json`: `{ "name": "My Dataset", "path": "./data/my_dataset" }`
5. Bake it: `node frontend/build/build.mjs --dataset my_dataset`

---

## Frontend Architecture

The frontend is a vanilla **Canvas 2D** app under `frontend/` (rewritten 2026-06; the
old WebGPU/D3-force-simulation version is gone). Node positions are **pre-computed
offline** (no runtime physics); the browser just draws fixed coordinates.

### Two phases

**1. Offline bake** (`frontend/build/`, Node + d3) — run after registering a dataset:
```bash
cd frontend/build && npm install        # one-time
node build.mjs --all                    # bake every dataset + merged "All Libraries"
node build.mjs --dataset <slug>         # bake just one
#   flags: --skip-images (fast, but NULLS portraits), --rebuild-images
```
For each `frontend/data/<slug>/` it reads the stage-3 JSON (via `manifest.json`) and writes:
- `baked.json` — lean render payload: `{meta, authors[], links[]}` with fixed `x/y/r`,
  `region`, `color`, `image_url`, years. **This is all the initial render needs.**
- `details.json` — heavy text (book/author descriptions + commentaries), **lazy-loaded**
  by the frontend after first paint (keeps initial load small).

It also sets `"baked": true` on the dataset's `frontend/datasets.json` entry and creates a
merged `_all` ("All Libraries"). Bake modules:
| File | Purpose |
|------|---------|
| `build/build.mjs` | CLI orchestrator |
| `build/graph_model.mjs` | Stage-3 JSON → authors/links (dedup, link aggregation) |
| `build/layout.mjs` | Y = time scale, X = collision-relaxed spacing, inner-book circle packing |
| `build/nationality.mjs` | nationality → region (reads `datasets/nationality_regions.json` + `datasets/nationality_overrides.json` + Wikipedia categories) |
| `build/images.mjs` | Wikipedia portrait thumbnails, cached in `datasets/author_images.json` |

**2. Runtime** (`frontend/js/`, vanilla + d3 from CDN for zoom/quadtree only):
| File | Purpose |
|------|---------|
| `js/app.js` | Bootstrap: load baked dataset, wire modules |
| `js/data.js` | Fetch `baked.json` (+ lazy `details.json`), build adjacency |
| `js/state.js` | Central state + pub/sub (selection, focus, back-stack) |
| `js/renderer.js` | Canvas 2D: gridlines, edges, author/book circles, portrait fade-in on zoom, focus dimming |
| `js/interaction.js` | d3-zoom pan/zoom, quadtree hit-test, `flyTo` navigation |
| `js/panels.js` | Detail panel + citation-navigation panel + legend + search |
| `js/d3-imports.js` | d3 v7 (loaded from jsdelivr CDN) |
| `css/main.css` | All styling (Cormorant Garamond + JetBrains Mono via Google Fonts) |

Color = author nationality grouped into ~12 regions (`datasets/nationality_regions.json`).
Y axis = time (author birth year / work year). Click an author → both panels open + graph
flies to it; click a cited author/work row to walk the citation chain (back-stack to return).

### Serving locally
```bash
bash scripts/launch_frontend.sh            # python http.server on :8000  → http://localhost:8000/frontend/
# OR a threaded server that also gzips (faster for the large _all payload):
python scripts/serve.py 8011               # → http://localhost:8011/frontend/  (binds 0.0.0.0)
```

---

## Common Tasks

### Add a new dataset from Calibre
```bash
# 1. Export from Calibre as TXT
# 2. Rename files to include Goodreads IDs
# 3. Run pipeline
uv run python run_folder.py /path/to/txt/files --workers 5
# 4. Register for frontend + bake
uv run python scripts/register_dataset.py outputs/folder_runs/run_* --name "My Books" --build
# 5. View
cd frontend && python -m http.server 8000
```

### Re-run a failed/interrupted pipeline
Just run the same command again — the checkpoint system resumes from the last saved state.

### Debug a specific book's citations
```bash
uv run python run_single_file.py path/to/book.txt \
    --output-dir outputs/debug_book \
    --book-title "Book Title" \
    --author "Author Name" \
    --goodreads-id 12345 \
    --verbose
```

---

## Deploying to Static Website

The frontend is hosted on a Blot.im static website. When the user asks to deploy or update the live site:

### Step 1: Copy the frontend files
```bash
cp frontend/index.html /home/thiago/repos/thiagolira/_projects/book_graph_2/index.html
cp frontend/datasets.json /home/thiago/repos/thiagolira/_projects/book_graph_2/datasets.json
for dir in $(ls frontend/data/); do
  cp -r "frontend/data/$dir" /home/thiago/repos/thiagolira/_projects/book_graph_2/data/
done
```

### Step 2: Commit and push in the static site repo

The remote is Blot.im which requires inline credentials. URL-encode the `@` in the email as `%40`:

```bash
cd /home/thiago/repos/thiagolira
git add _projects/book_graph_2/
git commit -m "Update BookGraph"
git push "https://thlira15%40gmail.com:$(grep STATIC_SITE_GIT_PASS /home/thiago/repos/bookgraph-revisited/.env | cut -d= -f2)@blot.im/clients/git/end/thiagolira.git" master
```

**Credentials** (stored in `.env`):
- Repo path: `/home/thiago/repos/thiagolira/_projects/book_graph_2`
- Git remote: `https://blot.im/clients/git/end/thiagolira.git`
- Git user: `thlira15@gmail.com` (URL-encode `@` as `%40` in push URL)
- Git password/token: See `STATIC_SITE_GIT_PASS` in `.env`

The user may ask you to "deploy", "push to live", or "update the website" — this means run the above steps.

---

## Agent Skills & Workflows (.agent/)

Before running pipeline commands manually, **always check `.agent/` for pre-built skills and workflows** that handle common tasks with proper defaults.

### Available skills

| Skill | Path | Purpose |
|-------|------|---------|
| **calibre_query** | `.agent/skills/calibre_query/retrieve_books.py` | Fetch books from Calibre library → `input_books/libraries/` |
| **goodreads_lookup** | `.agent/skills/goodreads_lookup/lookup_book.py` | Look up Goodreads IDs from local DB |

### Available workflows

| Workflow | Path | Purpose |
|----------|------|---------|
| **process_calibre** | `.agent/workflows/workflow_process_calibre.md` | Full Calibre → pipeline → frontend flow |
| **process_folder** | `.agent/workflows/workflow_process_folder.md` | Run pipeline on a folder of books |
| **process_single_file** | `.agent/workflows/workflow_process_single_file.md` | Run pipeline on one book |

### When to use skills vs manual commands

- **User says "process this book from Calibre"** → Read `workflow_process_calibre.md` and follow it
- **User says "find the Goodreads ID for X"** → Use `goodreads_lookup` skill
- **User says "grab books by Author from my library"** → Use `calibre_query` skill
- **User says "run the pipeline on folder X"** → Read `workflow_process_folder.md` and follow it

### Key paths

- Calibre library: `/home/thiago/Onedrive/Ebooks Vault`
- Static site repo: `/home/thiago/repos/thiagolira/_projects/book_graph_2`

---

## Environment Setup

### Required environment variables (.env file):
```bash
OPENROUTER_API_KEY=sk-or-...
```

### Key dependencies (managed by uv):
- `llama-index` - Agent framework for CitationWorkflow
- `openai` - AsyncOpenAI client for extraction
- `pydantic` - Data validation
- `nltk` - Sentence tokenization
- `tqdm` - Progress bars

---

## Troubleshooting

### "No ID in filename" warnings
Add Goodreads IDs to filenames: `Book_Title_12345.txt`

### Pipeline hangs on a book
Check `pipeline.log` for the specific error. Common issues:
- Rate limiting (reduce `--agent-concurrency`)
- Timeout on large books (workflow timeout is 120s per citation)

### Frontend shows empty graph
1. Check browser console for errors
2. Verify `manifest.json` lists the correct files
3. Verify JSON files have `"citations"` array with data

### Focus mode not working
Make sure the author has outbound citations (links to other authors).
