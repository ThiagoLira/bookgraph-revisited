#!/usr/bin/env python3
"""
LLM-based citation validation step.

Sits between preprocessing and the workflow. Sends citations to the LLM in
batches for validation: filters non-persons, corrects misattributions,
normalizes author names, and flags low-confidence entries.
"""

from __future__ import annotations

import asyncio
import copy
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

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
    """Format citations as a compact JSON list for the prompt."""
    compact = []
    for i, cit in enumerate(citations):
        compact.append({
            "index": i,
            "author": cit.get("author", ""),
            "title": cit.get("title", ""),
            "count": cit.get("count", 1),
        })
    return json.dumps(compact, indent=2, ensure_ascii=False)


def _parse_validation_response(text: str, batch_size: int) -> List[Dict[str, Any]]:
    """Parse the LLM validation response, handling common formatting issues."""
    text = text.strip()
    # Strip markdown code fences
    if text.startswith("```"):
        text = text.split("\n", 1)[1]
        if text.endswith("```"):
            text = text.rsplit("```", 1)[0]
        text = text.strip()

    results = json.loads(text)
    if not isinstance(results, list):
        raise ValueError(f"Expected a JSON array, got {type(results)}")
    return results


async def validate_batch(
    client: AsyncOpenAI,
    model: str,
    citations: List[Dict[str, Any]],
    source_title: str,
    source_authors: str,
    max_completion_tokens: int = 4096,
) -> List[Dict[str, Any]]:
    """Validate a single batch of citations via the LLM.

    Returns a list of decision dicts with keys: index, status, reason,
    and optionally fixed_author/fixed_title.
    """
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

            results = _parse_validation_response(content, len(citations))
            return results

        except json.JSONDecodeError as e:
            logger.warning(f"[validate] JSON parse error (attempt {attempt + 1}): {e}")
        except Exception as e:
            logger.warning(f"[validate] API error (attempt {attempt + 1}): {e}")

    # If all retries fail, default to keeping everything
    logger.error("[validate] All retries failed, keeping batch unchanged")
    return [{"index": i, "status": "keep", "reason": "validation failed"} for i in range(len(citations))]


def apply_validation_results(
    citations: List[Dict[str, Any]],
    results: List[Dict[str, Any]],
) -> tuple[List[Dict[str, Any]], Dict[str, int]]:
    """Apply validation decisions to citations.

    Returns (validated_citations, stats_dict).
    """
    stats = {"kept": 0, "fixed": 0, "removed": 0, "errors": 0}

    # Build index map for results
    result_map: Dict[int, Dict[str, Any]] = {}
    for r in results:
        idx = r.get("index")
        if idx is not None:
            result_map[int(idx)] = r

    validated = []
    for i, cit in enumerate(citations):
        decision = result_map.get(i)
        if not decision:
            # No decision for this citation — keep it
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

        # status == "keep" or unknown
        stats["kept"] += 1
        validated.append(cit)

    return validated, stats


async def validate_citations(
    citations: List[Dict[str, Any]],
    source_title: str,
    source_authors: Sequence[str],
    *,
    base_url: str,
    api_key: str,
    model: str,
    concurrency: int = 5,
    batch_size: int = BATCH_SIZE,
) -> tuple[List[Dict[str, Any]], Dict[str, int]]:
    """Run LLM validation on all citations in batches.

    Returns (validated_citations, aggregate_stats).
    """
    if not citations:
        return [], {"kept": 0, "fixed": 0, "removed": 0, "errors": 0}

    authors_str = ", ".join(source_authors) if source_authors else "Unknown"

    # Split into batches
    batches = [citations[i:i + batch_size] for i in range(0, len(citations), batch_size)]
    logger.info(f"[validate] Validating {len(citations)} citations in {len(batches)} batches (model={model})")
    print(f"[validate] Validating {len(citations)} citations in {len(batches)} batches...")

    semaphore = asyncio.Semaphore(concurrency)
    all_validated: List[Dict[str, Any]] = []
    total_stats = {"kept": 0, "fixed": 0, "removed": 0, "errors": 0}

    async with AsyncOpenAI(api_key=api_key, base_url=base_url) as client:

        async def process_batch(batch_citations: List[Dict[str, Any]]) -> tuple[List[Dict[str, Any]], Dict[str, int]]:
            async with semaphore:
                results = await validate_batch(
                    client, model, batch_citations,
                    source_title, authors_str,
                )
                return apply_validation_results(batch_citations, results)

        tasks = [process_batch(batch) for batch in batches]

        for coro in asyncio.as_completed(tasks):
            validated, stats = await coro
            all_validated.extend(validated)
            for k in total_stats:
                total_stats[k] += stats.get(k, 0)

    logger.info(f"[validate] Done: kept={total_stats['kept']}, fixed={total_stats['fixed']}, removed={total_stats['removed']}")
    print(f"[validate] Results: kept={total_stats['kept']}, fixed={total_stats['fixed']}, removed={total_stats['removed']}")

    return all_validated, total_stats
