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
                    "count": 1,
                    "contexts": [citation.get("citation_excerpt")] if citation.get("citation_excerpt") else [],
                    "commentaries": [citation.get("commentary")] if citation.get("commentary") else [],
                }
            )
    return rows


def merge_citation_metadata(target: Citation, source: Citation) -> Citation:
    """Merge metadata (count, contexts, commentaries) from source into target."""
    target["count"] = target.get("count", 1) + source.get("count", 1)
    
    # Merge contexts unique-ly
    tgt_contexts = target.get("contexts", [])
    src_contexts = source.get("contexts", [])
    target["contexts"] = list(dict.fromkeys(tgt_contexts + src_contexts)) # Deduplicate preserving order

    # Merge commentaries unique-ly
    tgt_comments = target.get("commentaries", [])
    src_comments = source.get("commentaries", [])
    target["commentaries"] = list(dict.fromkeys(tgt_comments + src_comments))

    return target


def deduplicate_exact(citations: Iterable[Citation]) -> List[Citation]:
    seen: Dict[tuple, Citation] = {}
    deduped: List[Citation] = []
    
    for citation in citations:
        key = (citation["title"].casefold(), citation["author"].casefold())
        if key in seen:
            merge_citation_metadata(seen[key], citation)
            continue
        
        seen[key] = citation
        deduped.append(citation)
    return deduped


def placeholder_heuristic(citations: List[Citation]) -> List[Citation]:
    """Placeholder for future merging heuristics."""
    return citations


def collapse_author_only(citations: List[Citation]) -> List[Citation]:
    """
    Keep only one entry per author when the title is empty/null.
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
                merge_citation_metadata(seen_authors[key], citation)
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
    seen: Dict[tuple, Citation] = {}
    result: List[Citation] = []
    
    for citation in citations:
        author = citation.get("author") or ""
        title = citation.get("title") or ""
        canon_author = normalize_text(author)
        canon_title = normalize_title(title)
        
        key = (canon_author, canon_title) if canon_title else (canon_author, title.casefold())
        
        if key in seen:
            merge_citation_metadata(seen[key], citation)
            continue
            
        seen[key] = citation
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


def merge_similar_citations(citations: List[Citation]) -> List[Citation]:
    """
    Aggressively merge citations that have very similar titles and authors.
    Uses difflib.SequenceMatcher.
    """
    from difflib import SequenceMatcher

    def is_similar(a: str, b: str, threshold: float = 0.9) -> bool:
        if not a and not b: return True
        if not a or not b: return False
        return SequenceMatcher(None, a, b).ratio() > threshold

    def is_similar_title(a: str, b: str) -> bool:
        # Lower threshold for titles to catch "The X" vs "X" or typos
        return is_similar(normalize_title(a), normalize_title(b), threshold=0.85)

    def is_similar_author(a: str, b: str) -> bool:
        return is_similar(normalize_text(a), normalize_text(b), threshold=0.85)

    merged: List[Citation] = []
    # We'll use a simple greedy clustering
    sorted_citations = sorted(
        citations, 
        key=lambda c: len(c.get("title") or "") + len(c.get("author") or ""), 
        reverse=True
    )

    used_indices = set()

    for i, candidate in enumerate(sorted_citations):
        if i in used_indices:
            continue
        
        cluster = [candidate]
        used_indices.add(i)

        ref_title = candidate.get("title") or ""
        ref_author = candidate.get("author") or ""

        for j in range(i + 1, len(sorted_citations)):
            if j in used_indices:
                continue
            
            target = sorted_citations[j]
            tgt_title = target.get("title") or ""
            tgt_author = target.get("author") or ""

            # Check if Author matches
            if not is_similar_author(ref_author, tgt_author):
                a1 = normalize_text(ref_author)
                a2 = normalize_text(tgt_author)
                if not (a1 in a2 or a2 in a1): 
                    continue

            # Check if Title matches
            same_title = False
            if not ref_title and not tgt_title:
                same_title = True
            elif ref_title and tgt_title:
                same_title = is_similar_title(ref_title, tgt_title)
            
            if same_title:
                # Merge target into candidate
                merge_citation_metadata(candidate, target)
                used_indices.add(j)

        merged.append(candidate)

    return merged


# Known non-person authors to remove (lowercased)
NON_PERSON_BLOCKLIST = {
    # Generic terms
    "unknown", "anonymous", "various authors", "various", "editor", "editors",
    "the author", "the editor", "narrator", "compiler",
    # Group nouns
    "thinkers", "poets", "philosophers", "scholars", "scientists", "writers",
    "critics", "historians", "theologians", "mystics", "commentators",
    "epicureans", "stoics", "pythagorean sect", "greek philosophers",
    "ancient authors", "jewish authors", "christian authors",
    "elders of zion", "church fathers", "scholastics", "pre-socratics",
    "cynics", "skeptics", "peripatetics", "neoplatonists", "atomists",
    # Fictional / mythological characters
    "hamlet", "faust", "don quixote", "zarathustra", "meursault",
    "dionysus", "zeus", "athena", "apollo", "prometheus", "hermes",
    "odysseus", "achilles", "oedipus", "antigone", "electra",
    "satan", "god", "christ", "jesus", "allah", "buddha",
    # Non-person references
    "lord", "the bible", "the quran", "the torah", "the talmud",
    "the koran", "the vedas", "the upanishads",
}

# Patterns that indicate a group noun rather than a person
_GROUP_SUFFIXES = re.compile(
    r"^the\s+\w+s$"           # "the Stoics", "the Greeks"
    r"|ists$"                  # "Marxists", "Platonists" (no first name)
    r"|ians$"                  # "Cartesians", "Freudians" (no first name)
    r"|ers$"                   # "thinkers", "philosophers" (no first name)
    r"|ites$"                  # "Jacobites", "Luddites" (no first name)
    r"|ics$",                  # "Academics", "Skeptics" (no first name)
    re.IGNORECASE,
)

# "et al." pattern — indicates a group reference, not a single person
_ET_AL_RE = re.compile(r"\bet\s+al\.?\s*$", re.IGNORECASE)


def _load_author_aliases_for_normalization() -> Dict[str, str]:
    """Load author aliases for normalization (variant -> canonical)."""
    aliases_path = Path(__file__).resolve().parents[1] / "datasets" / "author_aliases.json"
    mapping: Dict[str, str] = {}
    if aliases_path.exists():
        try:
            raw = json.loads(aliases_path.read_text())
            for canonical, variants in raw.items():
                for v in variants:
                    mapping[v.lower()] = canonical
        except Exception:
            pass
    return mapping


# Load once at module level
_AUTHOR_ALIAS_NORMALIZATION = _load_author_aliases_for_normalization()


def filter_non_person_authors(citations: List[Citation]) -> List[Citation]:
    """Remove citations where the author is not a real named individual."""
    result: List[Citation] = []
    for cit in citations:
        author = (cit.get("author") or "").strip()
        author_lower = author.lower()

        # Blocklist check
        if author_lower in NON_PERSON_BLOCKLIST:
            continue

        # All-caps single word (e.g. "UNKNOWN", "LORD")
        if author.isupper() and " " not in author.strip():
            continue

        # Single character or very short (likely noise)
        if len(author) <= 2:
            continue

        # "et al." references (group citations)
        if _ET_AL_RE.search(author):
            continue

        # Group noun patterns — only apply when there's no first name
        # (i.e. single word or "the X" pattern)
        has_first_name = len(author.split()) >= 2 and not author_lower.startswith("the ")
        if not has_first_name and _GROUP_SUFFIXES.search(author_lower):
            continue

        result.append(cit)
    return result


def normalize_author_aliases(citations: List[Citation]) -> List[Citation]:
    """Normalize known author name variants to canonical forms.

    Uses author_aliases.json to replace common variants like
    "Dostoevski" -> "Fyodor Dostoevsky", "Nietzche" -> "Friedrich Nietzsche".
    This reduces work for the LLM validation stage.
    """
    if not _AUTHOR_ALIAS_NORMALIZATION:
        return citations

    result: List[Citation] = []
    for cit in citations:
        author = (cit.get("author") or "").strip()
        canonical = _AUTHOR_ALIAS_NORMALIZATION.get(author.lower())
        if canonical and canonical != author:
            cit = {**cit, "author": canonical, "canonical_author": author}
        result.append(cit)
    return result


HEURISTICS: List[Heuristic] = [
    filter_non_person_authors,
    normalize_author_aliases,
    collapse_author_only,
    collapse_variant_titles,
    merge_similar_citations,
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
                    "count": 1,
                    "contexts": [citation.get("citation_excerpt")] if citation.get("citation_excerpt") else [],
                    "commentaries": [citation.get("commentary")] if citation.get("commentary") else [],
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
