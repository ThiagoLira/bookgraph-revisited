"""Per-book author cache for citation resolution."""

import copy
import logging
from typing import Dict, List, Optional

from lib.text_utils import normalize_author, is_similar

logger = logging.getLogger(__name__)


class AuthorCache:
    """Cache resolved author-only citations to skip redundant workflow runs.

    Keys are normalized author names. Also caches bare last-name variants
    for fuzzy matching (e.g. "Plutarch" from "Lucius Plutarch").
    """

    def __init__(self):
        self._cache: Dict[str, dict] = {}

    def add(self, author_name: str, result: dict):
        """Add a resolved result to cache, including bare last-name variant."""
        key = normalize_author(author_name)
        self._cache[key] = result
        parts = key.split()
        if len(parts) > 1:
            self._cache[parts[-1]] = result

    def find(self, author_name: str) -> Optional[dict]:
        """Look up an author, with fuzzy fallback. Returns deep copy or None."""
        key = normalize_author(author_name)
        if key in self._cache:
            return self._cache[key]
        for cached_key, cached_val in self._cache.items():
            if is_similar(key, cached_key, threshold=0.9):
                return cached_val
        return None

    def find_for_author_only(self, citation: dict) -> Optional[dict]:
        """Check if an author-only citation can be resolved from cache.

        Returns a cloned result dict with the current citation's raw data, or None.
        """
        author = citation.get("author")
        title = citation.get("title")
        if not author or title:
            return None

        cached = self.find(author)
        if cached:
            cloned = copy.deepcopy(cached)
            cloned["raw"] = citation
            logger.info(f"[cache] Hit for author-only citation: '{author}'")
            return cloned
        return None

    def seed_from_results(self, results: List[dict]):
        """Seed cache from existing (checkpoint) results."""
        for r in results:
            raw = r.get("raw", {})
            author = raw.get("author")
            if author:
                self.add(author, r)

    def __len__(self) -> int:
        return len(self._cache)
