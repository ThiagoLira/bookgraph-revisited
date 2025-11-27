#!/usr/bin/env python3
"""Standalone CLI for querying the Goodreads SQLite index."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from lib.bibliography_agent.goodreads_tool import SQLiteGoodreadsCatalog  # pylint: disable=wrong-import-position


def main() -> None:
    parser = argparse.ArgumentParser(description="Query Goodreads FTS index directly.")
    parser.add_argument("--db-path", type=Path, default=Path("goodreads_data/books_index.db"))
    parser.add_argument("--title")
    parser.add_argument("--author")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--quiet", action="store_true", help="Print only summary info.")
    args = parser.parse_args()

    catalog = SQLiteGoodreadsCatalog(db_path=args.db_path, trace=False)
    matches = catalog.find_books(title=args.title, author=args.author, limit=args.limit)
    if args.quiet:
        if matches:
            top = matches[0]
            title = top.get("title") or "<untitled>"
            authors = ", ".join(top.get("authors", []))
            print(
                json.dumps(
                    {
                        "query": {"title": args.title, "author": args.author},
                        "count": len(matches),
                        "top_title": title,
                        "top_authors": authors,
                    },
                    ensure_ascii=False,
                )
            )
        else:
            print(
                json.dumps(
                    {"query": {"title": args.title, "author": args.author}, "count": 0},
                    ensure_ascii=False,
                )
            )
    else:
        payload = {
            "query": {"title": args.title, "author": args.author, "limit": args.limit},
            "matches": matches,
            "count": len(matches),
        }
        print(json.dumps(payload, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
