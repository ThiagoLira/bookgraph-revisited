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
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple


Citation = Dict[str, Any]
Heuristic = Callable[[List[Citation]], List[Citation]]


def load_citations(path: Path) -> List[Citation]:
    data = json.loads(path.read_text())
    rows: List[Citation] = []
    for chunk in data.get("chunks", []):
        for citation in chunk.get("citations", []):
            title = (citation.get("title") or "").strip()
            author = (citation.get("author") or "").strip()
            excerpt = (citation.get("citation_excerpt") or citation.get("note") or "").strip()
            
            if not author:
                continue
                
            rows.append(
                {
                    "title": title,
                    "author": author,
                    "count": 1,
                    "excerpts": [excerpt] if excerpt else [],
                }
            )
    return rows


def merge_citations(dest: Citation, src: Citation) -> None:
    """Merge source citation data into destination in-place."""
    dest["count"] += src["count"]
    # Append new excerpts, avoiding exact duplicates if desired, 
    # but for now just keeping all to see frequency/context.
    # We can dedupe excerpts later if they are identical.
    for exc in src["excerpts"]:
        if exc and exc not in dest["excerpts"]:
            dest["excerpts"].append(exc)


def deduplicate_exact(citations: Iterable[Citation]) -> List[Citation]:
    """
    Merge exact duplicates (same case-insensitive title and author).
    """
    merged: Dict[Tuple[str, str], Citation] = {}
    
    for citation in citations:
        title = citation["title"].strip()
        author = citation["author"].strip()
        key = (title.casefold(), author.casefold())
        
        if key in merged:
            merge_citations(merged[key], citation)
        else:
            # Store a copy to avoid mutating the original if it's reused elsewhere
            # though here we are consuming the list.
            merged[key] = citation.copy()
            
    return list(merged.values())


def filter_noise(citations: List[Citation]) -> List[Citation]:
    """
    Remove citations that are clearly noise or incomplete references.
    """
    # Regex for "Ibid", "Op. cit.", "Vol.", "p.", "pp."
    # Also filters strings that are just numbers or punctuation.
    noise_patterns = [
        r"^(ibid|op\.?\s*cit|loc\.?\s*cit|id\.|vol\.?|p\.?|pp\.?|page|chapter|bk\.?|book|part|section|c\.?|v\.?)$",
        r"^[\d\W]+$",  # Only numbers and symbols
    ]
    compiled_patterns = [re.compile(p, re.IGNORECASE) for p in noise_patterns]

    clean: List[Citation] = []
    for citation in citations:
        author = citation["author"]
        title = citation["title"]
        
        # Check author for noise
        is_noise = False
        for pattern in compiled_patterns:
            if pattern.match(author):
                is_noise = True
                break
        
        if is_noise:
            continue
            
        # If title exists, check it too (less strict, but "Ibid" as title is bad)
        if title:
            for pattern in compiled_patterns:
                if pattern.match(title):
                    # If title is noise, just clear it? Or drop citation?
                    # Usually if title is "Ibid", the author might be real, 
                    # but without a real title it's ambiguous. 
                    # For now, let's just clear the title if it's noise.
                    citation["title"] = ""
                    break
        
        clean.append(citation)
    return clean


def normalize_essay_titles(citations: List[Citation]) -> List[Citation]:
    """
    Detect titles that look like essay/chapter references ("On...", "Of...", "Chapter...")
    and clear the title so they can be merged into the author-only bucket.
    """
    # Patterns that suggest a non-book title
    # "On [Subject]", "Of [Subject]", "Chapter [X]", "Book [X]"
    # We want to be careful not to catch "On the Origin of Species" (Book) vs "On Friendship" (Essay)
    # This is heuristic.
    patterns = [
        r"^(on|of|concerning|regarding)\s+.+$",
        r"^(chapter|book|part|section|volume)\s+[\dIVX]+.*$",
    ]
    compiled = [re.compile(p, re.IGNORECASE) for p in patterns]

    for citation in citations:
        title = citation["title"]
        if not title:
            continue
            
        for pattern in compiled:
            if pattern.match(title):
                # Heuristic: if it matches, treat as "not a book title"
                # Clear title to allow merging with author
                citation["title"] = ""
                break
                
    return citations


def normalize_author_names(citations: List[Citation]) -> List[Citation]:
    """
    Normalize author names from "Last, First" to "First Last".
    Example: "Wallace, David Foster" -> "David Foster Wallace"
    """
    # Regex for "Word, Word Word..."
    # We want to be careful not to flip things that aren't names.
    # But usually "Author" field is a name.
    pattern = re.compile(r"^([A-Z][a-z\.\-]+),\s+([A-Z][a-z\.\-]+(?:\s+[A-Z][a-z\.\-]+)*)$")

    for citation in citations:
        author = citation["author"].strip()
        if not author:
            continue
            
        match = pattern.match(author)
        if match:
            last, first = match.groups()
            # Flip it
            citation["author"] = f"{first} {last}"
            
    return citations


def collapse_author_only(citations: List[Citation]) -> List[Citation]:
    """
    Merge entries with the same author where one has no title.
    
    If we have {"author": "Plato", "title": ""} and {"author": "Plato", "title": "Republic"},
    we generally KEEP "Republic" separate.
    
    BUT if we have multiple {"author": "Plato", "title": ""}, they merge.
    
    This function specifically merges all title-less entries for an author into one.
    """
    seen_authors: Dict[str, Citation] = {}
    result: List[Citation] = []
    
    # First pass: collect all title-less citations by author
    # We need to be careful: we can't just merge them all immediately if we want to preserve order?
    # Actually order doesn't matter much for the graph.
    
    # Let's separate titled and untitled
    untitled_map: Dict[str, Citation] = {}
    titled_list: List[Citation] = []
    
    for citation in citations:
        title = citation["title"].strip()
        author = citation["author"].strip()
        author_key = author.casefold()
        
        if not title:
            if author_key in untitled_map:
                merge_citations(untitled_map[author_key], citation)
            else:
                # Ensure canonical author name is set nicely if possible
                citation["canonical_author"] = author.title() 
                untitled_map[author_key] = citation
        else:
            titled_list.append(citation)
            
    # Combine results
    result = titled_list + list(untitled_map.values())
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
    merged: Dict[Tuple[str, str], Citation] = {}
    
    for citation in citations:
        author = citation.get("author") or ""
        title = citation.get("title") or ""
        
        canon_author = normalize_text(author)
        canon_title = normalize_title(title)
        
        # If title is empty, key is just author (but we handled this in collapse_author_only mostly)
        # Actually collapse_author_only handles empty titles. 
        # Here we handle "Republic" vs "The Republic".
        
        if not canon_title:
             # Should have been handled or it's just author
             key = (canon_author, "")
        else:
             key = (canon_author, canon_title)
             
        if key in merged:
            merge_citations(merged[key], citation)
            # Update title to the longer/more complete one? 
            # Or keep the one we saw first?
            # Let's keep the longer one as it might be more descriptive
            existing_title = merged[key]["title"]
            if len(title) > len(existing_title):
                merged[key]["title"] = title
        else:
            merged[key] = citation
            
    return list(merged.values())


def drop_self_references(
    citations: List[Citation],
    source_title: Optional[str],
    source_authors: Optional[Sequence[str]],
) -> List[Citation]:
    """
    Remove citations that point back to the same book/author.
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
        
        # If same author AND (same title OR no title), drop it.
        # "No title" means it's just a reference to the author, which is self-ref.
        if is_same_author and (is_same_title or not c_title.strip()):
            continue
            
        result.append(citation)
    return result


HEURISTICS: List[Heuristic] = [
    filter_noise,
    normalize_author_names,
    normalize_essay_titles,
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


def preprocess(
    path: Path,
    source_title: Optional[str] = None,
    source_authors: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    citations = load_citations(path)
    # First exact dedup to merge identicals immediately
    citations = deduplicate_exact(citations)
    # Then apply fuzzy heuristics
    citations = apply_heuristics(citations, source_title, source_authors)
    
    # Sort by count descending
    citations.sort(key=lambda x: x["count"], reverse=True)
    
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
