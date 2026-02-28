"""
Combined citation cleaning: heuristic preprocessing + LLM validation.

Replaces the separate preprocess_citations.py and validate_citations.py stages
with a single unified cleaning pipeline.
"""

from __future__ import annotations

import asyncio
import copy
import json
import logging
import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from openai import AsyncOpenAI

from lib.text_utils import normalize_text, normalize_title, is_similar
from lib.author_aliases import AuthorAliasRegistry
from lib.llm_client import LLMConfig, build_async_openai

logger = logging.getLogger(__name__)

Citation = Dict[str, Any]
Heuristic = Callable[[List[Citation]], List[Citation]]


# --------------------------------------------------------------------------- #
#  FLATTEN RAW EXTRACTION → CITATION LIST
# --------------------------------------------------------------------------- #

def flatten_raw_citations(data: Dict[str, Any]) -> List[Citation]:
    """Extract citation dicts from raw extraction JSON (chunks → flat list)."""
    rows: List[Citation] = []
    for chunk in data.get("chunks", []):
        for citation in chunk.get("citations", []):
            title = (citation.get("title") or "").strip()
            author = (citation.get("author") or "").strip()
            if not author:
                continue
            rows.append({
                "title": title,
                "author": author,
                "note": citation.get("note"),
                "count": 1,
                "contexts": [citation.get("citation_excerpt")] if citation.get("citation_excerpt") else [],
                "commentaries": [citation.get("commentary")] if citation.get("commentary") else [],
            })
    return rows


# --------------------------------------------------------------------------- #
#  HEURISTIC HELPERS
# --------------------------------------------------------------------------- #

def merge_citation_metadata(target: Citation, source: Citation) -> Citation:
    """Merge metadata (count, contexts, commentaries) from source into target."""
    target["count"] = target.get("count", 1) + source.get("count", 1)
    tgt_contexts = target.get("contexts", [])
    src_contexts = source.get("contexts", [])
    target["contexts"] = list(dict.fromkeys(tgt_contexts + src_contexts))
    tgt_comments = target.get("commentaries", [])
    src_comments = source.get("commentaries", [])
    target["commentaries"] = list(dict.fromkeys(tgt_comments + src_comments))
    return target


def deduplicate_exact(citations: List[Citation]) -> List[Citation]:
    """Exact dedup by (title, author) case-insensitive."""
    seen: Dict[tuple, Citation] = {}
    deduped: List[Citation] = []
    for cit in citations:
        key = (cit["title"].casefold(), cit["author"].casefold())
        if key in seen:
            merge_citation_metadata(seen[key], cit)
            continue
        seen[key] = cit
        deduped.append(cit)
    return deduped


# --------------------------------------------------------------------------- #
#  HEURISTIC: FILTER NON-PERSON AUTHORS
# --------------------------------------------------------------------------- #

NON_PERSON_BLOCKLIST = {
    "unknown", "anonymous", "various authors", "various", "editor", "editors",
    "the author", "the editor", "narrator", "compiler",
    "thinkers", "poets", "philosophers", "scholars", "scientists", "writers",
    "critics", "historians", "theologians", "mystics", "commentators",
    "epicureans", "stoics", "pythagorean sect", "greek philosophers",
    "ancient authors", "jewish authors", "christian authors",
    "elders of zion", "church fathers", "scholastics", "pre-socratics",
    "cynics", "skeptics", "peripatetics", "neoplatonists", "atomists",
    "hamlet", "faust", "don quixote", "zarathustra", "meursault",
    "dionysus", "zeus", "athena", "apollo", "prometheus", "hermes",
    "odysseus", "achilles", "oedipus", "antigone", "electra",
    "satan", "god", "christ", "jesus", "allah", "buddha",
    "lord", "the bible", "the quran", "the torah", "the talmud",
    "the koran", "the vedas", "the upanishads",
}

_GROUP_SUFFIXES = re.compile(
    r"^the\s+\w+s$"
    r"|ists$"
    r"|ians$"
    r"|ers$"
    r"|ites$"
    r"|ics$",
    re.IGNORECASE,
)

_ET_AL_RE = re.compile(r"\bet\s+al\.?\s*$", re.IGNORECASE)


def filter_non_person_authors(citations: List[Citation]) -> List[Citation]:
    """Remove citations where the author is not a real named individual."""
    result: List[Citation] = []
    for cit in citations:
        author = (cit.get("author") or "").strip()
        author_lower = author.lower()
        if author_lower in NON_PERSON_BLOCKLIST:
            continue
        if author.isupper() and " " not in author.strip():
            continue
        if len(author) <= 2:
            continue
        if _ET_AL_RE.search(author):
            continue
        has_first_name = len(author.split()) >= 2 and not author_lower.startswith("the ")
        if not has_first_name and _GROUP_SUFFIXES.search(author_lower):
            continue
        result.append(cit)
    return result


# --------------------------------------------------------------------------- #
#  HEURISTIC: NORMALIZE AUTHOR ALIASES
# --------------------------------------------------------------------------- #

def normalize_author_aliases(
    citations: List[Citation],
    registry: AuthorAliasRegistry,
) -> List[Citation]:
    """Normalize known author name variants to canonical forms."""
    if len(registry) == 0:
        return citations
    result: List[Citation] = []
    for cit in citations:
        author = (cit.get("author") or "").strip()
        canonical = registry.canonical(author)
        if canonical and canonical != author:
            cit = {**cit, "author": canonical, "canonical_author": author}
        result.append(cit)
    return result


# --------------------------------------------------------------------------- #
#  HEURISTIC: COLLAPSE AUTHOR-ONLY
# --------------------------------------------------------------------------- #

def collapse_author_only(citations: List[Citation]) -> List[Citation]:
    """Keep only one entry per author when the title is empty/null."""
    seen_authors: Dict[str, Citation] = {}
    result: List[Citation] = []
    for cit in citations:
        title = (cit.get("title") or "").strip()
        author = cit.get("author")
        if not author:
            continue
        if not title:
            key = author.casefold()
            if key in seen_authors:
                merge_citation_metadata(seen_authors[key], cit)
                continue
            seen_authors[key] = cit
            cit = {**cit, "title": "", "canonical_author": author.title()}
        result.append(cit)
    return result


# --------------------------------------------------------------------------- #
#  HEURISTIC: COLLAPSE VARIANT TITLES
# --------------------------------------------------------------------------- #

def collapse_variant_titles(citations: List[Citation]) -> List[Citation]:
    """Deduplicate obvious title variants for the same author."""
    seen: Dict[tuple, Citation] = {}
    result: List[Citation] = []
    for cit in citations:
        author = cit.get("author") or ""
        title = cit.get("title") or ""
        canon_author = normalize_text(author)
        canon_title = normalize_title(title)
        key = (canon_author, canon_title) if canon_title else (canon_author, title.casefold())
        if key in seen:
            merge_citation_metadata(seen[key], cit)
            continue
        seen[key] = cit
        result.append(cit)
    return result


# --------------------------------------------------------------------------- #
#  HEURISTIC: MERGE SIMILAR CITATIONS (FUZZY)
# --------------------------------------------------------------------------- #

def merge_similar_citations(citations: List[Citation]) -> List[Citation]:
    """Aggressively merge citations with very similar titles and authors."""
    def is_similar_title(a: str, b: str) -> bool:
        return is_similar(normalize_title(a), normalize_title(b), threshold=0.85)

    def is_similar_author(a: str, b: str) -> bool:
        return is_similar(normalize_text(a), normalize_text(b), threshold=0.85)

    merged: List[Citation] = []
    sorted_citations = sorted(
        citations,
        key=lambda c: len(c.get("title") or "") + len(c.get("author") or ""),
        reverse=True,
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

            if not is_similar_author(ref_author, tgt_author):
                a1 = normalize_text(ref_author)
                a2 = normalize_text(tgt_author)
                if not (a1 in a2 or a2 in a1):
                    continue

            same_title = False
            if not ref_title and not tgt_title:
                same_title = True
            elif ref_title and tgt_title:
                same_title = is_similar_title(ref_title, tgt_title)

            if same_title:
                merge_citation_metadata(candidate, target)
                used_indices.add(j)

        merged.append(candidate)
    return merged


# --------------------------------------------------------------------------- #
#  HEURISTIC: DROP SELF-REFERENCES
# --------------------------------------------------------------------------- #

def drop_self_references(
    citations: List[Citation],
    source_title: Optional[str],
    source_authors: Optional[Sequence[str]],
) -> List[Citation]:
    """Remove citations that point back to the same book/author."""
    if not source_title and not source_authors:
        return citations
    norm_title = normalize_title(source_title or "")
    norm_authors = {normalize_text(a) for a in (source_authors or []) if a}
    result: List[Citation] = []
    for cit in citations:
        c_title = cit.get("title") or ""
        c_author = cit.get("author") or ""
        canon_title = normalize_title(c_title)
        canon_author = normalize_text(c_author)
        is_same_author = norm_authors and canon_author in norm_authors
        is_same_title = norm_title and canon_title and canon_title == norm_title
        if is_same_author and (is_same_title or not c_title.strip()):
            continue
        result.append(cit)
    return result


# --------------------------------------------------------------------------- #
#  LLM VALIDATION
# --------------------------------------------------------------------------- #

BATCH_SIZE = 30

VALIDATION_SYSTEM_PROMPT = (
    "You are an expert bibliographer and literary scholar. "
    "Your job is to validate and clean a list of book/author citations "
    "extracted from a source text. You will receive a batch of citations "
    "and must return a JSON array with one decision per citation."
)

VALIDATION_USER_TEMPLATE = """You are validating citations extracted from "{source_title}" by {source_authors}.

For each citation below, decide:
- "keep": Citation is valid — a real person authored a real (or plausible) book.
- "fix": Citation has errors — provide corrected author/title. Common fixes:
  - Normalize author name to canonical form (e.g. "Dostoevski" → "Fyodor Dostoevsky")
  - Correct misattributions (wrong author for a known book)
  - Fix obvious title typos
- "remove": Citation is invalid — author is not a real person, is a fictional/mythological
  character, a group noun ("the Stoics"), or a generic term ("poets", "thinkers").

Return ONLY a JSON array with this shape:
[
  {{
    "index": 0,
    "status": "keep" | "fix" | "remove",
    "reason": "brief explanation",
    "fixed_author": "Corrected Name",   // only if status="fix"
    "fixed_title": "Corrected Title"    // only if status="fix" and title needs correction
  }},
  ...
]

IMPORTANT:
- Be conservative: only "remove" entries you are VERY confident are not real authors.
- Only "fix" when you are certain of the correct author/title.
- When normalizing names, use the most widely recognized English form.
- One entry per citation, in the same order as the input.

=== CITATIONS ===
{citations_json}
=== END CITATIONS ===
"""


def _format_citations_for_prompt(citations: List[Dict[str, Any]]) -> str:
    compact = []
    for i, cit in enumerate(citations):
        compact.append({
            "index": i,
            "author": cit.get("author", ""),
            "title": cit.get("title", ""),
            "count": cit.get("count", 1),
        })
    return json.dumps(compact, indent=2, ensure_ascii=False)


def _parse_validation_response(text: str) -> List[Dict[str, Any]]:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1]
        if text.endswith("```"):
            text = text.rsplit("```", 1)[0]
        text = text.strip()
    results = json.loads(text)
    if not isinstance(results, list):
        raise ValueError(f"Expected a JSON array, got {type(results)}")
    return results


async def _validate_batch(
    client: AsyncOpenAI,
    model: str,
    citations: List[Dict[str, Any]],
    source_title: str,
    source_authors: str,
    max_completion_tokens: int = 4096,
) -> List[Dict[str, Any]]:
    citations_json = _format_citations_for_prompt(citations)
    user_prompt = VALIDATION_USER_TEMPLATE.format(
        source_title=source_title,
        source_authors=source_authors,
        citations_json=citations_json,
    )
    messages = [
        {"role": "system", "content": VALIDATION_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    max_retries = 2
    for attempt in range(max_retries + 1):
        try:
            response = await client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=max_completion_tokens,
                temperature=0.0,
                timeout=120.0,
            )
            content = ""
            if response.choices:
                content = (response.choices[0].message.content or "").strip()
            if not content:
                logger.warning(f"[validate] Empty response (attempt {attempt + 1})")
                continue
            return _parse_validation_response(content)
        except json.JSONDecodeError as e:
            logger.warning(f"[validate] JSON parse error (attempt {attempt + 1}): {e}")
        except Exception as e:
            logger.warning(f"[validate] API error (attempt {attempt + 1}): {e}")

    logger.error("[validate] All retries failed, keeping batch unchanged")
    return [{"index": i, "status": "keep", "reason": "validation failed"} for i in range(len(citations))]


def _apply_validation_results(
    citations: List[Dict[str, Any]],
    results: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    stats = {"kept": 0, "fixed": 0, "removed": 0}
    result_map: Dict[int, Dict[str, Any]] = {}
    for r in results:
        idx = r.get("index")
        if idx is not None:
            result_map[int(idx)] = r

    validated = []
    for i, cit in enumerate(citations):
        decision = result_map.get(i)
        if not decision:
            validated.append(cit)
            stats["kept"] += 1
            continue

        status = decision.get("status", "keep")
        reason = decision.get("reason", "")

        if status == "remove":
            stats["removed"] += 1
            logger.info(f"[validate] REMOVED: '{cit.get('author')}' - '{cit.get('title', '')}' ({reason})")
            continue

        if status == "fix":
            stats["fixed"] += 1
            fixed = copy.deepcopy(cit)
            old_author = fixed.get("author", "")
            old_title = fixed.get("title", "")
            if decision.get("fixed_author"):
                fixed["author"] = decision["fixed_author"]
                if decision["fixed_author"] != old_author:
                    logger.info(f"[validate] FIX author: '{old_author}' → '{decision['fixed_author']}' ({reason})")
            if decision.get("fixed_title"):
                fixed["title"] = decision["fixed_title"]
                if decision["fixed_title"] != old_title:
                    logger.info(f"[validate] FIX title: '{old_title}' → '{decision['fixed_title']}' ({reason})")
            validated.append(fixed)
            continue

        stats["kept"] += 1
        validated.append(cit)

    return validated, stats


async def run_llm_validation(
    citations: List[Dict[str, Any]],
    source_title: str,
    source_authors: Sequence[str],
    llm_config: LLMConfig,
    concurrency: int = 5,
    batch_size: int = BATCH_SIZE,
) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    """Run LLM validation on all citations in batches."""
    if not citations:
        return [], {"kept": 0, "fixed": 0, "removed": 0}

    authors_str = ", ".join(source_authors) if source_authors else "Unknown"
    batches = [citations[i:i + batch_size] for i in range(0, len(citations), batch_size)]
    logger.info(f"[validate] Validating {len(citations)} citations in {len(batches)} batches (model={llm_config.model})")
    print(f"[validate] Validating {len(citations)} citations in {len(batches)} batches...")

    semaphore = asyncio.Semaphore(concurrency)
    all_validated: List[Dict[str, Any]] = []
    total_stats = {"kept": 0, "fixed": 0, "removed": 0}

    client = build_async_openai(llm_config)
    async with client:
        async def process_batch(batch_citations):
            async with semaphore:
                results = await _validate_batch(
                    client, llm_config.model, batch_citations,
                    source_title, authors_str,
                )
                return _apply_validation_results(batch_citations, results)

        tasks = [process_batch(batch) for batch in batches]
        for coro in asyncio.as_completed(tasks):
            validated, stats = await coro
            all_validated.extend(validated)
            for k in total_stats:
                total_stats[k] += stats.get(k, 0)

    logger.info(f"[validate] Done: kept={total_stats['kept']}, fixed={total_stats['fixed']}, removed={total_stats['removed']}")
    print(f"[validate] Results: kept={total_stats['kept']}, fixed={total_stats['fixed']}, removed={total_stats['removed']}")
    return all_validated, total_stats


# --------------------------------------------------------------------------- #
#  UNIFIED CLEANING PIPELINE
# --------------------------------------------------------------------------- #

def apply_heuristics(
    citations: List[Citation],
    source_title: Optional[str],
    source_authors: Optional[Sequence[str]],
    alias_registry: Optional[AuthorAliasRegistry] = None,
) -> List[Citation]:
    """Apply all heuristic cleaning steps in order."""
    if alias_registry is None:
        alias_registry = AuthorAliasRegistry()

    result = filter_non_person_authors(citations)
    result = normalize_author_aliases(result, alias_registry)
    result = collapse_author_only(result)
    result = collapse_variant_titles(result)
    result = merge_similar_citations(result)
    result = drop_self_references(result, source_title, source_authors)
    return result


async def clean_citations(
    raw_data: Dict[str, Any],
    source_name: str,
    source_title: Optional[str] = None,
    source_authors: Optional[Sequence[str]] = None,
    alias_registry: Optional[AuthorAliasRegistry] = None,
    llm_config: Optional[LLMConfig] = None,
    validate_concurrency: int = 5,
) -> Dict[str, Any]:
    """Full cleaning pipeline: flatten → dedup → heuristics → LLM validation.

    If llm_config is None, LLM validation is skipped (heuristics only).
    Returns a dict with 'source', 'total', 'citations', and optionally 'validation_stats'.
    """
    # 1. Flatten raw chunks to citation list
    citations = flatten_raw_citations(raw_data)

    # 2. Exact dedup
    citations = deduplicate_exact(citations)

    # 3. Heuristic chain
    citations = apply_heuristics(citations, source_title, source_authors, alias_registry)

    heuristic_count = len(citations)

    # 4. LLM validation (optional)
    validation_stats = None
    if llm_config and citations:
        citations, validation_stats = await run_llm_validation(
            citations,
            source_title or "",
            source_authors or [],
            llm_config,
            concurrency=validate_concurrency,
        )

    result = {
        "source": source_name,
        "total": len(citations),
        "citations": citations,
    }
    if validation_stats:
        result["validation_stats"] = validation_stats

    return result
