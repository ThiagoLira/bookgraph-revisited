#!/usr/bin/env python3
"""Deduplicate citations within each frontend data file.

Finds citations by the same author with essentially the same title but different
Goodreads book IDs (different editions), and merges them into one entry.

Merge strategy:
- Keep the citation with the real Goodreads ID (not web_ prefixed)
- If both are real or both are web_, keep the one with more contexts
- Merge contexts, commentaries, and sum counts from the duplicate

Usage:
    uv run python scripts/dedup_citations.py [--dry-run] [--verbose]
"""

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DATA = ROOT / "frontend" / "data"


def normalize_title(title):
    """Normalize a title for comparison."""
    t = title.lower().strip()
    # Remove common prefixes
    for prefix in ["the ", "a ", "an ", "de ", "on ", "les ", "la ", "le ", "il ", "el "]:
        if t.startswith(prefix):
            t = t[len(prefix):]
    # Remove punctuation
    t = re.sub(r'[^\w\s]', '', t)
    t = re.sub(r'\s+', ' ', t).strip()
    return t


def is_real_gr_id(book_id):
    """Check if a book ID is a real Goodreads numeric ID (not web_ prefixed)."""
    if book_id is None:
        return False
    return not str(book_id).startswith("web_")


def pick_keeper(cit_a, idx_a, cit_b, idx_b):
    """Choose which citation to keep and which to merge away.

    Returns (keeper_cit, keeper_idx, dupe_cit, dupe_idx).
    """
    id_a = cit_a.get("edge", {}).get("target_book_id")
    id_b = cit_b.get("edge", {}).get("target_book_id")

    real_a = is_real_gr_id(id_a)
    real_b = is_real_gr_id(id_b)

    # Prefer real Goodreads ID
    if real_a and not real_b:
        return cit_a, idx_a, cit_b, idx_b
    if real_b and not real_a:
        return cit_b, idx_b, cit_a, idx_a

    # Both real or both web_: prefer the one with more contexts
    count_a = cit_a.get("raw", {}).get("count", 0)
    count_b = cit_b.get("raw", {}).get("count", 0)
    if count_a >= count_b:
        return cit_a, idx_a, cit_b, idx_b
    return cit_b, idx_b, cit_a, idx_a


def merge_citations(keeper, dupe):
    """Merge dupe's data into keeper."""
    kr = keeper.get("raw", {})
    dr = dupe.get("raw", {})

    # Merge contexts (deduplicated)
    existing = set(kr.get("contexts", []))
    for ctx in dr.get("contexts", []):
        if ctx not in existing:
            kr.setdefault("contexts", []).append(ctx)
            existing.add(ctx)

    # Merge commentaries
    existing_comm = set(kr.get("commentaries", []))
    for comm in dr.get("commentaries", []):
        if comm not in existing_comm:
            kr.setdefault("commentaries", []).append(comm)
            existing_comm.add(comm)

    # Sum counts
    kr["count"] = kr.get("count", 0) + dr.get("count", 0)


def dedup_file(filepath, dry_run=False, verbose=False):
    """Deduplicate citations within a single file. Returns list of merge descriptions."""
    with open(filepath) as f:
        data = json.load(f)

    citations = data.get("citations", [])
    if not citations:
        return []

    # Group by normalized (author, title)
    groups = defaultdict(list)  # (author_norm, title_norm) -> [(idx, citation)]
    for i, cit in enumerate(citations):
        raw = cit.get("raw", {})
        title = raw.get("title", "")
        if not title:
            continue
        author = raw.get("canonical_author", raw.get("author", "?")).lower()
        norm = normalize_title(title)
        groups[(author, norm)].append((i, cit))

    # Find groups with multiple entries that have different book_ids
    indices_to_remove = set()
    merges = []
    rel = filepath.relative_to(ROOT)

    for (author, norm_title), entries in groups.items():
        if len(entries) < 2:
            continue

        # Further group by book_id to find actual duplicates
        by_id = defaultdict(list)
        for idx, cit in entries:
            bid = cit.get("edge", {}).get("target_book_id")
            by_id[bid].append((idx, cit))

        if len(by_id) < 2:
            continue

        # Merge all into one keeper
        all_entries = [(idx, cit) for idx, cit in entries if idx not in indices_to_remove]
        if len(all_entries) < 2:
            continue

        keeper_idx, keeper_cit = all_entries[0]
        # Find the best keeper (real GR ID, most contexts)
        for idx, cit in all_entries[1:]:
            keeper_cit, keeper_idx, _, _ = pick_keeper(keeper_cit, keeper_idx, cit, idx)

        # Merge all others into keeper
        for idx, cit in all_entries:
            if idx == keeper_idx:
                continue
            dupe_title = cit.get("raw", {}).get("title", "?")
            dupe_id = cit.get("edge", {}).get("target_book_id")
            keeper_id = keeper_cit.get("edge", {}).get("target_book_id")
            keeper_title = keeper_cit.get("raw", {}).get("title", "?")

            merge_citations(keeper_cit, cit)
            indices_to_remove.add(idx)
            merges.append(
                f"[{rel}] [{author}] merged '{dupe_title}' (id={dupe_id}) "
                f"into '{keeper_title}' (id={keeper_id})"
            )

    if not merges:
        return []

    if verbose or dry_run:
        for m in merges:
            print(f"  {m}")

    if not dry_run:
        # Remove duplicates (iterate in reverse to preserve indices)
        for idx in sorted(indices_to_remove, reverse=True):
            citations.pop(idx)
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")

    return merges


def main():
    parser = argparse.ArgumentParser(description="Deduplicate citations in frontend data")
    parser.add_argument("--dry-run", action="store_true", help="Report without modifying files")
    parser.add_argument("--verbose", action="store_true", help="Print each merge")
    args = parser.parse_args()

    all_merges = []

    for fp in sorted(FRONTEND_DATA.glob("**/*.json")):
        if fp.name in ("manifest.json", "original_publication_dates.json", "authors_metadata.json"):
            continue
        if "raw_extracted_citations" in str(fp) or "preprocessed_extracted_citations" in str(fp):
            continue

        merges = dedup_file(fp, dry_run=args.dry_run, verbose=args.verbose)
        all_merges.extend(merges)

    print(f"\nTotal merges: {len(all_merges)}")
    if args.dry_run:
        print("(dry-run mode — no files were modified)")


if __name__ == "__main__":
    sys.exit(main())
