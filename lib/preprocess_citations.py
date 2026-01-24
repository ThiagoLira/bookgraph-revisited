#!/usr/bin/env python3
"""
Deduplicate and heuristically merge citation outputs from run_single_file.py.

Usage:
    uv run python preprocess_citations.py book.json > book.cleaned.json
"""

import argparse
import json
import re
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence


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


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().casefold()


def normalize_title(title: str) -> str:
    """
    Normalize titles for loose dedup:
    - Lowercase/strip
    - Split on common separators (:, -, _, (, [) and take the leading chunk
    - Collapse non-alphanumerics to spaces
    """
    lowered = title.strip().casefold()
    for sep in (":", "-", "_", "(", "["):
        if sep in lowered:
            lowered = lowered.split(sep, 1)[0]
    cleaned = re.sub(r"[^a-z0-9]+", " ", lowered)
    return cleaned.strip()


def collapse_variant_titles(citations: List[Citation]) -> List[Citation]:
    """
    Deduplicate obvious title variants for the same author by using a
    normalized prefix of the title.
    """
    seen = set()
    result: List[Citation] = []
    for citation in citations:
        author = citation.get("author") or ""
        title = citation.get("title") or ""
        canon_author = normalize_text(author)
        canon_title = normalize_title(title)
        key = (canon_author, canon_title) if canon_title else (canon_author, title.casefold())
        if key in seen:
            continue
        seen.add(key)
        result.append(citation)
    return result


def drop_self_references(
    citations: List[Citation],
    source_title: Optional[str],
    source_authors: Optional[Sequence[str]],
) -> List[Citation]:
    """
    Remove citations that point back to the same book/author when we know the source.
    """
    if not source_title and not source_authors:
        return citations
    norm_title = normalize_title(source_title or "")
    norm_authors = {normalize_text(a) for a in (source_authors or []) if a}
    result: List[Citation] = []
    for citation in citations:
        c_title = citation.get("title") or ""
        c_author = citation.get("author") or ""
        canon_title = normalize_title(c_title)
        canon_author = normalize_text(c_author)
        is_same_author = norm_authors and canon_author in norm_authors
        is_same_title = norm_title and canon_title and canon_title == norm_title
        if is_same_author and (is_same_title or not c_title.strip()):
            # Drop self-citations (same author + same title or no title)
            continue
        result.append(citation)
    return result


HEURISTICS: List[Heuristic] = [
    placeholder_heuristic,
    collapse_author_only,
    collapse_variant_titles,
]


def apply_heuristics(
    citations: List[Citation],
    source_title: Optional[str],
    source_authors: Optional[Sequence[str]],
) -> List[Citation]:
    result = citations
    for heuristic in HEURISTICS:
        result = heuristic(result)
    result = drop_self_references(result, source_title, source_authors)
    return result


def preprocess_data(
    data: Dict[str, Any],
    source_name: str,
    source_title: Optional[str] = None,
    source_authors: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    # Extract
    citations: List[Citation] = []
    for chunk in data.get("chunks", []):
        for citation in chunk.get("citations", []):
            title = (citation.get("title") or "").strip()
            author = (citation.get("author") or "").strip()
            if not author:
                continue
            citations.append(
                {
                    "title": title,
                    "author": author,
                    "note": citation.get("note"),
                }
            )
            
    # Process
    citations = deduplicate_exact(citations)
    citations = apply_heuristics(citations, source_title, source_authors)
    
    return {
        "source": source_name,
        "total": len(citations),
        "citations": citations,
    }


def preprocess(
    path: Path,
    source_title: Optional[str] = None,
    source_authors: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return preprocess_data(
        data, 
        source_name=path.name,
        source_title=source_title, 
        source_authors=source_authors
    )


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
