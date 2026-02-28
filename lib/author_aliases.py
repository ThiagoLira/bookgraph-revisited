"""
Single source of truth for author alias management.

Loads author_aliases.json once and provides canonical name lookup,
variant expansion, and normalization for all pipeline consumers.
"""

import json
from pathlib import Path
from typing import Dict, List, Optional


class AuthorAliasRegistry:
    """Manages canonical ↔ variant author name mappings."""

    def __init__(self, aliases_path: Optional[Path] = None):
        self._variant_to_canonical: Dict[str, str] = {}  # lower -> canonical
        self._canonical_to_variants: Dict[str, List[str]] = {}  # canonical -> [variants]

        if aliases_path is None:
            aliases_path = Path(__file__).resolve().parents[1] / "datasets" / "author_aliases.json"

        if aliases_path.exists():
            self._load(aliases_path)

    def _load(self, path: Path):
        try:
            raw = json.loads(path.read_text())
        except Exception:
            return

        for canonical, variants in raw.items():
            # Self-mapping: canonical -> canonical
            self._variant_to_canonical[canonical.lower()] = canonical
            self._canonical_to_variants[canonical] = list(variants)
            for v in variants:
                self._variant_to_canonical[v.lower()] = canonical

    def canonical(self, name: str) -> Optional[str]:
        """Get canonical name for a variant, or None if not in registry."""
        return self._variant_to_canonical.get(name.lower())

    def variants(self, name: str) -> List[str]:
        """Get all known variants for a name (looks up canonical first)."""
        canon = self.canonical(name)
        if canon:
            return list(self._canonical_to_variants.get(canon, []))
        return []

    def normalize(self, name: str) -> str:
        """Return canonical form if known, otherwise return original."""
        return self._variant_to_canonical.get(name.lower(), name)

    def expand_for_search(self, name: str) -> List[str]:
        """Return all name forms for search: [original, canonical, ...variants].

        Deduplicated, preserving order. Never returns empty for non-empty input.
        """
        if not name:
            return []

        result = [name]
        seen = {name.lower()}

        canon = self.canonical(name)
        if canon and canon.lower() not in seen:
            result.append(canon)
            seen.add(canon.lower())

        # Get all variants of the canonical form
        lookup = canon or name
        for variant_key, canon_val in self._variant_to_canonical.items():
            if canon_val.lower() == lookup.lower() and variant_key not in seen:
                result.append(variant_key.title())
                seen.add(variant_key)

        return result

    @property
    def reverse_map(self) -> Dict[str, str]:
        """Legacy compatibility: return variant.lower() -> canonical mapping."""
        return dict(self._variant_to_canonical)

    def __len__(self) -> int:
        return len(self._variant_to_canonical)

    def __contains__(self, name: str) -> bool:
        return name.lower() in self._variant_to_canonical
