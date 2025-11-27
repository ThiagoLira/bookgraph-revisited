"""
Basic smoke test for the Goodreads lookup tool.

Usage:
    python web-search-agent/test_tool.py
"""

from __future__ import annotations

from pathlib import Path

from bibliography_tool import GoodreadsCatalog


def main() -> None:
    catalog = GoodreadsCatalog(
        books_path=Path("goodreads_data/goodreads_books.json.gz"),
        authors_path=Path("goodreads_data/goodreads_book_authors.json.gz"),
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
