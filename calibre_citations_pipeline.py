#!/usr/bin/env python3
"""
Calibre-aware citation pipeline.

Input: a Calibre library directory (metadata.db + book folders with TXT exports).
Pipeline stages:
  1) Extract raw citations from each book's TXT.
  2) Clean/validate citations (heuristics + LLM).
  3) Resolve citations via Goodreads/Wikipedia workflow and emit graph-friendly JSON.

Outputs are written under a derived folder name: ./outputs/calibre_libs/<library_basename>/,
with subfolders for each stage. Each book's files are named by its Goodreads ID.
Books without a Goodreads ID are skipped with a warning.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from lib.cli_common import (
    ensure_repo_root, add_llm_args, add_pipeline_args,
    build_config_from_args, setup_logging, REPO_ROOT,
)

ensure_repo_root()

from lib.main_pipeline import BookPipeline

logger = logging.getLogger(__name__)

try:
    from tqdm import tqdm  # type: ignore
except ImportError:  # pragma: no cover
    tqdm = None


@dataclass
class CalibreBook:
    calibre_id: int
    title: str
    author_sort: str
    path: Path
    txt_path: Path
    epub_path: Optional[Path]
    goodreads_id: str
    description: Optional[str] = None


def load_calibre_books(library_dir: Path, allowed_goodreads_ids: Optional[Set[str]] = None) -> List[CalibreBook]:
    """Load Calibre metadata, focusing on books with a Goodreads identifier and TXT format."""
    db_path = library_dir / "metadata.db"
    if not db_path.exists():
        raise FileNotFoundError(f"No metadata.db found at {db_path}")

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT
            b.id,
            b.title,
            b.author_sort,
            b.path,
            d.name,
            d.format,
            i.val as goodreads_id,
            c.text as description
        FROM books b
        JOIN identifiers i ON i.book = b.id AND i.type = 'goodreads'
        LEFT JOIN data d ON d.book = b.id
        LEFT JOIN comments c ON c.book = b.id
        """
    )
    rows = cur.fetchall()
    conn.close()

    books: List[CalibreBook] = []
    for calibre_id, title, author_sort, rel_path, name, fmt, goodreads_id, description in rows:
        if not goodreads_id:
            continue
        if allowed_goodreads_ids is not None and str(goodreads_id) not in allowed_goodreads_ids:
            continue
        if fmt != "TXT":
            continue
        book_dir = library_dir / rel_path
        txt_path = book_dir / f"{name}.txt"
        epub_path = book_dir / f"{name}.epub"
        if not txt_path.exists():
            logger.warning(f"Skipping Goodreads {goodreads_id} ({title}) because TXT not found at {txt_path}")
            continue
        books.append(
            CalibreBook(
                calibre_id=calibre_id,
                title=title,
                author_sort=author_sort,
                path=book_dir,
                txt_path=txt_path,
                epub_path=epub_path if epub_path.exists() else None,
                goodreads_id=str(goodreads_id),
                description=(description.strip() if description else None),
            )
        )
    return books


def load_goodreads_metadata(book_ids: Set[str], db_path: str = "datasets/books_index.db") -> Dict[str, Any]:
    """Load metadata for a set of Goodreads book IDs from the SQLite index."""
    if not book_ids or not os.path.exists(db_path):
        return {}

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    placeholders = ",".join("?" for _ in book_ids)
    results = {}
    try:
        cur.execute(f"SELECT * FROM books WHERE book_id IN ({placeholders})", list(book_ids))
        for row in cur.fetchall():
            data = dict(row)
            if isinstance(data.get("authors"), str):
                try:
                    data["authors"] = json.loads(data["authors"])
                except json.JSONDecodeError:
                    pass
            results[str(data["book_id"])] = data
    except Exception as e:
        logger.error(f"Error loading Goodreads metadata: {e}")
    finally:
        conn.close()

    return results


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Calibre citation processing pipeline.")
    parser.add_argument("library_dir", type=Path,
                        help="Calibre library directory (contains metadata.db).")
    parser.add_argument("--output-dir", type=Path, default=None,
                        help="Base output directory. Defaults to ./outputs/calibre_libs/<library_basename>/")
    add_llm_args(parser)
    add_pipeline_args(parser)
    parser.add_argument("--only-goodreads-ids", type=str, default=None,
                        help="Comma-separated list of Goodreads IDs to process.")
    parser.add_argument("--debug-trace", action="store_true",
                        help="Enable verbose debug tracing.")
    return parser.parse_args()


async def run_pipeline(args):
    if not args.library_dir.exists():
        raise SystemExit(f"Library directory {args.library_dir} does not exist.")

    allowed_ids: Optional[Set[str]] = None
    if args.only_goodreads_ids:
        allowed_ids = {t.strip() for t in args.only_goodreads_ids.replace(",", " ").split() if t.strip()}

    logger.info("Loading Calibre metadata...")
    books = load_calibre_books(args.library_dir, allowed_ids)
    if not books:
        logger.warning("No eligible Calibre books found (need TXT format and Goodreads ID).")
        return

    config = build_config_from_args(args)
    pipeline = BookPipeline(config)

    output_base = args.output_dir or (Path("outputs") / "calibre_libs" / args.library_dir.name)
    setup_logging(output_base, verbose=args.verbose or args.debug_trace)

    book_ids_needed = {b.goodreads_id for b in books}
    source_metadata_map = load_goodreads_metadata(book_ids_needed, config.books_db)

    logger.info(f"Starting pipeline for {len(books)} books...")
    logger.info(f"Output Directory: {output_base}")

    iterator = tqdm(books, desc="Total Progress") if tqdm else books

    for book in iterator:
        if tqdm:
            iterator.set_description(f"Processing {book.title}")

        gr_meta = source_metadata_map.get(book.goodreads_id, {})
        source_meta = {
            "title": gr_meta.get("title") or book.title,
            "authors": gr_meta.get("author_names_resolved") or [book.author_sort],
            "goodreads_id": book.goodreads_id,
            "calibre_id": book.calibre_id,
            "description": book.description,
        }

        try:
            await pipeline.run_file(
                input_text_path=book.txt_path,
                output_dir=output_base,
                source_metadata=source_meta,
                book_id=book.goodreads_id,
            )
        except Exception as e:
            logger.error(f"Failed to process {book.title}: {e}", exc_info=True)


def main():
    args = parse_args()
    try:
        asyncio.run(run_pipeline(args))
    except KeyboardInterrupt:
        logger.info("Pipeline cancelled by user.")
    except Exception as e:
        logger.critical(f"Unhandled pipeline exception: {e}", exc_info=True)


if __name__ == "__main__":
    main()
