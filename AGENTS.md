# AGENTS.md - Quick Reference for AI Agents

This document helps AI agents quickly understand how to work with BookGraph.

## Project Overview

BookGraph extracts citations from books (who does the author reference?) and visualizes them as an interactive graph. The pipeline:

1. **Extract** citations from text using LLM
2. **Resolve** citations against Goodreads/Wikipedia databases
3. **Visualize** in a D3.js frontend

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

### Register output for frontend visualization
```bash
uv run python scripts/register_dataset.py <OUTPUT_DIR> --name "Display Name"
```

### Serve the frontend
```bash
cd frontend && python -m http.server 8000
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
├── raw_extracted_citations/              # Step 1: Raw LLM extraction
│   └── Book_Title_12345.json
├── preprocessed_extracted_citations/     # Step 2: Cleaned/deduplicated
│   └── Book_Title_12345.json
└── final_citations_metadata_goodreads/   # Step 3: Resolved with metadata
    └── Book_Title_12345.json             # ← This is what the frontend uses
```

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

### Option 2: Manual setup

1. Create folder: `frontend/data/my_dataset/`

2. Copy final JSON files there

3. Create `manifest.json`:
```json
["book1.json", "book2.json"]
```

4. Add to `frontend/datasets.json`:
```json
{
    "name": "My Dataset",
    "path": "./data/my_dataset",
    "covers": ["covers/book_cover.jpg"]  // optional
}
```

### Adding book covers

1. Create `frontend/data/my_dataset/covers/`
2. Add cover images (JPG/PNG)
3. Name them like the book title slugified: `the_republic.jpg`
4. Reference in `datasets.json` under `"covers"` array

---

## Frontend Architecture

The frontend is a single-file D3.js application: `frontend/index.html`

### Key sections in index.html:

| Lines (approx) | Section |
|----------------|---------|
| 1-700 | CSS styles and variables |
| 700-720 | HTML structure |
| 720-900 | Data loading and processing |
| 900-1100 | D3 force simulation and rendering |
| 1100-1250 | Focus mode (radial zoom view) |
| 1250-1350 | Panel display (showPanel function) |
| 1350-1450 | Search and keyboard handlers |

### CSS variables (theming):
```css
--bg: #0a0a0c;           /* Background */
--accent: #d4a574;        /* Highlight color (amber) */
--book-source: #c45c4a;   /* Red - source books */
--book-cited: #4a6fa5;    /* Blue - cited books */
```

### Key JavaScript functions:

- `loadDataset(path)` - Loads and processes a dataset
- `processData(records)` - Builds the graph from JSON
- `enterFocusMode(node)` - Zoom into author's citation network
- `exitFocusMode()` - Return to full view
- `showPanel(node)` - Display book/author details in sidebar
- `highlight(node)` - Highlight connected nodes on hover

### Data flow:
```
datasets.json → manifest.json → [book1.json, book2.json, ...] → processData() → D3 render
```

---

## Common Tasks

### Add a new dataset from Calibre
```bash
# 1. Export from Calibre as TXT
# 2. Rename files to include Goodreads IDs
# 3. Run pipeline
uv run python run_folder.py /path/to/txt/files --workers 5

# 4. Register for frontend
uv run python scripts/register_dataset.py outputs/folder_runs/run_* --name "My Books"

# 5. View
cd frontend && python -m http.server 8000
```

### Re-run a failed/interrupted pipeline
The pipeline now has checkpointing. Just run the same command again - it will resume from the last checkpoint.

### Debug a specific book's citations
```bash
uv run python run_single_file.py path/to/book.txt \
    --output-dir outputs/debug_book \
    --book-title "Book Title" \
    --author "Author Name" \
    --goodreads-id 12345 \
    --verbose
```

### Modify frontend styling
Edit CSS variables in `frontend/index.html` (lines 12-37) for colors/theming.

### Add new citation card styling
Look for `.citation-card` in the CSS section (~line 400-520).

---

## Environment Setup

### Required environment variables (.env file):
```bash
OPENROUTER_API_KEY=sk-or-...
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
```

### Key dependencies (managed by uv):
- `llama-index` - Agent framework
- `openai` - LLM API client
- `pydantic` - Data validation
- `tqdm` - Progress bars

### Database files (in `datasets/`):
- `goodreads_books.db` - SQLite index of Goodreads books
- `wiki_people.db` - SQLite index of Wikipedia people
- `author_aliases.json` - Maps variant spellings to canonical names

---

## Deploying to Static Website

The frontend is also hosted on a static website. When the user asks to deploy or update the live site, do the following:

### Step 1: Copy the frontend
```bash
cp frontend/index.html /home/thiago/repos/thiagolira/_projects/book_graph_2/index.html
```

### Step 2: Commit and push in the static site repo
```bash
cd /home/thiago/repos/thiagolira/_projects/book_graph_2
git add index.html
git commit -m "Update BookGraph frontend"
git push
```

**Credentials** (stored in `.env`):
- Repo path: `/home/thiago/repos/thiagolira/_projects/book_graph_2`
- Git user: `thlira15@gmail.com`
- Git password/token: See `STATIC_SITE_GIT_PASS` in `.env`

If git push asks for credentials, use the values from `.env`. The user may ask you to "deploy", "push to live", or "update the website" - this means run the above steps.

---

## Troubleshooting

### "No ID in filename" warnings
Add Goodreads IDs to filenames: `Book_Title_12345.txt`

### Pipeline hangs on a book
Check `pipeline.log` for the specific error. Common issues:
- Rate limiting (reduce `--workers`)
- Timeout on large books (increase chunk size)

### Frontend shows empty graph
1. Check browser console for errors
2. Verify `manifest.json` lists the correct files
3. Verify JSON files have `"citations"` array with data

### Focus mode not working
Make sure the author has outbound citations (links to other authors).
