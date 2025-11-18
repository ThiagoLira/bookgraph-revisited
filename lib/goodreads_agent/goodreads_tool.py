"""
Utilities that expose Goodreads search capabilities as LlamaIndex tools.

This version stores book metadata in a SQLite FTS5 index (built via
``scripts/build_goodreads_index.py``) so lookups are fast and memory-light.
"""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Iterable, List, Optional

if TYPE_CHECKING:  # pragma: no cover
    from llama_index.core.tools import FunctionTool


BOOKS_PATH = Path("goodreads_data/goodreads_books.json")
AUTHORS_PATH = Path("goodreads_data/goodreads_book_authors.json")
BOOKS_DB_PATH = Path("goodreads_data/books_index.db")
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


def _book_author_names_from_lookup(
    book: Dict[str, Any], authors_lookup: Dict[str, str]
) -> List[str]:
    names = []
    for author in book.get("authors", []) or []:
        author_id = str(author.get("author_id"))
        if not author_id:
            continue
        names.append(authors_lookup.get(author_id, author_id))
    return names


def _format_match_data(
    book: Dict[str, Any], authors_lookup: Dict[str, str]
) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    for key in BOOK_METADATA_KEYS:
        value = book.get(key)
        if value in ("", None, [], {}):
            continue
        result[key] = value
    description = (book.get("description") or "").strip()
    if description:
        truncated = description[:MAX_DESCRIPTION_CHARS]
        if len(description) > MAX_DESCRIPTION_CHARS:
            truncated = truncated.rstrip() + "..."
        result["description"] = truncated
    result["authors"] = _book_author_names_from_lookup(book, authors_lookup)
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

    def __init__(
        self,
        db_path: Path | str = BOOKS_DB_PATH,
        authors_path: Path | str = AUTHORS_PATH,
        trace: bool = False,
    ) -> None:
        self.db_path = Path(db_path)
        self.trace = trace
        if not self.db_path.exists():
            raise FileNotFoundError(
                f"{self.db_path} not found. Run scripts/build_goodreads_index.py first."
            )
        self.authors_lookup = self._load_authors(Path(authors_path))

    def _load_authors(self, authors_path: Path) -> Dict[str, str]:
        if not authors_path.exists():
            raise FileNotFoundError(
                f"Author dataset missing at {authors_path.resolve()}."
            )
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

    def _fts_escape(self, text: str) -> str:
        return text.replace('"', '""')

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

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

        sql = """
            SELECT data
            FROM books_fts
            WHERE books_fts MATCH ?
            ORDER BY rank
            LIMIT ?
        """

        conn = self._connect()
        try:
            rows = conn.execute(sql, (query, limit)).fetchall()
        except sqlite3.OperationalError as exc:
            if self.trace:
                print(f"[goodreads_tool] FTS query error: {exc}")
            return []
        finally:
            conn.close()

        matches = []
        for row in rows:
            payload = row["data"]
            try:
                book = json.loads(payload)
            except json.JSONDecodeError:
                continue
            matches.append(_format_match_data(book, self.authors_lookup))
        if self.trace:
            print(f"[goodreads_tool] SQLite search returned {len(matches)} matches")
        return matches


class GoodreadsAuthorCatalog:
    """Loads author metadata into a simple in-memory list."""

    def __init__(self, authors_path: Path | str = AUTHORS_PATH) -> None:
        self.authors_path = Path(authors_path)
        self._authors: List[Dict[str, Any]] = []
        self._load_authors()

    def _load_authors(self) -> None:
        if not self.authors_path.exists():
            raise FileNotFoundError(
                f"Author dataset missing at {self.authors_path.resolve()}."
            )
        with self.authors_path.open("r", encoding="utf-8") as fh:
            for line in fh:
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                self._authors.append(row)

    def find_authors(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        if not query:
            return []
        norm = _normalize(query)
        matches: List[Dict[str, Any]] = []
        for row in self._authors:
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
    books_path: Path | str = BOOKS_PATH,
    authors_path: Path | str = AUTHORS_PATH,
    description: Optional[str] = None,
    trace: bool = False,
    db_path: Path | str = BOOKS_DB_PATH,
    catalog: Optional[Any] = None,
) -> "FunctionTool":
    """
    Build a LlamaIndex FunctionTool that verifies if a Goodreads book exists.
    """

    try:
        from llama_index.core.tools import FunctionTool
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "llama-index is required to build the Goodreads lookup tool. "
            "Install it via `uv sync` or `pip install llama-index`."
        ) from exc

    catalog_obj = catalog or SQLiteGoodreadsCatalog(
        db_path=db_path,
        authors_path=authors_path,
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
        seen_ids = set()
        matches: List[Dict[str, Any]] = []

        def add_candidates(reason: str, candidates: List[Dict[str, Any]]) -> None:
            if trace:
                print(f"[goodreads_tool] add_candidates via {reason}: {len(candidates)} rows")
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
                "title-only", catalog_obj.find_books(title=title, author=None, limit=capped_limit)
            )
        if len(matches) < limit and author:
            add_candidates(
                "author-only", catalog_obj.find_books(title=None, author=author, limit=capped_limit)
            )

        if trace:
            print(
                "[goodreads_tool] lookup results:",
                json.dumps(
                    {"query": {"title": title, "author": author}, "matches": matches},
                    ensure_ascii=False,
                ),
            )
        return {
            "query": {"title": title, "author": author, "limit": limit},
            "matches_found": len(matches),
            "matches": matches,
        }

    tool_description = description or (
        "Searches Goodreads edition metadata by title or author. "
        "Provide a partial title OR author (one field per call)."
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
                "[goodreads_tool] lookup_author",
                json.dumps({"author": author, "matches": len(matches)}),
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
