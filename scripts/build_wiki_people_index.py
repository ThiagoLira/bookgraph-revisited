#!/usr/bin/env python3
"""
Build a SQLite FTS5 index from people_pages.jsonl.

Each row is keyed by title and stores:
  - title (FTS searchable)
  - infoboxes (joined string)
  - categories (joined string)
  - data (raw JSON for downstream use)

Output DB: datasets/wiki_people_index.db
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Iterable, Tuple


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build wiki people FTS index.")
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("people_pages.jsonl"),
        help="Path to people_pages.jsonl produced by filter_wiki_people.py",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("datasets/wiki_people_index.db"),
        help="Path to output SQLite DB.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=2000,
        help="Rows per transaction batch.",
    )
    return parser.parse_args()


def iter_people(path: Path) -> Iterable[Tuple[str, str, str, str]]:
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            obj = json.loads(line)
            title = obj.get("title") or ""
            infoboxes = obj.get("infoboxes") or []
            categories = obj.get("categories") or []
            infobox_str = " ".join(infoboxes)
            category_str = " ".join(categories)
            yield (
                title,
                infobox_str,
                category_str,
                json.dumps(obj, ensure_ascii=False),
            )


def init_db(db_path: Path) -> sqlite3.Connection:
    if db_path.exists():
        db_path.unlink()
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE VIRTUAL TABLE people_fts USING fts5("
        "title, infoboxes, categories, data, tokenize='porter'"
        ")"
    )
    return conn


def bulk_insert(conn: sqlite3.Connection, rows: Iterable[Tuple[str, str, str, str]], batch_size: int) -> None:
    cur = conn.cursor()
    batch = []
    for row in rows:
        batch.append(row)
        if len(batch) >= batch_size:
            cur.executemany("INSERT INTO people_fts VALUES (?,?,?,?)", batch)
            conn.commit()
            batch.clear()
    if batch:
        cur.executemany("INSERT INTO people_fts VALUES (?,?,?,?)", batch)
        conn.commit()


def main() -> None:
    args = parse_args()
    if not args.input.exists():
        raise SystemExit(f"Input not found: {args.input}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    conn = init_db(args.output)
    try:
        bulk_insert(conn, iter_people(args.input), args.batch_size)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
