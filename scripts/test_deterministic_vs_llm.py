#!/usr/bin/env python3
"""
Head-to-head comparison: deterministic query generation vs LLM pipeline results.

Loads final output JSONs from the philosophy_stress_test dataset (2,331 citations
with known match results from the LLM-based pipeline), generates deterministic
queries, runs them through the REAL search functions, and compares results.

Usage:
    uv run python scripts/test_deterministic_vs_llm.py \
        --data-dir frontend/data/philosophy_stress_test \
        --verbose
"""

import argparse
import json
import sys
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import re

# Ensure repo root is on path
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from lib.bibliography_agent.deterministic_queries import generate_queries_deterministic
from lib.bibliography_agent.bibliography_tool import (
    SQLiteGoodreadsCatalog,
    GoodreadsAuthorCatalog,
    SQLiteWikiPeopleIndex,
)
from lib.bibliography_agent.events import SearchQuery


def fuzzy_token_sort_ratio(s1: str, s2: str) -> int:
    """Same fuzzy scoring used in the workflow."""
    if not s1 or not s2:
        return 0
    tokens1 = sorted(re.findall(r'\w+', s1.lower()))
    tokens2 = sorted(re.findall(r'\w+', s2.lower()))
    sorted_s1 = " ".join(tokens1)
    sorted_s2 = " ".join(tokens2)
    matcher = SequenceMatcher(None, sorted_s1, sorted_s2)
    return int(matcher.ratio() * 100)


def load_author_aliases() -> Dict[str, str]:
    """Load author aliases in the same format as CitationWorkflow."""
    aliases_path = REPO_ROOT / "datasets" / "author_aliases.json"
    aliases = {}
    if aliases_path.exists():
        raw = json.loads(aliases_path.read_text())
        for canonical, variants in raw.items():
            aliases[canonical.lower()] = canonical
            for v in variants:
                aliases[v.lower()] = canonical
    return aliases


def load_citations(data_dir: Path) -> List[Tuple[Dict, Dict, str]]:
    """Load all citations from frontend data files.

    Returns list of (raw_citation, full_citation_entry, source_file) tuples.
    """
    manifest_path = data_dir / "manifest.json"
    if manifest_path.exists():
        filenames = json.loads(manifest_path.read_text())
    else:
        filenames = [f.name for f in sorted(data_dir.glob("*.json")) if f.name != "manifest.json"]

    citations = []
    for fname in filenames:
        fpath = data_dir / fname
        if not fpath.exists():
            continue
        data = json.loads(fpath.read_text())
        for cit in data.get("citations", []):
            raw = cit.get("raw", {})
            citations.append((raw, cit, fname))

    return citations


def search_book(
    queries: List[SearchQuery],
    book_catalog: SQLiteGoodreadsCatalog,
    citation_raw: Dict,
) -> Optional[Dict]:
    """Run book queries and pick best candidate using fuzzy scoring."""
    all_results = []
    seen_ids = set()

    for q in queries:
        if not q.title and not q.author:
            continue
        try:
            matches = book_catalog.find_books(title=q.title, author=q.author, limit=5)
        except (ValueError, Exception):
            continue
        for m in matches:
            mid = m.get("book_id")
            if mid and mid not in seen_ids:
                all_results.append(m)
                seen_ids.add(mid)

    if not all_results:
        return None

    # Score and pick best by fuzzy match
    source_title = citation_raw.get("title", "")
    source_author = citation_raw.get("author", "")

    best_score = 0
    best_match = None
    for res in all_results:
        title_score = fuzzy_token_sort_ratio(source_title, res.get("title", "")) if source_title else 0
        author_score = fuzzy_token_sort_ratio(source_author, ", ".join(res.get("authors", []))) if source_author else 0
        # Combined score weighted toward title for book mode
        score = title_score * 0.6 + author_score * 0.4 if source_title else author_score
        if score > best_score:
            best_score = score
            best_match = res

    # Apply minimum threshold
    if best_score < 40:
        return None

    return best_match


def search_author(
    queries: List[SearchQuery],
    author_catalog: GoodreadsAuthorCatalog,
    citation_raw: Dict,
) -> Optional[Dict]:
    """Run author queries and pick best candidate."""
    all_results = []
    seen_ids = set()

    for q in queries:
        name = q.author or q.title
        if not name:
            continue
        matches = author_catalog.find_authors(query=name, limit=5)
        for m in matches:
            mid = m.get("author_id")
            if mid and mid not in seen_ids:
                all_results.append(m)
                seen_ids.add(mid)

    if not all_results:
        return None

    source_author = citation_raw.get("author", "")
    best_score = 0
    best_match = None
    for res in all_results:
        score = fuzzy_token_sort_ratio(source_author, res.get("name", ""))
        if score > best_score:
            best_score = score
            best_match = res

    if best_score < 50:
        return None

    return best_match


def search_person(
    queries: List[SearchQuery],
    wiki_catalog: Optional[SQLiteWikiPeopleIndex],
    citation_raw: Dict,
) -> Optional[Dict]:
    """Run Wikipedia people queries and pick best candidate."""
    if wiki_catalog is None:
        return None

    all_results = []
    seen_ids = set()

    for q in queries:
        name = q.author
        if not name:
            continue
        try:
            matches = wiki_catalog.find_people(name=name, limit=5)
        except Exception:
            continue
        for m in matches:
            mid = m.get("page_id")
            if mid and mid not in seen_ids:
                all_results.append(m)
                seen_ids.add(mid)

    if not all_results:
        return None

    source_author = citation_raw.get("author", "")
    best_score = 0
    best_match = None
    for res in all_results:
        score = fuzzy_token_sort_ratio(source_author, res.get("title", ""))
        if score > best_score:
            best_score = score
            best_match = res

    if best_score < 50:
        return None

    return best_match


def compare_citation(
    raw: Dict,
    full_entry: Dict,
    book_catalog: SQLiteGoodreadsCatalog,
    author_catalog: GoodreadsAuthorCatalog,
    wiki_catalog: Optional[SQLiteWikiPeopleIndex],
    author_aliases: Dict[str, str],
) -> Dict[str, Any]:
    """Compare deterministic result vs LLM result for one citation.

    Returns a dict with comparison details.
    """
    edge = full_entry.get("edge", {})
    llm_type = edge.get("target_type", "not_found")
    llm_book_id = edge.get("target_book_id")
    llm_author_ids = edge.get("target_author_ids", [])
    llm_person = edge.get("target_person", {})
    llm_page_id = str(llm_person.get("page_id", "")) if llm_person else ""

    title = (raw.get("title") or "").strip()
    mode = "book" if title else "author_only"

    # Generate deterministic queries
    queries = generate_queries_deterministic(raw, author_aliases)

    result = {
        "raw": raw,
        "mode": mode,
        "llm_type": llm_type,
        "queries_generated": len(queries),
    }

    if mode == "book":
        det_match = search_book(queries, book_catalog, raw)
        det_book_id = det_match.get("book_id") if det_match else None

        if llm_type == "not_found" and det_book_id is None:
            result["category"] = "both_miss"
        elif llm_type == "not_found" and det_book_id is not None:
            result["category"] = "det_found_extra"
            result["det_book_id"] = det_book_id
            result["det_title"] = det_match.get("title", "")
        elif llm_book_id is None and det_book_id is None:
            # LLM found author/person but not book, det also missed
            result["category"] = "both_miss"
        elif det_book_id is None:
            result["category"] = "det_miss"
            result["llm_book_id"] = llm_book_id
        elif str(det_book_id) == str(llm_book_id):
            result["category"] = "match"
        else:
            result["category"] = "different"
            result["det_book_id"] = det_book_id
            result["llm_book_id"] = llm_book_id
            result["det_title"] = det_match.get("title", "")
            result["llm_title"] = (full_entry.get("goodreads_match") or {}).get("title", "")

    else:
        # Author-only mode: compare author_id or page_id
        det_author = search_author(queries, author_catalog, raw)
        det_person = search_person(queries, wiki_catalog, raw)

        det_author_id = det_author.get("author_id") if det_author else None
        det_page_id = str(det_person.get("page_id", "")) if det_person else None

        # Determine det_type
        if det_author_id:
            det_type = "author"
        elif det_page_id:
            det_type = "person"
        else:
            det_type = "not_found"

        if llm_type == "not_found" and det_type == "not_found":
            result["category"] = "both_miss"
        elif llm_type == "not_found" and det_type != "not_found":
            result["category"] = "det_found_extra"
        elif det_type == "not_found":
            result["category"] = "det_miss"
        else:
            # Both found something — compare IDs
            llm_aid = llm_author_ids[0] if llm_author_ids else None

            if llm_type == "author" and det_type == "author":
                if str(det_author_id) == str(llm_aid):
                    result["category"] = "match"
                else:
                    result["category"] = "different"
                    result["det_author_id"] = det_author_id
                    result["llm_author_id"] = llm_aid
            elif llm_type == "person" and det_type == "person":
                if det_page_id == llm_page_id:
                    result["category"] = "match"
                else:
                    result["category"] = "different"
            elif llm_type == "author" and det_type == "person":
                # Both found something, just different sources
                result["category"] = "match"  # close enough
            elif llm_type == "person" and det_type == "author":
                result["category"] = "match"  # close enough
            else:
                result["category"] = "different"

        result["det_type"] = det_type
        result["det_author_id"] = det_author_id
        result["det_page_id"] = det_page_id

    return result


def main():
    parser = argparse.ArgumentParser(
        description="Compare deterministic query generation vs LLM pipeline results."
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=REPO_ROOT / "frontend" / "data" / "philosophy_stress_test",
        help="Directory with frontend JSON data files.",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show detailed output for each miss.",
    )
    parser.add_argument(
        "--books-db",
        type=Path,
        default=REPO_ROOT / "datasets" / "books_index.db",
    )
    parser.add_argument(
        "--authors-json",
        type=Path,
        default=REPO_ROOT / "datasets" / "goodreads_book_authors.json",
    )
    parser.add_argument(
        "--wiki-db",
        type=Path,
        default=REPO_ROOT / "datasets" / "wiki_people_index.db",
    )
    args = parser.parse_args()

    print(f"Loading citations from {args.data_dir}...")
    citations = load_citations(args.data_dir)
    print(f"Loaded {len(citations)} citations.")

    print("Loading author aliases...")
    author_aliases = load_author_aliases()
    print(f"Loaded {len(author_aliases)} alias entries.")

    print("Initializing search catalogs...")
    book_catalog = SQLiteGoodreadsCatalog(db_path=args.books_db)
    author_catalog = GoodreadsAuthorCatalog(authors_path=args.authors_json)

    wiki_catalog = None
    if args.wiki_db.exists():
        wiki_catalog = SQLiteWikiPeopleIndex(db_path=args.wiki_db)
    else:
        print(f"WARNING: Wiki DB not found at {args.wiki_db}, skipping Wiki lookups.")

    print("\nRunning comparison...")
    print("=" * 70)

    counts = Counter()
    det_misses = []
    different_cases = []
    det_extras = []

    for i, (raw, full_entry, source_file) in enumerate(citations):
        result = compare_citation(
            raw, full_entry, book_catalog, author_catalog, wiki_catalog, author_aliases
        )
        category = result["category"]
        counts[category] += 1

        if category == "det_miss":
            det_misses.append((raw, full_entry, source_file, result))
        elif category == "different":
            different_cases.append((raw, full_entry, source_file, result))
        elif category == "det_found_extra":
            det_extras.append((raw, full_entry, source_file, result))

        # Progress
        if (i + 1) % 200 == 0:
            print(f"  Processed {i + 1}/{len(citations)}...")

    # --- Report ---
    total = len(citations)
    print(f"\n{'=' * 70}")
    print(f"RESULTS: {total} citations")
    print(f"{'=' * 70}")

    for cat in ["match", "different", "det_miss", "both_miss", "det_found_extra"]:
        n = counts[cat]
        pct = n / total * 100 if total else 0
        label = {
            "match": "MATCH (same ID)",
            "different": "DIFFERENT (both found, different ID)",
            "det_miss": "DET_MISS (det missed, LLM found)",
            "both_miss": "BOTH_MISS (neither found)",
            "det_found_extra": "DET_EXTRA (det found, LLM missed)",
        }.get(cat, cat)
        print(f"  {label:50s} {n:5d}  ({pct:5.1f}%)")

    # Effective match rate: match + different (both found something)
    found_both = counts["match"] + counts["different"]
    llm_found = found_both + counts["det_miss"]
    if llm_found > 0:
        effective_rate = found_both / llm_found * 100
        print(f"\n  Effective rate (det found / LLM found): {found_both}/{llm_found} = {effective_rate:.1f}%")

    # --- Detailed misses ---
    if args.verbose and det_misses:
        print(f"\n{'=' * 70}")
        print(f"DETAILED DET_MISS CASES ({len(det_misses)} total)")
        print(f"{'=' * 70}")
        for raw, full_entry, source_file, result in det_misses[:50]:
            title = raw.get("title", "")
            author = raw.get("author", "")
            llm_match = full_entry.get("goodreads_match", {})
            llm_title = llm_match.get("title", "(author match)")
            llm_bid = result.get("llm_book_id", "")
            mode = result.get("mode", "?")
            nq = result.get("queries_generated", 0)
            print(f"\n  [{source_file}] mode={mode} queries={nq}")
            print(f"    Citation: title='{title}', author='{author}'")
            print(f"    LLM found: '{llm_title}' (book_id={llm_bid})")

        if len(det_misses) > 50:
            print(f"\n  ... and {len(det_misses) - 50} more")

    if args.verbose and different_cases:
        print(f"\n{'=' * 70}")
        print(f"DIFFERENT ID CASES (first 20 of {len(different_cases)})")
        print(f"{'=' * 70}")
        for raw, full_entry, source_file, result in different_cases[:20]:
            title = raw.get("title", "")
            author = raw.get("author", "")
            print(f"\n  [{source_file}] mode={result.get('mode')}")
            print(f"    Citation: title='{title}', author='{author}'")
            if result.get("det_title"):
                print(f"    Det: '{result['det_title']}' (id={result.get('det_book_id')})")
            if result.get("llm_title"):
                print(f"    LLM: '{result['llm_title']}' (id={result.get('llm_book_id')})")

    print()


if __name__ == "__main__":
    main()
