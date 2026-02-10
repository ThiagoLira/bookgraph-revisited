#!/usr/bin/env python3
"""Backfill rich Goodreads metadata into source book records in frontend data files.

Source books in existing pipeline output only have sparse metadata (title, authors,
publication_year). This script looks up each source book in the Goodreads catalog
and merges in the full metadata (description, average_rating, num_pages, publisher,
link, isbn, etc.) — the same fields that cited books already have.

Usage:
    uv run python scripts/backfill_source_metadata.py [--dry-run] [--verbose]
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lib.bibliography_agent.bibliography_tool import SQLiteGoodreadsCatalog

FRONTEND_DATA = ROOT / "frontend" / "data"
BOOKS_DB = ROOT / "datasets" / "books_index.db"


def backfill_file(filepath, catalog, dry_run=False, verbose=False):
    """Backfill source metadata in a single file. Returns list of descriptions."""
    with open(filepath) as f:
        data = json.load(f)

    source = data.get("source", {})
    title = source.get("title", "")
    goodreads_id = source.get("goodreads_id")

    if not title:
        return []

    # Check if already enriched (has description or link)
    if source.get("description") or source.get("link"):
        if verbose:
            print(f"  [skip] {title} — already has rich metadata")
        return []

    # Look up in catalog
    try:
        matches = catalog.find_books(title=title, limit=3)
    except Exception as e:
        print(f"  [error] {title}: {e}")
        return []

    if not matches:
        if verbose:
            print(f"  [miss] {title} — no catalog match")
        return []

    # Find match with same ID, or fallback to best match
    book_match = None
    for m in matches:
        if goodreads_id and str(m.get("book_id")) == str(goodreads_id):
            book_match = m
            break
    if not book_match:
        book_match = matches[0]

    # Merge fields that don't already exist in source
    added_fields = []
    for k, v in book_match.items():
        if v is not None and k not in source:
            source[k] = v
            added_fields.append(k)

    if not added_fields:
        if verbose:
            print(f"  [skip] {title} — no new fields to add")
        return []

    desc = f"{title}: added {len(added_fields)} fields ({', '.join(sorted(added_fields)[:5])}{'...' if len(added_fields) > 5 else ''})"

    if verbose or dry_run:
        print(f"  [fill] {desc}")

    if not dry_run:
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")

    return [desc]


def main():
    parser = argparse.ArgumentParser(description="Backfill source book metadata from Goodreads catalog")
    parser.add_argument("--dry-run", action="store_true", help="Report without modifying files")
    parser.add_argument("--verbose", action="store_true", help="Print each operation")
    args = parser.parse_args()

    catalog = SQLiteGoodreadsCatalog(BOOKS_DB)
    all_fills = []

    for fp in sorted(FRONTEND_DATA.glob("**/final_citations_metadata_goodreads/*.json")):
        fills = backfill_file(fp, catalog, dry_run=args.dry_run, verbose=args.verbose)
        all_fills.extend(fills)

    # Also check top-level data files (registered datasets)
    for fp in sorted(FRONTEND_DATA.glob("**/*.json")):
        if fp.name in ("manifest.json", "original_publication_dates.json", "authors_metadata.json"):
            continue
        if "raw_extracted_citations" in str(fp) or "preprocessed_extracted_citations" in str(fp):
            continue
        if "final_citations_metadata_goodreads" in str(fp):
            continue

        fills = backfill_file(fp, catalog, dry_run=args.dry_run, verbose=args.verbose)
        all_fills.extend(fills)

    print(f"\nTotal backfills: {len(all_fills)}")
    if args.dry_run:
        print("(dry-run mode — no files were modified)")


if __name__ == "__main__":
    sys.exit(main())
