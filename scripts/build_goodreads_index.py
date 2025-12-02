#!/usr/bin/env python3
"""
One-time utility to build a SQLite FTS5 index for Goodreads books.

Usage:
    uv run python scripts/build_goodreads_index.py
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Dict, Iterable, List

BOOKS_JSON = Path("goodreads_data/goodreads_books.json")
AUTHORS_JSON = Path("goodreads_data/goodreads_book_authors.json")
DEFAULT_DB = Path("goodreads_data/books_index.db")
MAX_DESCRIPTION_CHARS = 512


def load_authors(authors_path: Path) -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    with authors_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            author_id = str(row.get("author_id"))
            name = row.get("name")
            if author_id and isinstance(name, str):
                mapping[author_id] = name
    return mapping


def chunks(iterable: Iterable[dict], size: int) -> Iterable[List[dict]]:
    batch: List[dict] = []
    for item in iterable:
        batch.append(item)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch


def build_index(db_path: Path, books_path: Path, authors: Dict[str, str], batch_size: int) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode = OFF;")
    conn.execute("PRAGMA synchronous = OFF;")
    conn.execute("PRAGMA temp_store = MEMORY;")
    cur = conn.cursor()
    cur.execute("DROP TABLE IF EXISTS books_fts;")
    cur.execute("DROP TABLE IF EXISTS books;")
    
    # FTS table for text search
    cur.execute(
        """
        CREATE VIRTUAL TABLE books_fts USING fts5(
            title,
            authors,
            book_id UNINDEXED,
            data UNINDEXED
        );
        """
    )
    
    # Standard table for ID lookup
    cur.execute(
        """
        CREATE TABLE books (
            book_id TEXT PRIMARY KEY,
            data TEXT
        );
        """
    )

    def iter_books():
        with books_path.open("r", encoding="utf-8") as fh:
            for raw_line in fh:
                try:
                    row = json.loads(raw_line)
                except json.JSONDecodeError:
                    continue
                title = row.get("title", "")
                author_names: List[str] = []
                author_ids: List[str] = []
                for author in row.get("authors", []) or []:
                    if not isinstance(author, dict):
                        continue
                    name = author.get("name")
                    if name:
                        author_names.append(str(name))
                    author_id = author.get("author_id")
                    if author_id is not None:
                        author_ids.append(str(author_id))
                        mapped = authors.get(str(author_id))
                        if mapped and mapped not in author_names:
                            author_names.append(mapped)
                authors_field = " ".join(author_names)
                row["author_names_resolved"] = author_names
                if author_ids:
                    row["author_ids"] = author_ids
                description = (row.get("description") or "").strip()
                if description:
                    row["description"] = (
                        description[:MAX_DESCRIPTION_CHARS].rstrip() + "..."
                        if len(description) > MAX_DESCRIPTION_CHARS
                        else description
                    )
                yield (
                    title,
                    authors_field,
                    str(row.get("book_id", "")),
                    json.dumps(row, ensure_ascii=False),
                )

    total = 0
    for batch in chunks(iter_books(), batch_size):
        # Insert into FTS
        cur.executemany(
            "INSERT INTO books_fts(title, authors, book_id, data) VALUES (?, ?, ?, ?)",
            [(b[0], b[1], b[2], b[3]) for b in batch],
        )
        # Insert into standard table
        cur.executemany(
            "INSERT OR IGNORE INTO books(book_id, data) VALUES (?, ?)",
            [(b[2], b[3]) for b in batch],
        )
        conn.commit()
        total += len(batch)
        if total % (batch_size * 10) == 0:
            print(f"Indexed {total} books...", end="\r")

    cur.execute("INSERT INTO books_fts(books_fts) VALUES('optimize');")
    conn.commit()
    conn.close()
    print(f"\nDone! Indexed {total} books into {db_path}.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Goodreads SQLite FTS index.")
    parser.add_argument("--books-json", type=Path, default=BOOKS_JSON, help="Path to goodreads_books.json")
    parser.add_argument("--authors-json", type=Path, default=AUTHORS_JSON, help="Path to goodreads_book_authors.json")
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB, help="Destination SQLite DB path")
    parser.add_argument("--batch-size", type=int, default=5000, help="Insert batch size")
    parser.add_argument("--force", action="store_true", help="Overwrite existing DB if present")
    args = parser.parse_args()

    if not args.books_json.exists():
        raise SystemExit(f"Books file not found: {args.books_json}")
    if not args.authors_json.exists():
        raise SystemExit(f"Authors file not found: {args.authors_json}")
    if args.db_path.exists():
        if not args.force:
            print(f"{args.db_path} already exists. Use --force to rebuild.")
            return
        args.db_path.unlink()

    print("Loading authors...")
    authors = load_authors(args.authors_json)
    print(f"Loaded {len(authors)} authors.")
    print("Building FTS index (this may take a few minutes)...")
    build_index(args.db_path, args.books_json, authors, args.batch_size)


if __name__ == "__main__":
    main()
