"""Post-resolution citation deduplication.

Merges citations that resolved to different editions of the same work.
"""

import logging
from collections import defaultdict
from typing import Any, Dict, List, Set

from lib.text_utils import normalize_author, normalize_title

logger = logging.getLogger(__name__)


def _is_real_gr_id(book_id) -> bool:
    """Check if a book ID is a real Goodreads numeric ID (not web_ prefixed)."""
    if book_id is None:
        return False
    return not str(book_id).startswith("web_")


def _merge_into_keeper(keeper_cit: dict, donor_cit: dict):
    """Merge a donor citation's raw data (contexts, commentaries, count) into keeper."""
    kr = keeper_cit.get("raw", {})
    dr = donor_cit.get("raw", {})

    existing = set(kr.get("contexts", []))
    for ctx in dr.get("contexts", []):
        if ctx not in existing:
            kr.setdefault("contexts", []).append(ctx)
            existing.add(ctx)

    existing_comm = set(kr.get("commentaries", []))
    for comm in dr.get("commentaries", []):
        if comm not in existing_comm:
            kr.setdefault("commentaries", []).append(comm)
            existing_comm.add(comm)

    kr["count"] = kr.get("count", 0) + dr.get("count", 0)


def _pick_best_keeper(entries: List[tuple]) -> tuple:
    """Pick the best citation to keep: prefer real GR ID, then most contexts."""
    keeper_idx, keeper_cit = entries[0]
    for idx, cit in entries[1:]:
        kid = keeper_cit.get("edge", {}).get("target_book_id")
        cid = cit.get("edge", {}).get("target_book_id")
        k_real = _is_real_gr_id(kid)
        c_real = _is_real_gr_id(cid)

        if c_real and not k_real:
            keeper_idx, keeper_cit = idx, cit
        elif not (k_real and not c_real):
            if cit.get("raw", {}).get("count", 0) > keeper_cit.get("raw", {}).get("count", 0):
                keeper_idx, keeper_cit = idx, cit
    return keeper_idx, keeper_cit


def dedup_resolved_citations(results: List[dict]) -> List[dict]:
    """Merge citations that resolved to different editions of the same work.

    Pass 1: Groups by work_id (definitive — all editions share the same
    Goodreads work_id).
    Pass 2: Groups remaining citations by (normalized_author, normalized_title)
    to catch duplicates without work_id (e.g. web_ IDs).
    """
    if not results:
        return results

    indices_to_remove: Set[int] = set()
    merge_count = 0

    # --- Pass 1: Group by work_id ---
    work_id_groups: Dict[str, List[tuple]] = defaultdict(list)
    for i, cit in enumerate(results):
        wid = (cit.get("goodreads_match") or {}).get("work_id")
        if wid:
            work_id_groups[str(wid)].append((i, cit))

    for wid, entries in work_id_groups.items():
        if len(entries) < 2:
            continue
        book_ids = {cit.get("edge", {}).get("target_book_id") for _, cit in entries}
        if len(book_ids) < 2:
            continue

        keeper_idx, keeper_cit = _pick_best_keeper(entries)
        for idx, cit in entries:
            if idx == keeper_idx:
                continue
            _merge_into_keeper(keeper_cit, cit)
            indices_to_remove.add(idx)
            merge_count += 1
            dupe_title = cit.get("raw", {}).get("title", "?")
            dupe_id = cit.get("edge", {}).get("target_book_id")
            keeper_id = keeper_cit.get("edge", {}).get("target_book_id")
            logger.info(f"[dedup] Merged '{dupe_title}' (id={dupe_id}) into (id={keeper_id}) by work_id={wid}")

    if merge_count:
        logger.info(f"[dedup] Pass 1 (work_id): merged {merge_count} duplicate citations")
        print(f"[pipeline] Post-resolution dedup pass 1 (work_id): merged {merge_count} duplicates")

    # --- Pass 2: Group by (author, title) ---
    title_merge_count = 0
    groups: Dict[tuple, List[tuple]] = defaultdict(list)
    for i, cit in enumerate(results):
        if i in indices_to_remove:
            continue
        raw = cit.get("raw", {})
        title = raw.get("title", "")
        if not title:
            continue
        author = normalize_author(raw.get("canonical_author", raw.get("author", "?")))
        norm = normalize_title(title)
        groups[(author, norm)].append((i, cit))

    for (author, norm_title), entries in groups.items():
        if len(entries) < 2:
            continue
        book_ids = {cit.get("edge", {}).get("target_book_id") for _, cit in entries}
        if len(book_ids) < 2:
            continue

        keeper_idx, keeper_cit = _pick_best_keeper(entries)
        for idx, cit in entries:
            if idx == keeper_idx:
                continue
            _merge_into_keeper(keeper_cit, cit)
            indices_to_remove.add(idx)
            title_merge_count += 1
            dupe_title = cit.get("raw", {}).get("title", "?")
            dupe_id = cit.get("edge", {}).get("target_book_id")
            keeper_id = keeper_cit.get("edge", {}).get("target_book_id")
            logger.info(f"[dedup] Merged '{dupe_title}' (id={dupe_id}) into (id={keeper_id}) for author '{author}'")

    if title_merge_count:
        logger.info(f"[dedup] Pass 2 (title): merged {title_merge_count} duplicate citations")
        print(f"[pipeline] Post-resolution dedup pass 2 (title): merged {title_merge_count} duplicates")

    total_merged = merge_count + title_merge_count
    if total_merged:
        results = [cit for i, cit in enumerate(results) if i not in indices_to_remove]

    return results
