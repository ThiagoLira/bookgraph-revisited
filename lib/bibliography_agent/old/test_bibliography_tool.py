"""
Basic smoke test for the Goodreads lookup tool.

Usage:
    python -m lib.bibliography_agent.test_bibliography_tool
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(ROOT))

from lib.bibliography_agent.bibliography_tool import GoodreadsCatalog


def main() -> None:
    catalog = GoodreadsCatalog(
        books_path=Path("datasets/goodreads_books.json.gz"),
        authors_path=Path("datasets/goodreads_book_authors.json.gz"),
    )
    matches = catalog.find_books(title="The Hobbit", author="Tolkien", limit=5)
    if not matches:
        raise SystemExit("FAIL: no matches returned for The Hobbit.")

    first = matches[0]
    title = (first.get("title") or "").lower()
    authors = " ".join(first.get("authors") or []).lower()

    if "hobbit" not in title or "tolkien" not in authors:
        raise SystemExit(
            f"FAIL: unexpected top match {first!r}. Expected Tolkien's The Hobbit."
        )

    print("PASS: Found The Hobbit by Tolkien in Goodreads dataset.")
    print(f"Top match: {first}")


if __name__ == "__main__":
    main()
