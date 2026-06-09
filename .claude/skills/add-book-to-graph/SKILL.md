---
name: add-book-to-graph
description: Ingest one or more plaintext books into the BookGraph frontend — run the citation-extraction pipeline, register + bake into frontend/data, then assess and fix the resulting dates/titles. Use when adding new source books to the graph (e.g. Project Gutenberg downloads, Calibre exports).
---

# Add Book(s) to the Graph

End-to-end workflow to turn a plaintext book into nodes/edges in the frontend graph.
The pipeline extracts **inline mentions of other authors/works** from the source text,
matches them to Goodreads/Wikipedia (for dates, ratings, portraits), and bakes a layout.

**Only process citation-rich non-fiction** (philosophy, history, criticism, science,
essays). Fiction/poetry/drama allude rather than cite and yield almost nothing as
*sources* — keep them as cited nodes. See `data_review/PROCUREMENT.md`.

## 0. Prereqs
- `OPENROUTER_API_KEY` lives in `.env` (the driver loads it automatically).
- Default LLM is `deepseek/deepseek-v4-flash` (set in `lib/cli_common.py`). Override with `--model`.
- Need a plaintext `.txt`. To fetch public-domain books: `python scripts/gutenberg_fetch.py search "<query>"` then `... get <id> "<slug>"` (writes to `gutenberg_downloads/`).

## 1. Ingest

**One book:**
```bash
uv run python scripts/ingest_books.py \
  --input gutenberg_downloads/hobbes_leviathan__pg3207.txt \
  --title "Leviathan" --author "Thomas Hobbes" \
  --name "Hobbes: Leviathan" --build
```

**A batch into ONE interconnected library** (recommended — the books cross-cite each other):
```bash
uv run python scripts/ingest_books.py \
  --manifest gutenberg_downloads/books.tsv \
  --output-dir outputs/single_runs/gutenberg_classics \
  --name "Gutenberg Classics" --build --workers 3
```
Manifest is TSV, one row per book: `filepath<TAB>title<TAB>author`. The `book_id` is
derived from a trailing `pgNNNNN`/`_NNNNN` in the filename.

What `--build` does: copies the stage-3 JSON to `frontend/data/<slug>/`, writes a
manifest, updates `frontend/datasets.json`, and runs the offline bake
(`frontend/build/build.mjs`). Outputs land in `outputs/` (gitignored); only the baked
`frontend/data/<slug>/` is committed.

## 2. Assess quality (always do this)
Dump every extracted citation with its match and eyeball it:
```bash
python3 - <<'PY'
import json
d=json.load(open('outputs/single_runs/<slug>/final_citations_metadata_goodreads/<id>.json'))
for c in sorted(d['citations'], key=lambda c:-c['raw'].get('count',0)):
    r=c['raw']; g=c.get('goodreads_match') or {}; w=c.get('wikipedia_match') or {}
    am=g.get('author_meta') or {}
    by=am.get('birth_year') or w.get('birth_year'); dy=am.get('death_year') or w.get('death_year')
    yr=g.get('original_year') or g.get('publication_year')
    print(f"{r.get('count',0):>3} {r.get('author','')[:24]:24} | {(g.get('title') or '')[:28]:28} {str(yr or ''):>6} | b{by} d{dy}")
PY
```
Check for the known failure modes:
- **Wrong-person matches** (ancient name → modern birth year, e.g. Juvenal b.1937).
- **BCE sign errors** (a BCE work with a positive year).
- **Edition-year contamination** (a reprint/translation year instead of original).
- **Duplicate-split nodes** (ligatures/accents: `Æschylus` vs `Aeschylus`; surname stubs).
- **Gray (unknown) region** = missing nationality.

## 3. Fix durably via the override layer (survives re-bakes)
Do NOT edit `baked.json` — it regenerates. Edit the build-time overrides, then re-bake.
See `memory/data-overrides-layer.md`.
- `datasets/data_overrides.json`:
  - `name_aliases`: `{ "<variant>": "<canonical>" }` — merge duplicate-split nodes.
  - `author_dates`: `{ "<name>": {birth_year, death_year} }` — fix Y-axis placement (BCE negative).
  - `books`: `{ "<name>": [ {match:"<current title>", year?, title?} ] }` — fix book year/title.
- `datasets/nationality_overrides.json`: `{ "<lowercased name>": "<demonym>" }` — fix gray nodes.

Re-bake the affected dataset + the merged graph:
```bash
cd frontend/build && node build.mjs --dataset <slug> && node build.mjs --all
```

> NOTE: `datasets/*.json` is gitignored. To version the override files, force-add them:
> `git add -f datasets/data_overrides.json datasets/nationality_overrides.json`.

## 4. Verify
- `frontend/data/<slug>/baked.json` exists and node count looks right.
- No `region:"unknown"` on notable nodes; no `year:null`.
- Serve locally: `python scripts/serve.py 8011` (gzips the payload).

## Files
- `scripts/ingest_books.py` — the driver (this skill's tool).
- `scripts/gutenberg_fetch.py` — search/download public-domain texts.
- `run_single_file.py` / `scripts/register_dataset.py` — the underlying steps.
