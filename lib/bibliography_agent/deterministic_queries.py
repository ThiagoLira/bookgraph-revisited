"""
Deterministic query generation for citation resolution.

Replaces LLM-based query generation with rule-based expansion.
Produces List[SearchQuery] from citation dicts without any LLM or DB calls.
"""

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from lib.bibliography_agent.events import SearchQuery


# Articles to strip from the beginning of titles (case-insensitive)
LEADING_ARTICLES = [
    # English
    "the ", "a ", "an ",
    # French
    "le ", "la ", "les ", "l'", "un ", "une ",
    # German
    "der ", "die ", "das ", "ein ", "eine ",
    # Spanish
    "el ", "los ", "las ",
    # Italian
    "il ", "lo ", "la ", "i ", "gli ", "le ",
    # Portuguese
    "o ", "os ", "as ",
]

# Subtitle separators (split title on first occurrence)
SUBTITLE_SEPARATORS = [": ", " — ", " – ", " - "]

# Name particles to strip
NAME_PARTICLES = ["von ", "de ", "la ", "van ", "du ", "di ", "del ", "della ", "al-", "ibn "]


def _strip_subtitle(title: str) -> Optional[str]:
    """Remove subtitle from title. Returns None if no subtitle found."""
    for sep in SUBTITLE_SEPARATORS:
        idx = title.find(sep)
        if idx > 0:
            return title[:idx].strip()
    return None


def _strip_leading_article(title: str) -> Optional[str]:
    """Remove leading article from title. Returns None if no article found."""
    lower = title.lower()
    for article in LEADING_ARTICLES:
        if lower.startswith(article):
            stripped = title[len(article):].strip()
            if stripped:
                return stripped
    return None


def _extract_last_name(author: str) -> Optional[str]:
    """Extract last name from author. Returns None if single-word name."""
    parts = author.strip().split()
    if len(parts) > 1:
        return parts[-1]
    return None


def _swap_comma_format(author: str) -> Optional[str]:
    """Convert 'Last, First' to 'First Last'. Returns None if no comma."""
    if ", " in author:
        parts = author.split(", ", 1)
        if len(parts) == 2 and parts[0].strip() and parts[1].strip():
            return f"{parts[1].strip()} {parts[0].strip()}"
    return None


def _strip_particles(author: str) -> Optional[str]:
    """Remove name particles (von, de, etc.). Returns None if no particle found."""
    lower = author.lower()
    for particle in NAME_PARTICLES:
        # Check if particle appears as a word boundary in the name
        idx = lower.find(f" {particle}")
        if idx >= 0:
            # Remove the particle
            before = author[:idx].strip()
            after = author[idx + len(particle) + 1:].strip()
            result = f"{before} {after}".strip() if before else after
            if result and result.lower() != author.lower():
                return result
    # Also check if name starts with a particle
    for particle in NAME_PARTICLES:
        if lower.startswith(particle):
            result = author[len(particle):].strip()
            if result:
                return result
    return None


def _get_alias_variants(
    author: str, author_aliases: Dict[str, str]
) -> List[str]:
    """Get all alias variants for an author from the alias mapping.

    Args:
        author: The author name to look up.
        author_aliases: Mapping of lowercase variant -> canonical name.

    Returns:
        List of variant names (excluding the input author itself).
    """
    variants = []
    if not author or not author_aliases:
        return variants

    # Check if this author has a canonical form
    canonical = author_aliases.get(author.lower())
    if canonical and canonical.lower() != author.lower():
        variants.append(canonical)

    # If this IS the canonical (or we found the canonical), get all variants
    lookup_canonical = canonical or author
    for variant_key, canon_val in author_aliases.items():
        if canon_val.lower() == lookup_canonical.lower() and variant_key != author.lower():
            # Reconstruct the variant with proper casing (title case)
            variants.append(variant_key.title())

    # Deduplicate while preserving order
    seen = {author.lower()}
    unique = []
    for v in variants:
        if v.lower() not in seen:
            seen.add(v.lower())
            unique.append(v)

    return unique


def generate_queries_deterministic(
    citation: Dict[str, Any],
    author_aliases: Optional[Dict[str, str]] = None,
) -> List[SearchQuery]:
    """Generate search queries deterministically from a citation dict.

    Args:
        citation: Dict with keys like 'title', 'author', 'canonical_author', etc.
        author_aliases: Mapping of lowercase variant -> canonical name
            (as built by CitationWorkflow from author_aliases.json).

    Returns:
        Deduplicated list of SearchQuery objects.
    """
    title = (citation.get("title") or "").strip()
    author = (citation.get("author") or "").strip()
    canonical_author = (citation.get("canonical_author") or "").strip()

    if not author_aliases:
        author_aliases = {}

    mode = "book" if title else "author_only"
    queries: List[Tuple[str, str]] = []  # (title, author) pairs

    if mode == "book":
        queries = _generate_book_queries(title, author, canonical_author, author_aliases)
    else:
        queries = _generate_author_queries(author, canonical_author, author_aliases)

    # Deduplicate by (title.lower(), author.lower())
    seen: Set[Tuple[str, str]] = set()
    result: List[SearchQuery] = []
    for t, a in queries:
        key = (t.lower().strip(), a.lower().strip())
        if key not in seen and (key[0] or key[1]):  # at least one must be non-empty
            seen.add(key)
            result.append(SearchQuery(
                title=t.strip() if t.strip() else None,
                author=a.strip() if a.strip() else None,
            ))

    return result


def _generate_book_queries(
    title: str,
    author: str,
    canonical_author: str,
    author_aliases: Dict[str, str],
) -> List[Tuple[str, str]]:
    """Generate query variants for book mode (has title + author)."""
    queries: List[Tuple[str, str]] = []

    # 1. Exact title + exact author
    queries.append((title, author))

    # Compute title variants
    title_no_subtitle = _strip_subtitle(title)
    title_no_article = _strip_leading_article(title)
    title_stripped = title  # start with original

    # 2. Title without subtitle
    if title_no_subtitle:
        queries.append((title_no_subtitle, author))
        title_stripped = title_no_subtitle

    # 3. Title without leading article
    if title_no_article:
        queries.append((title_no_article, author))

    # 4. Both subtitle and article stripped
    if title_no_subtitle and title_no_article:
        combined = _strip_leading_article(title_no_subtitle)
        if combined and combined.lower() != title_no_subtitle.lower():
            queries.append((combined, author))

    # 5. Original title + author last name only
    last_name = _extract_last_name(author) if author else None
    if last_name:
        queries.append((title, last_name))

    # 6. Stripped title + author last name only
    if title_no_subtitle and last_name:
        queries.append((title_no_subtitle, last_name))

    # 7. Alias variants: original title + each variant
    if author:
        for variant in _get_alias_variants(author, author_aliases):
            queries.append((title, variant))

    # 8. Comma-format swap
    if author:
        swapped = _swap_comma_format(author)
        if swapped:
            queries.append((title, swapped))

    # 9. Author without particles
    if author:
        no_particles = _strip_particles(author)
        if no_particles:
            queries.append((title, no_particles))

    # 10. canonical_author if different from author
    if canonical_author and canonical_author.lower() != author.lower():
        queries.append((title, canonical_author))

    return queries


def _generate_author_queries(
    author: str,
    canonical_author: str,
    author_aliases: Dict[str, str],
) -> List[Tuple[str, str]]:
    """Generate query variants for author-only mode (empty title)."""
    queries: List[Tuple[str, str]] = []

    # 1. Original author name
    if author:
        queries.append(("", author))

    # 2. Last name only
    last_name = _extract_last_name(author) if author else None
    if last_name:
        queries.append(("", last_name))

    # 3. Alias variants
    if author:
        for variant in _get_alias_variants(author, author_aliases):
            queries.append(("", variant))

    # 4. Author without particles
    if author:
        no_particles = _strip_particles(author)
        if no_particles:
            queries.append(("", no_particles))

    # 5. Comma-format swap
    if author:
        swapped = _swap_comma_format(author)
        if swapped:
            queries.append(("", swapped))

    # 6. canonical_author if present and different
    if canonical_author and canonical_author.lower() != (author or "").lower():
        queries.append(("", canonical_author))

    return queries
