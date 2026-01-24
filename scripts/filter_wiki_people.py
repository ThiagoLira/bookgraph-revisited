#!/usr/bin/env python3
"""
Stream and filter a Wikipedia XML dump into a JSONL of person pages.

Heuristic:
  - namespace 0 (mainspace), not a redirect
  - categories matching births/deaths/living people
    OR infobox templates containing person/scientist/writer/etc.

Designed to be memory-safe by streaming and batching pages, with optional
multiprocessing to speed up classification.
"""

from __future__ import annotations

import argparse
import bz2
import json
import multiprocessing as mp
import re
from pathlib import Path
from typing import Iterable, List, Optional

import mwxml


CATEGORY_RE = re.compile(r"\[\[Category:([^\]]+)\]\]", re.IGNORECASE)
INFOBOX_RE = re.compile(r"\{\{Infobox\s*([^\n\|]+)", re.IGNORECASE)
DISAMBIG_RE = re.compile(r"\{\{(?:[Dd]isambiguation|[Hh]ndis|[Gg]eodis)", re.IGNORECASE)
PEOPLE_CATS = re.compile(r"births|living people|deaths", re.IGNORECASE)
PEOPLE_BOXES = re.compile(
    r"person|scientist|writer|artist|philosopher|biography|academic|politician",
    re.IGNORECASE,
)
# Matches "1809 births", "384 BC births", "50 births"
BIRTH_CAT_RE = re.compile(r"(\d{1,4})(?:\s+(BC))?\s+births", re.IGNORECASE)
DEATH_CAT_RE = re.compile(r"(\d{1,4})(?:\s+(BC))?\s+deaths", re.IGNORECASE)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Filter Wikipedia dump to people pages (JSONL).")
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("datasets/enwiki-20251101-pages-articles-multistream.xml.bz2"),
        help="Path to enwiki XML.bz2 dump.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("people_pages.jsonl"),
        help="Output JSONL path.",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=max(1, mp.cpu_count() - 1),
        help="Number of worker processes (default: cpu_count-1).",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=200,
        help="Pages per batch sent to workers.",
    )
    parser.add_argument(
        "--limit-pages",
        type=int,
        default=None,
        help="Optional cap on pages to process (for smoke tests).",
    )
    return parser.parse_args()


def extract_categories(text: str) -> List[str]:
    return CATEGORY_RE.findall(text)


def extract_infoboxes(text: str) -> List[str]:
    return INFOBOX_RE.findall(text)


def extract_years(categories: List[str]) -> Tuple[Optional[int], Optional[int]]:
    birth_year = None
    death_year = None
    for cat in categories:
        b_match = BIRTH_CAT_RE.search(cat)
        if b_match:
            try:
                y = int(b_match.group(1))
                if b_match.group(2): # BC
                    y = -y
                birth_year = y
            except ValueError:
                pass
        d_match = DEATH_CAT_RE.search(cat)
        if d_match:
            try:
                y = int(d_match.group(1))
                if d_match.group(2): # BC
                    y = -y
                death_year = y
            except ValueError:
                pass
    return birth_year, death_year


def is_person(text: str, categories: List[str], infoboxes: List[str]) -> bool:
    if DISAMBIG_RE.search(text):
        return False
    if any(PEOPLE_CATS.search(cat) for cat in categories):
        return True
    if any(PEOPLE_BOXES.search(box) for box in infoboxes):
        return True
    return False


def page_to_record(page: mwxml.Page) -> Optional[dict]:
    if page.namespace != 0:
        return None
    if page.redirect:
        return None
    revision = page.latest_revision
    if revision is None or revision.text is None:
        return None
    text: str = revision.text
    categories = extract_categories(text)
    infoboxes = extract_infoboxes(text)
    if not is_person(text, categories, infoboxes):
        return None
    
    birth_year, death_year = extract_years(categories)
    return {
        "title": page.title,
        "page_id": page.id,
        "rev_id": revision.id,
        "categories": categories,
        "infoboxes": infoboxes,
        "birth_year": birth_year,
        "death_year": death_year,
    }


def process_batch(pages: List[dict]) -> List[dict]:
    results: List[dict] = []
    for pdata in pages:
        # pdata is a lightweight dict to avoid pickling full mwxml.Page
        text = pdata.get("text") or ""
        cats = extract_categories(text)
        boxes = extract_infoboxes(text)
        if not is_person(text, cats, boxes):
            continue
            
        birth_year, death_year = extract_years(cats)
        results.append(
            {
                "title": pdata["title"],
                "page_id": pdata["page_id"],
                "rev_id": pdata["rev_id"],
                "categories": cats,
                "infoboxes": boxes,
                "birth_year": birth_year,
                "death_year": death_year,
            }
        )
    return results


def page_stream(dump_path: Path) -> Iterable[mwxml.Page]:
    with bz2.open(dump_path, "rb") as fh:
        dump = mwxml.Dump.from_file(fh)
        for page in dump:
            yield page


def main() -> None:
    args = parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)

    pool = mp.Pool(processes=args.workers)
    buffer: List[dict] = []
    processed = 0

    with args.output.open("w", encoding="utf-8") as out:
        try:
            for page in page_stream(args.input):
                processed += 1
                last_rev = None
                for rev in page:
                    last_rev = rev
                text = last_rev.text if last_rev and last_rev.text else ""
                buffer.append(
                    {
                        "title": page.title,
                        "page_id": page.id,
                        "rev_id": last_rev.id if last_rev else None,
                        "text": text,
                    }
                )
                if len(buffer) >= args.batch_size:
                    for rec in pool.imap_unordered(process_batch, [buffer]):
                        for item in rec:
                            out.write(json.dumps(item, ensure_ascii=False) + "\n")
                    buffer = []
                if args.limit_pages and processed >= args.limit_pages:
                    break
            # flush remaining
            if buffer:
                for rec in pool.imap_unordered(process_batch, [buffer]):
                    for item in rec:
                        out.write(json.dumps(item, ensure_ascii=False) + "\n")
        finally:
            pool.close()
            pool.join()


if __name__ == "__main__":
    main()
