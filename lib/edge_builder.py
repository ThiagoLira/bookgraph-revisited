"""Build citation result dicts with edge/metadata structure."""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def build_result_dict(
    citation: dict,
    match_type: str,
    metadata: Dict[str, Any],
    wiki_match: Optional[dict] = None,
) -> dict:
    """Build a fully-structured result dict from workflow/fallback output.

    Extracts target_book_id, target_author_ids from metadata and assembles
    the standard {raw, goodreads_match, wikipedia_match, edge} structure.
    """
    target_book_id = metadata.get("book_id")

    target_author_ids: List[str] = []
    if metadata.get("author_id"):
        target_author_ids.append(str(metadata["author_id"]))
    elif metadata.get("author_ids"):
        target_author_ids = [str(a) for a in metadata["author_ids"]]

    return {
        "raw": citation,
        "goodreads_match": metadata if match_type == "book" else None,
        "wikipedia_match": wiki_match,
        "edge": {
            "target_type": match_type,
            "target_book_id": target_book_id,
            "target_author_ids": target_author_ids,
            "target_person": wiki_match,
        },
    }
