"""
Utilities that expose Goodreads search capabilities as LlamaIndex tools.

Books are indexed via SQLite FTS5 (see scripts/build_goodreads_index.py).
"""

from __future__ import annotations

import json
import re
import sqlite3
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Iterable, List, Optional

if TYPE_CHECKING:  # pragma: no cover
    from llama_index.core.tools import FunctionTool

BOOKS_DB_PATH = Path("goodreads_data/books_index.db")
AUTHORS_PATH = Path("goodreads_data/goodreads_book_authors.json")
BOOK_METADATA_KEYS = {
    "book_id",
    "work_id",
    "isbn",
    "isbn13",
    "title",
    "title_without_series",
    "publication_year",
    "publication_month",
    "publication_day",
    "publisher",
    "num_pages",
    "format",
    "average_rating",
    "ratings_count",
    "text_reviews_count",
}
MAX_DESCRIPTION_CHARS = 512


def _to_int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _to_float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().casefold()


def _format_match_data(book: Dict[str, Any]) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    for key in BOOK_METADATA_KEYS:
        value = book.get(key)
        if value in ("", None, [], {}):
            continue
        result[key] = value
    authors = book.get("author_names_resolved")
    if isinstance(authors, list) and authors:
        result["authors"] = authors
    else:
        fallback = []
        for author in book.get("authors", []) or []:
            name = author.get("name")
            if isinstance(name, str) and name.strip():
                fallback.append(name.strip())
        result["authors"] = fallback
    description = (book.get("description") or "").strip()
    if description:
        truncated = description[:MAX_DESCRIPTION_CHARS]
        if len(description) > MAX_DESCRIPTION_CHARS:
            truncated = truncated.rstrip() + "..."
        result["description"] = truncated
    result["publication_year"] = _to_int(book.get("publication_year"))
    result["publication_month"] = _to_int(book.get("publication_month"))
    result["publication_day"] = _to_int(book.get("publication_day"))
    result["publisher"] = book.get("publisher")
    result["num_pages"] = _to_int(book.get("num_pages"))
    result["book_id"] = str(book.get("book_id")) if book.get("book_id") else None
    result["work_id"] = str(book.get("work_id")) if book.get("work_id") else None
    result["average_rating"] = _to_float(book.get("average_rating"))
    result["ratings_count"] = _to_int(book.get("ratings_count"))
    result["text_reviews_count"] = _to_int(book.get("text_reviews_count"))
    link = book.get("link") or book.get("url")
    if link:
        result["link"] = link
    return {k: v for k, v in result.items() if v not in (None, "", [], {})}


class SQLiteGoodreadsCatalog:
    """Search Goodreads book metadata via SQLite FTS5."""

    def __init__(self, db_path: Path | str = BOOKS_DB_PATH, trace: bool = False) -> None:
        self.db_path = Path(db_path)
        self.trace = trace
        if not self.db_path.exists():
            raise FileNotFoundError(
                f"{self.db_path} not found. Run scripts/build_goodreads_index.py first."
            )
        self._conn = sqlite3.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row
        if trace:
            print(f"[goodreads_tool] Connected to {self.db_path}")

    def _fts_escape(self, text: str) -> str:
        return text.replace('"', '""')

    def find_books(
        self,
        title: Optional[str] = None,
        author: Optional[str] = None,
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        if not title and not author:
            raise ValueError("Provide at least a title or author.")

        clauses: List[str] = []
        if title:
            clauses.append(f'title : "{self._fts_escape(title)}"')
        if author:
            clauses.append(f'authors : "{self._fts_escape(author)}"')
        query = " AND ".join(clauses)
        if self.trace:
            print(f"[goodreads_tool] FTS query string: {query}")

        sql = """
            SELECT data
            FROM books_fts
            WHERE books_fts MATCH ?
            ORDER BY rank
            LIMIT ?
        """

        start = time.perf_counter()
        try:
            rows = self._conn.execute(sql, (query, limit)).fetchall()
        except sqlite3.OperationalError as exc:
            if self.trace:
                print(f"[goodreads_tool] FTS query error: {exc}")
            return []
        duration = time.perf_counter() - start

        matches = []
        for row in rows:
            payload = row["data"]
            try:
                book = json.loads(payload)
            except json.JSONDecodeError:
                continue
            matches.append(_format_match_data(book))
        if self.trace:
            print(
                f"[goodreads_tool] SQLite search returned {len(matches)} matches "
                f"in {duration:.3f}s"
            )
        return matches


class GoodreadsAuthorCatalog:
    """Loads author metadata into a simple in-memory list.

    Uses class-level caching to avoid reloading the same authors file
    multiple times across different instances.
    """

    # Class-level cache shared by all instances
    _cached_authors: List[Dict[str, Any]] = []
    _cached_path: Path | None = None

    def __init__(self, authors_path: Path | str = AUTHORS_PATH) -> None:
        self.authors_path = Path(authors_path)
        self._load_authors()

    def _load_authors(self) -> None:
        # Use cached data if available and path matches
        if (GoodreadsAuthorCatalog._cached_authors and
            GoodreadsAuthorCatalog._cached_path == self.authors_path):
            return

        if not self.authors_path.exists():
            raise FileNotFoundError(
                f"Author dataset missing at {self.authors_path.resolve()}."
            )

        # Load and cache the data at class level
        authors_list: List[Dict[str, Any]] = []
        with self.authors_path.open("r", encoding="utf-8") as fh:
            for line in fh:
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                authors_list.append(row)

        # Update class-level cache
        GoodreadsAuthorCatalog._cached_authors = authors_list
        GoodreadsAuthorCatalog._cached_path = self.authors_path

    def find_authors(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        if not query:
            return []
        norm = _normalize(query)
        matches: List[Dict[str, Any]] = []
        # Use the class-level cached data
        for row in GoodreadsAuthorCatalog._cached_authors:
            name = row.get("name")
            if not isinstance(name, str):
                continue
            if norm in _normalize(name):
                matches.append(
                    {
                        "author_id": str(row.get("author_id")),
                        "name": name,
                        "average_rating": row.get("average_rating"),
                        "works_count": row.get("works_count"),
                        "fans_count": row.get("fans_count"),
                        "link": row.get("link") or row.get("url"),
                    }
                )
            if len(matches) >= limit:
                break
        return matches


def create_book_lookup_tool(
    *,
    description: Optional[str] = None,
    trace: bool = False,
    db_path: Path | str = BOOKS_DB_PATH,
    catalog: Optional[Any] = None,
) -> "FunctionTool":
    """Build a LlamaIndex FunctionTool that verifies if a Goodreads book exists."""
    try:
        from llama_index.core.tools import FunctionTool
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "llama-index is required to build the Goodreads lookup tool. "
            "Install it via `uv sync` or `pip install llama-index`."
        ) from exc

    catalog_obj = catalog or SQLiteGoodreadsCatalog(
        db_path=db_path,
        trace=trace,
    )

    def lookup_book(
        title: Optional[str] = None,
        author: Optional[str] = None,
        limit: int = 5,
    ) -> Dict[str, Any]:
        if trace:
            print(
                "[goodreads_tool] lookup_book call "
                f"title={title!r} author={author!r} limit={limit}"
            )
        if not title and not author:
            raise ValueError("Provide at least a title or author.")

        seen_ids = set()
        matches: List[Dict[str, Any]] = []

        def add_candidates(reason: str, candidates: List[Dict[str, Any]]) -> None:
            if trace:
                print(
                    f"[goodreads_tool] add_candidates via {reason}: "
                    f"{len(candidates)} rows"
                )
            for entry in candidates:
                book_id = entry.get("book_id")
                if not book_id or book_id in seen_ids:
                    continue
                seen_ids.add(book_id)
                matches.append(entry)
                if len(matches) >= limit:
                    break

        capped_limit = min(limit, 20)
        if title:
            add_candidates(
                "title-only",
                catalog_obj.find_books(title=title, author=None, limit=capped_limit),
            )
        if len(matches) < limit and author:
            add_candidates(
                "author-only",
                catalog_obj.find_books(title=None, author=author, limit=capped_limit),
            )

        if trace:
            print(
                "[goodreads_tool] lookup results:\n",
                json.dumps(
                    {"query": {"title": title, "author": author}, "matches": matches},
                    indent=2,
                    ensure_ascii=False,
                ),
            )
        return {
            "query": {"title": title, "author": author, "limit": limit},
            "matches_found": len(matches),
            "matches": matches,
        }

    tool_description = description or (
        "Searches Goodreads edition metadata by title or author (one field per call)."
    )
    return FunctionTool.from_defaults(
        fn=lookup_book,
        name="goodreads_book_lookup",
        description=tool_description,
    )


def create_author_lookup_tool(
    *,
    authors_path: Path | str = AUTHORS_PATH,
    description: Optional[str] = None,
    trace: bool = False,
) -> "FunctionTool":
    try:
        from llama_index.core.tools import FunctionTool
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "llama-index is required to build the Goodreads lookup tool. "
            "Install it via `uv sync` or `pip install llama-index`."
        ) from exc

    catalog = GoodreadsAuthorCatalog(authors_path=authors_path)

    def lookup_author(author: Optional[str] = None, limit: int = 5) -> Dict[str, Any]:
        norm_limit = min(limit, 20)
        matches = catalog.find_authors(author or "", limit=norm_limit)
        if trace:
            print(
                "[goodreads_tool] lookup_author\n",
                json.dumps(
                    {"query": author, "matches_found": len(matches), "matches": matches},
                    indent=2,
                    ensure_ascii=False,
                ),
            )
        return {
            "query": {"author": author, "limit": norm_limit},
            "matches_found": len(matches),
            "matches": matches,
        }

    tool_description = description or (
        "Searches Goodreads author metadata. Use when only the author is known and "
        "you need to disambiguate identities."
    )
    return FunctionTool.from_defaults(
        fn=lookup_author,
        name="goodreads_author_lookup",
        description=tool_description,
    )
