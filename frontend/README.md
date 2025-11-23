Interactive citation graph (D3.js)
==================================

Renders a book/author citation graph from stage-3 JSON outputs.

How it works
------------
- Loads all `*.json` files from a folder of stage-3 outputs (default: `frontend/data` next to this HTML).
- Builds nodes for books (`book_id`) and authors (`author_id`).
- Creates edges:
  - source book → cited book (if `edge.target_book_id`)
  - source book → cited author(s) (if `edge.target_author_ids`)
- Deduplicates nodes/edges, skips citations without Goodreads IDs.

Run locally
-----------
```bash
# From repo root
python -m http.server 8000
# Open in browser (uses frontend/data by default):
http://localhost:8000/frontend/index.html

# Or point at another folder:
# http://localhost:8000/frontend/index.html?dataDir=calibre_outputs/calibre_bookgraph/final_citations_metadata_goodreads
```

Controls
--------
- Drag nodes to reposition; scroll/drag to zoom/pan.
- Hover to highlight neighbors; click to fix/unfix node position.
- Legend toggles: hide/show books or authors.

Notes
-----
- Directory listing must be accessible (e.g., via `python -m http.server`) so the viewer can discover JSON filenames.
- If `dataDir` is omitted, the default path above is used.
