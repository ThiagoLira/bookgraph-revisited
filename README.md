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
flowchart TD
    %% ── Input ──────────────────────────────────────────────
    INPUT[/"📁 Input: .txt files<br/>(Title_GoodreadsID.txt)"/]
    INPUT --> ENRICH

    %% ── Stage 0: Source Enrichment ─────────────────────────
    subgraph STAGE0["Stage 0 — Source Metadata Enrichment  (_enrich_source_metadata in main_pipeline.py)"]
        ENRICH["_enrich_source_metadata()<br/>called once per book before extraction"]
        ENRICH --> GR_LOOKUP["Goodreads Catalog<br/>SQLiteGoodreadsCatalog.find_books()<br/>FTS5 title match → top 3<br/>prefer exact book_id match,<br/>fallback to best title match"]
        GR_LOOKUP -->|"authors[], pub_year"| ENRICH_MERGE["Merge into<br/>source_metadata dict"]
        ENRICH -->|"authors or pub_year<br/>still missing?"| LLM_SOURCE["LLM Fallback<br/>(acomplete → JSON)<br/>prompt: 'Provide metadata for<br/>book titled ...'<br/>→ {author, publication_year}"]
        LLM_SOURCE -->|"author, year"| ENRICH_MERGE
        ENRICH_MERGE --> AUTHOR_META_SRC["enrich_author(primary_author)<br/>same 4-source cascade as Stage 4<br/>including validate_dates() gate"]
        AUTHOR_META_SRC -->|"birth/death years<br/>(date-validated)"| ENRICHED_META[/"Enriched source_metadata<br/>{title, authors, publication_year,<br/>author_metadata: {birth_year,<br/>death_year, ...}}"/]
    end

    ENRICHED_META --> EXTRACT

    %% ── Stage 1: Extraction ───────────────────────────────
    subgraph STAGE1["Stage 1 — LLM Extraction  (extract_citations.py)"]
        EXTRACT["process_book()"]
        EXTRACT --> SENT["NLTK sent_tokenize()<br/>split full text into sentences"]
        SENT --> CHUNK["build_chunks()<br/>token-budget aware,<br/>≤50 sentences/chunk,<br/>respects max_context_per_request"]
        CHUNK --> PARALLEL_LLM["Async LLM calls<br/>(semaphore = extract_concurrency)<br/>OpenAI-compatible API<br/>model from PipelineConfig"]
        PARALLEL_LLM -->|"JSON schema enforced<br/>via response_format"| PARSE["Pydantic parse<br/>ModelChunkCitations<br/>→ list of {title?, author?,<br/>contexts[], commentaries[]}"]
        PARSE -->|"retry ×2 on<br/>parse failure"| PARALLEL_LLM
        PARSE --> RAW_OUT[/"raw_extracted_citations/<br/>BookID.json<br/>{chunks: [{citations: [...]}]}<br/>one file per source book"/]
    end

    RAW_OUT --> PREPROCESS

    %% ── Stage 2: Preprocessing ────────────────────────────
    subgraph STAGE2["Stage 2 — Heuristic Preprocessing  (preprocess_citations.py)"]
        PREPROCESS["preprocess_data()<br/>deterministic, no LLM calls"]
        PREPROCESS --> FLATTEN["Flatten chunks →<br/>single flat citation list<br/>aggregate counts per (title, author)"]
        FLATTEN --> DEDUP_EXACT["deduplicate_exact()<br/>case-insensitive (title, author)<br/>merge contexts + commentaries"]
        DEDUP_EXACT --> H1["filter_non_person_authors()<br/>blocklist: 'Various', 'Anonymous'...<br/>pattern filter: all-caps, groups,<br/>'The X Institute', etc."]
        H1 --> H2["collapse_author_only()<br/>if author appears both with<br/>and without title → merge<br/>author-only into titled entry"]
        H2 --> H3["collapse_variant_titles()<br/>normalize 'The X' vs 'X',<br/>'A X' vs 'X' prefixes"]
        H3 --> H4["merge_similar_citations()<br/>SequenceMatcher ≥0.85 on titles<br/>within same author group"]
        H4 --> SELF_REF["drop_self_references()<br/>remove citations matching<br/>source_title or source_authors"]
        SELF_REF --> PRE_OUT[/"preprocessed_extracted_citations/<br/>BookID.json<br/>{total: N, citations: [...]}<br/>⚠️ dedup here is on RAW titles,<br/>before Goodreads resolution —<br/>'Republic' and 'The Republic'<br/>may survive as separate entries"/]
    end

    PRE_OUT --> VALIDATE

    %% ── Stage 3: LLM Validation ──────────────────────────
    subgraph STAGE3["Stage 3 — LLM Batch Validation  (validate_citations.py)"]
        VALIDATE["validate_citations()"]
        VALIDATE --> BATCH["Split into batches<br/>(≤30 citations each)"]
        BATCH --> VAL_LLM["Async LLM calls<br/>(semaphore = validate_concurrency)<br/>per-batch prompt with<br/>source_title + source_authors<br/>for context"]
        VAL_LLM -->|"JSON array response"| VAL_PARSE["Parse per-citation decisions:<br/>keep / fix / remove"]
        VAL_PARSE -->|"fix"| APPLY_FIX["Apply corrections<br/>(author name spelling,<br/>title correction,<br/>misattribution fix)"]
        VAL_PARSE -->|"remove"| LOG_REMOVE["Log removal reason<br/>(non-person, fictional,<br/>generic concept, etc.)"]
        VAL_PARSE -->|"keep"| PASS_THROUGH["Pass through unchanged"]
        APPLY_FIX --> VAL_OUT
        PASS_THROUGH --> VAL_OUT
        VAL_OUT[/"validated_citations/<br/>BookID.json<br/>{total: N, validation_stats:<br/>{removed, fixed, kept},<br/>citations: [...]}"/]
    end

    VAL_OUT --> WORKFLOW

    %% ── Stage 4: Citation Workflow ────────────────────────
    subgraph STAGE4["Stage 4 — Agentic Resolution + Enrichment + Dedup  (citation_workflow.py + main_pipeline.py + metadata_enricher.py)"]

        WORKFLOW["_run_workflow()<br/>loads checkpoint if exists,<br/>seeds author_cache from<br/>checkpoint results"]
        WORKFLOW --> CACHE_CHECK{"Per-book author_cache hit?<br/>(author-only citation,<br/>no title field)<br/>lookup: _find_cached_author()<br/>exact match on _normalize_author()<br/>or SequenceMatcher ≥0.9"}
        CACHE_CHECK -->|"hit"| CACHE_RESULT["deep copy cached result_dict<br/>replace raw field with<br/>current citation's raw data"]
        CACHE_CHECK -->|"miss"| CIT_WORKFLOW["CitationWorkflow.run()<br/>(LlamaIndex Workflow,<br/>timeout=120s)"]

        subgraph WF_INNER["CitationWorkflow Steps  (citation_workflow.py)"]
            direction TB
            GEN_Q["generate_queries()<br/>attempt 0: deterministic<br/>(deterministic_queries.py:<br/>author_aliases lookup,<br/>title/author SearchQuery pairs)<br/>attempt ≥1: LLM → structured<br/>QueryList with title/author variants"]
            GEN_Q --> SEARCH_GR["search_goodreads()<br/>SQLiteGoodreadsCatalog<br/>FTS5 full-text search<br/>→ top 5 by fuzzy score<br/>each query run independently"]
            GEN_Q --> SEARCH_WIKI["search_wikipedia()<br/>SQLiteWikiPeopleIndex<br/>FTS5 full-text search<br/>→ top 5 by fuzzy score"]
            SEARCH_GR --> VALIDATE_GR["validate_matches()<br/>LLM structured_predict()<br/>→ MatchDecision: best index<br/>or -1 (no match)<br/>prompt includes all candidates"]
            SEARCH_WIKI --> VALIDATE_WIKI["validate_matches()<br/>LLM structured_predict()<br/>→ best index or -1"]
            VALIDATE_GR -->|"if LLM says -1:<br/>fallback to fuzzy ≥70"| AGG["aggregate_results()<br/>combine best GR match<br/>+ best Wiki match<br/>→ match_type: book/person/<br/>not_found"]
            VALIDATE_WIKI --> AGG
            AGG -->|"not_found &<br/>retry_count < 3"| GEN_Q
            AGG -->|"match found or<br/>retries exhausted"| WF_RESULT["Return {match_type,<br/>metadata: {book_id, title,<br/>authors, author_ids,<br/>wikipedia_match, ...}}"]
        end

        CIT_WORKFLOW --> WF_INNER
        WF_INNER --> FALLBACK_CHECK{"match_type ==<br/>not_found / unknown<br/>/ error ?"}
        FALLBACK_CHECK -->|"yes"| WEB_FALLBACK["resolve_citation_fallback()<br/>(metadata_enricher.py)<br/>LLM prompt with source context:<br/>source_title, source_year,<br/>citation title/author/contexts<br/>→ JSON: match_type + metadata<br/>generates web_ synthetic ID<br/>via md5 hash if book match"]
        FALLBACK_CHECK -->|"no: book or person<br/>already resolved"| ENRICH_STEP

        WEB_FALLBACK --> VALIDATE_FB_DATES["🛡️ validate_dates()<br/>on fallback metadata<br/>birth_year / death_year<br/>before returning from<br/>resolve_citation_fallback()"]
        VALIDATE_FB_DATES -->|"book or person<br/>(corrected dates)"| ENRICH_STEP
        VALIDATE_FB_DATES -->|"still not_found"| ENRICH_STEP

        subgraph ENRICHMENT["Metadata Enrichment  (metadata_enricher.py)"]
            ENRICH_STEP["Enrich resolved citation<br/>skip enricher calls if<br/>fallback already provided data"]

            ENRICH_STEP -->|"need original_year"| ENRICH_BOOK["enrich_book(book_id, title, author)<br/>4-source cascade:<br/>1. Cache: dates_cache[book_id]<br/>2. Goodreads scraper:<br/>   get_original_publication_date()<br/>   handles 'BC' string → negative int<br/>   skips web_ and manual_run IDs<br/>3. Wikipedia web:<br/>   wiki.get_book_info(title)<br/>   parse year from date strings<br/>4. LLM fallback:<br/>   _lookup_book_year(title, author)<br/>   regex extract -?\\d{3,4}<br/>→ caches to dates_updates[book_id]"]

            ENRICH_STEP -->|"need birth/death"| ENRICH_AUTHOR["enrich_author(author_name)<br/>4-source cascade + validation"]
            ENRICH_AUTHOR --> EA_CACHE{"authors_cache<br/>or authors_updates<br/>has author_name?"}
            EA_CACHE -->|"hit"| EA_CACHED["Return cached meta dict<br/>⚠️ entries cached BEFORE<br/>validate_dates() was added<br/>are NOT retroactively fixed.<br/>Use scripts/fix_metadata_errors.py<br/>to clean old cache entries."]
            EA_CACHE -->|"miss"| EA_WIKI_DB["Source 2: Local Wiki DB<br/>wiki_catalog.find_people(<br/>  name=author_name, limit=1)<br/>→ birth_year, death_year,<br/>  canonical_name from title field"]
            EA_WIKI_DB -->|"found"| EA_CHOKEPOINT
            EA_WIKI_DB -->|"miss or error"| EA_WIKI_WEB["Source 3: Wikipedia Web Scraper<br/>wiki.get_person_dates(author_name)<br/>→ parse 'born'/'died' strings<br/>regex \\d{3,4} for year extraction<br/>detect BC/BCE suffix → negate year<br/>skip if response has 'error' key<br/>or raw HTML dump >500 chars"]
            EA_WIKI_WEB -->|"found"| EA_CHOKEPOINT
            EA_WIKI_WEB -->|"miss or error"| EA_LLM["Source 4: LLM Fallback<br/>_lookup_author_bio(name)<br/>→ JSON: {birth_year, death_year,<br/>  main_genre, nationality}<br/>strips markdown code fences"]
            EA_LLM --> EA_LLM_VALIDATE["🛡️ validate_dates()<br/>on LLM bio response<br/>BEFORE returning to<br/>enrich_author() caller<br/>⚠️ LLM path is validated<br/>TWICE: here + chokepoint"]
            EA_LLM_VALIDATE --> EA_CHOKEPOINT

            EA_CHOKEPOINT["🛡️ validate_dates() — CHOKEPOINT<br/>runs on ALL non-cached results<br/>before cache write. Checks:<br/>• birth>0, death<0, plausible → flip death sign<br/>• birth<0, death>0, plausible → flip birth sign<br/>• both<0, death < birth → flip both if plausible, else null<br/>• birth>0, death<0, implausible → null death<br/>• BC-to-AD: birth<0, death>0,<br/>  abs(birth)+death < 120 → keep (legit BC person)<br/>  else → null birth<br/>• birth>death, both>0 → null both (wrong person)<br/>• lifespan > 200 years → null both (wrong person)<br/>corrections logged as WARNING"]
            EA_CHOKEPOINT --> EA_CACHE_WRITE["Cache write:<br/>authors_updates[name] = meta<br/>authors_cache[name] = meta<br/>(in-memory, flushed later<br/>by enricher.save())"]
            EA_CACHE_WRITE --> EA_MERGE_WIKI["Merge birth/death into<br/>wiki_match / target_person<br/>only if not already present"]

            ENRICH_BOOK --> BUILD_EDGE_PREP
            EA_CACHED --> BUILD_EDGE_PREP
            EA_MERGE_WIKI --> BUILD_EDGE_PREP
            BUILD_EDGE_PREP["metadata.update(enrichment)<br/>merge original_year +<br/>author_meta into metadata"]
        end

        BUILD_EDGE["Build result_dict:<br/>{raw: citation,<br/> goodreads_match: metadata or null,<br/> wikipedia_match: wiki_match,<br/> edge: {target_type,<br/>  target_book_id,<br/>  target_author_ids[],<br/>  target_person: wiki_match}}"]
        BUILD_EDGE_PREP --> BUILD_EDGE

        CACHE_RESULT --> RESULTS
        BUILD_EDGE --> ADD_AUTHOR_CACHE["_add_to_author_cache()<br/>cache by _normalize_author(name)<br/>also cache bare last name<br/>for fuzzy matching later<br/>(e.g. 'Plutarch' from<br/>'Lucius Mestrius Plutarch')"]
        ADD_AUTHOR_CACHE --> RESULTS["Append to results[]"]
        RESULTS -->|"every 5 results"| CHECKPOINT[("💾 .checkpoint.json<br/>{source: meta,<br/>citations: results,<br/>complete: false}")]

        RESULTS --> STATS_REPORT["Print resolution summary:<br/>total, cache_hits,<br/>workflow_success (% rate),<br/>not_found, errors,<br/>fallback_triggered/success,<br/>enrichment_success"]

        STATS_REPORT --> POST_DEDUP["🔀 _dedup_resolved_citations(results)<br/>POST-RESOLUTION DEDUP<br/>catches duplicates that survive<br/>Stage 2 preprocessing because<br/>they only become identical after<br/>Goodreads/Wikipedia resolution.<br/><br/>1. Group by (norm_author, norm_title):<br/>   _normalize_author(): strip accents,<br/>   lowercase, remove ./comma,<br/>   strip 'St.'/'Saint' prefix<br/>   _normalize_title(): lowercase,<br/>   strip articles (the/a/an/de/<br/>   les/la/le/il/el), rm punctuation<br/>2. Skip groups with < 2 entries<br/>   or all same book_id<br/>3. Pick keeper per group:<br/>   prefer real GR ID over web_ prefix<br/>   (_is_real_gr_id check)<br/>   if tie: prefer more raw.count<br/>4. Merge into keeper:<br/>   contexts[] (deduplicated via set)<br/>   commentaries[] (deduplicated)<br/>   count = sum of all counts<br/>5. Remove merged duplicates<br/>6. Log each merge + total count"]

        POST_DEDUP --> SAVE_ENRICHER["enricher.save()<br/>flush dates_updates →<br/>  dates_json (disk)<br/>flush authors_updates →<br/>  author_meta_json (disk)<br/>both sorted + indented JSON"]
    end

    SAVE_ENRICHER --> FINAL_OUT[/"final_citations_metadata_goodreads/<br/>BookID.json<br/>{source: {title, authors,<br/>publication_year, author_metadata},<br/>citations: [{raw, goodreads_match,<br/>wikipedia_match, edge}]}<br/>dates validated, duplicates merged"/]

    FINAL_OUT --> CLEANUP["Remove .checkpoint.json<br/>(only on successful completion)"]
    CLEANUP --> REGISTER

    %% ── Frontend Registration ─────────────────────────────
    subgraph FRONTEND["Frontend"]
        REGISTER["register_dataset.py<br/>copy JSONs to frontend/data/<br/>create manifest.json listing files"]
        REGISTER --> DATASETS_JSON[/"datasets.json<br/>{name, path, covers[]}"/]
        REGISTER --> MANIFEST[/"data/library_name/manifest.json<br/>['book1.json', 'book2.json']"/]
        MANIFEST --> D3["D3.js Visualization<br/>index.html<br/>loadDataset → processData → render"]
        DATASETS_JSON --> D3
    end

    %% ── Maintenance Scripts (post-hoc) ────────────────────
    FINAL_OUT -.->|"retroactive fix<br/>for old data"| MAINT_FIX["scripts/fix_metadata_errors.py<br/>applies same validate_dates() logic<br/>to authors_metadata.json +<br/>all frontend JSON files<br/>--dry-run to preview"]
    FINAL_OUT -.->|"retroactive dedup<br/>for old data"| MAINT_DEDUP["scripts/dedup_citations.py<br/>applies same dedup logic<br/>to frontend JSON files<br/>--dry-run to preview"]

    %% ── Styling ───────────────────────────────────────────
    classDef stage fill:#1a1a2e,stroke:#d4a574,color:#e8e6e3
    classDef io fill:#0d1117,stroke:#4a6fa5,color:#c9d1d9
    classDef llm fill:#2d1b3d,stroke:#b48ead,color:#e8e6e3
    classDef db fill:#1b2d2a,stroke:#a3be8c,color:#e8e6e3
    classDef checkpoint fill:#2d2a1b,stroke:#ebcb8b,color:#e8e6e3
    classDef validation fill:#2d1b1b,stroke:#bf616a,color:#e8e6e3
    classDef maintenance fill:#1b1b2d,stroke:#88c0d0,color:#c9d1d9,stroke-dasharray: 5 5

    class STAGE0,STAGE1,STAGE2,STAGE3,STAGE4 stage
    class INPUT,RAW_OUT,PRE_OUT,VAL_OUT,FINAL_OUT,ENRICHED_META io
    class PARALLEL_LLM,VAL_LLM,LLM_SOURCE,GEN_Q,VALIDATE_GR,VALIDATE_WIKI,WEB_FALLBACK,EA_LLM llm
    class GR_LOOKUP,SEARCH_GR,SEARCH_WIKI,EA_WIKI_DB db
    class CHECKPOINT checkpoint
    class VALIDATE_FB_DATES,EA_LLM_VALIDATE,EA_CHOKEPOINT,POST_DEDUP validation
    class MAINT_FIX,MAINT_DEDUP maintenance
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
| `--model` | deepseek/deepseek-v3.2 | LLM model ID |
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
