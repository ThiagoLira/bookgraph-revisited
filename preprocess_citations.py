#!/usr/bin/env python3
"""
Deduplicate and heuristically merge citation outputs from run_single_file.py.

Usage:
    uv run python preprocess_citations.py book.json > book.cleaned.json
"""

import argparse
import json
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List


Citation = Dict[str, Any]
Heuristic = Callable[[List[Citation]], List[Citation]]


def load_citations(path: Path) -> List[Citation]:
    data = json.loads(path.read_text())
    rows: List[Citation] = []
    for chunk in data.get("chunks", []):
        for citation in chunk.get("citations", []):
            title = (citation.get("title") or "").strip()
            author = (citation.get("author") or "").strip()
            if not author:
                continue
            rows.append(
                {
                    "title": title,
                    "author": author,
                    "note": citation.get("note"),
                }
            )
    return rows


def deduplicate_exact(citations: Iterable[Citation]) -> List[Citation]:
    seen = set()
    deduped: List[Citation] = []
    for citation in citations:
        key = (citation["title"].casefold(), citation["author"].casefold())
        if key in seen:
            continue
        seen.add(key)
        deduped.append(citation)
    return deduped


def placeholder_heuristic(citations: List[Citation]) -> List[Citation]:
    """Placeholder for future merging heuristics."""
    return citations


def collapse_author_only(citations: List[Citation]) -> List[Citation]:
    """
    Keep only one entry per author when the title is empty/null.

    Example: repeated author mentions with no title (e.g., "Wagner") collapse to one.
    """

    seen_authors: Dict[str, Citation] = {}
    result: List[Citation] = []
    for citation in citations:
        title = (citation.get("title") or "").strip()
        author = citation.get("author")
        if not author:
            continue
        if not title:
            key = author.casefold()
            if key in seen_authors:
                continue
            seen_authors[key] = citation
            citation = {
                **citation,
                "title": "",
                "canonical_author": author.title(),
            }
        result.append(citation)
    return result


HEURISTICS: List[Heuristic] = [
    placeholder_heuristic,
    collapse_author_only,
]


def apply_heuristics(citations: List[Citation]) -> List[Citation]:
    result = citations
    for heuristic in HEURISTICS:
        result = heuristic(result)
    return result


def preprocess(path: Path) -> Dict[str, Any]:
    citations = load_citations(path)
    citations = deduplicate_exact(citations)
    citations = apply_heuristics(citations)
    return {
        "source": path.name,
        "total": len(citations),
        "citations": citations,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Preprocess citation JSON output.")
    ap.add_argument("json_path", type=Path, help="Path to run_single_file JSON.")
    args = ap.parse_args()

    result = preprocess(args.json_path)
    payload = json.dumps(result, indent=2, ensure_ascii=False)
    output_path = args.json_path.with_name(f"{args.json_path.stem}_filtered.json")
    output_path.write_text(payload)
    print(f"Wrote filtered citations to {output_path}")


if __name__ == "__main__":
    main()
