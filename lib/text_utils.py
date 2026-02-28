"""
Shared text normalization and fuzzy matching utilities.

Single source of truth for all text normalization used across the pipeline.
"""

import re
import unicodedata
from difflib import SequenceMatcher
from typing import Optional


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
    "il ", "lo ", "i ", "gli ",
    # Portuguese
    "o ", "os ", "as ",
    # Other
    "de ", "on ",
]

# Subtitle separators (split title on first occurrence)
SUBTITLE_SEPARATORS = [": ", " — ", " – ", " - "]

# Name particles to strip
NAME_PARTICLES = ["von ", "de ", "la ", "van ", "du ", "di ", "del ", "della ", "al-", "ibn "]


def normalize_text(text: str) -> str:
    """Collapse whitespace and casefold. Basic text normalization."""
    return re.sub(r"\s+", " ", text).strip().casefold()


def normalize_author(name: str) -> str:
    """Normalize author name for cache lookup and dedup.

    Strips accents, lowercases, removes periods/commas, and strips common
    prefixes like 'St.' or 'Saint'.
    """
    # Strip accents
    name = unicodedata.normalize("NFD", name)
    name = "".join(c for c in name if unicodedata.category(c) != "Mn")
    # Lowercase, strip periods/commas, normalize whitespace
    name = name.lower().replace(".", "").replace(",", "").strip()
    name = " ".join(name.split())
    # Strip common prefixes
    for prefix in ("st ", "saint "):
        if name.startswith(prefix):
            name = name[len(prefix):]
    return name


def normalize_title(title: str) -> str:
    """Normalize a title for dedup comparison.

    Strips leading articles (multi-language), splits on subtitle separators,
    removes non-alphanumeric characters.
    """
    t = title.strip().casefold()
    # Strip subtitle
    for sep in (":", "-", "_", "(", "["):
        if sep in t:
            t = t.split(sep, 1)[0]
    # Strip leading articles
    for article in LEADING_ARTICLES:
        if t.startswith(article):
            t = t[len(article):]
            break
    # Remove non-alphanumeric
    t = re.sub(r"[^a-z0-9]+", " ", t)
    return t.strip()


def strip_subtitle(title: str) -> Optional[str]:
    """Remove subtitle from title. Returns None if no subtitle found."""
    for sep in SUBTITLE_SEPARATORS:
        idx = title.find(sep)
        if idx > 0:
            return title[:idx].strip()
    return None


def strip_leading_article(title: str) -> Optional[str]:
    """Remove leading article from title. Returns None if no article found."""
    lower = title.lower()
    for article in LEADING_ARTICLES:
        if lower.startswith(article):
            stripped = title[len(article):].strip()
            if stripped:
                return stripped
    return None


def extract_last_name(author: str) -> Optional[str]:
    """Extract last name from author. Returns None if single-word name."""
    parts = author.strip().split()
    if len(parts) > 1:
        return parts[-1]
    return None


def swap_comma_format(author: str) -> Optional[str]:
    """Convert 'Last, First' to 'First Last'. Returns None if no comma."""
    if ", " in author:
        parts = author.split(", ", 1)
        if len(parts) == 2 and parts[0].strip() and parts[1].strip():
            return f"{parts[1].strip()} {parts[0].strip()}"
    return None


def strip_particles(author: str) -> Optional[str]:
    """Remove name particles (von, de, etc.). Returns None if no particle found."""
    lower = author.lower()
    for particle in NAME_PARTICLES:
        idx = lower.find(f" {particle}")
        if idx >= 0:
            before = author[:idx].strip()
            after = author[idx + len(particle) + 1:].strip()
            result = f"{before} {after}".strip() if before else after
            if result and result.lower() != author.lower():
                return result
    for particle in NAME_PARTICLES:
        if lower.startswith(particle):
            result = author[len(particle):].strip()
            if result:
                return result
    return None


def fuzzy_ratio(s1: str, s2: str) -> int:
    """Token-sort fuzzy match ratio (0-100).

    Mimics fuzzywuzzy.token_sort_ratio using difflib.
    Tokenizes, sorts, and compares for order-independent matching.
    """
    if not s1 or not s2:
        return 0
    tokens1 = sorted(re.findall(r"\w+", s1.lower()))
    tokens2 = sorted(re.findall(r"\w+", s2.lower()))
    sorted_s1 = " ".join(tokens1)
    sorted_s2 = " ".join(tokens2)
    return int(SequenceMatcher(None, sorted_s1, sorted_s2).ratio() * 100)


def is_similar(a: str, b: str, threshold: float = 0.9) -> bool:
    """Check if two strings are similar using SequenceMatcher."""
    if not a and not b:
        return True
    if not a or not b:
        return False
    return SequenceMatcher(None, a, b).ratio() > threshold
