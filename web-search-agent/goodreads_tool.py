"""
Utilities that expose Goodreads search capabilities as LlamaIndex tools.

The latest dataset drop ships as newline-delimited JSON files under ``goodreads_data``.
This module reads the plain ``.json`` variants directly and memory-maps
``goodreads_books.json`` for high-throughput scans.

- ``goodreads_books.json`` – per-edition metadata including title, author IDs,
  and publication info.
- ``goodreads_book_authors.json`` – lookup table for author IDs to human names.
- ``goodreads_book_works.json`` – aggregate work-level statistics (not needed here).

The `create_book_lookup_tool` function below builds a `FunctionTool` that LLM agents
can call to verify whether a book exists given a title, an author, or both.
"""

from __future__ import annotations

import json
import math
import mmap
import os
import re
import threading
import multiprocessing as mp
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Iterable, List, Optional

if TYPE_CHECKING:  # pragma: no cover
    from llama_index.core.tools import FunctionTool


BOOKS_PATH = Path("goodreads_data/goodreads_books.json")
AUTHORS_PATH = Path("goodreads_data/goodreads_book_authors.json")
SEGMENT_SIZE_BYTES = 1 * 1024 * 1024  # 1MB per scan segment


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
    cleaned = re.sub(r"\s+", " ", text).strip().casefold()
    return cleaned


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
    result = dict(book)
    result["authors"] = _book_author_names_from_lookup(book, authors_lookup)
    result["publication_year"] = _to_int(book.get("publication_year"))
    result["publisher"] = book.get("publisher")
    result["book_id"] = str(book.get("book_id"))
    result["work_id"] = str(book.get("work_id"))
    result["average_rating"] = _to_float(book.get("average_rating"))
    result["ratings_count"] = _to_int(book.get("ratings_count"))
    result["text_reviews_count"] = _to_int(book.get("text_reviews_count"))
    result["link"] = book.get("link") or book.get("url")
    return result


_MP_AUTHORS: Dict[str, str] = {}


def _mp_init_worker(authors_lookup: Dict[str, str]) -> None:
    global _MP_AUTHORS
    _MP_AUTHORS = authors_lookup


def _matches_title_static(book: Dict[str, Any], title_norm: Optional[str]) -> bool:
    if not title_norm:
        return True
    for field in ("title", "title_without_series"):
        raw = book.get(field)
        if isinstance(raw, str) and title_norm in _normalize(raw):
            return True
    return False


def _matches_author_static(book: Dict[str, Any], author_norm: Optional[str]) -> bool:
    if not author_norm:
        return True
    for name in _book_author_names_from_lookup(book, _MP_AUTHORS):
        if author_norm in _normalize(name):
            return True
    return False


def _mp_scan_chunk(args) -> List[Dict[str, Any]]:
    path, start, end, title_norm, author_norm, limit = args
    matches: List[Dict[str, Any]] = []
    with open(path, "rb") as fh:
        mm = mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ)
        try:
            mm.seek(start)
            if start > 0:
                mm.readline()
            while mm.tell() < end:
                line = mm.readline()
                if not line:
                    break
                book = json.loads(line.decode("utf-8"))
                if not _matches_title_static(book, title_norm):
                    continue
                if not _matches_author_static(book, author_norm):
                    continue
                matches.append(_format_match_data(book, _MP_AUTHORS))
                if len(matches) >= limit:
                    break
        finally:
            mm.close()
    return matches


class GoodreadsCatalog:
    """Lightweight iterator-based index over Goodreads book metadata."""

    def __init__(
        self,
        books_path: Path | str = BOOKS_PATH,
        authors_path: Path | str = AUTHORS_PATH,
        parallel_workers: int = 20,
    ) -> None:
        self.books_path = Path(books_path)
        self.authors_path = Path(authors_path)
        self._authors: Dict[str, str] = {}
        self.parallel_workers = max(1, parallel_workers)
        self._load_authors()
        self._books_file = self.books_path.open("rb")
        self._books_mm = mmap.mmap(
            self._books_file.fileno(), 0, access=mmap.ACCESS_READ
        )
        if hasattr(self._books_mm, "madvise") and hasattr(mmap, "MADV_RANDOM"):
            self._books_mm.madvise(mmap.MADV_RANDOM)
        self._file_size = self._books_mm.size()
        self._chunk_bounds = self._compute_chunk_bounds(self.parallel_workers)

    def _compute_chunk_bounds(self, workers: int) -> List[tuple[int, int]]:
        mm = self._books_mm
        file_size = self._file_size
        workers = max(1, workers)
        boundaries = [0]
        for i in range(1, workers):
            approx = (file_size * i) // workers
            if approx >= file_size:
                break
            pos = mm.find(b"\n", approx)
            if pos == -1:
                break
            start_of_next_line = pos + 1
            if start_of_next_line < file_size and start_of_next_line > boundaries[-1]:
                boundaries.append(start_of_next_line)
        if boundaries[-1] != file_size:
            boundaries.append(file_size)
        unique = []
        last = -1
        for b in sorted(boundaries):
            if b > last:
                unique.append(b)
                last = b
        if unique[-1] != file_size:
            unique.append(file_size)
        return list(zip(unique[:-1], unique[1:]))

    def _load_authors(self) -> None:
        if not self.authors_path.exists():
            raise FileNotFoundError(
                f"Author dataset missing at {self.authors_path.resolve()}."
            )
        with self.authors_path.open("r", encoding="utf-8") as fh:
            for line in fh:
                row = json.loads(line)
                author_id = str(row.get("author_id"))
                name = row.get("name")
                if author_id and name:
                    self._authors[author_id] = name

    def _iter_books(self) -> Iterable[Dict[str, Any]]:
        if not self.books_path.exists():
            raise FileNotFoundError(
                f"Book dataset missing at {self.books_path.resolve()}."
            )
        self._books_mm.seek(0)
        while True:
            line = self._books_mm.readline()
            if not line:
                break
            yield json.loads(line.decode("utf-8"))

    def _desired_workers(self) -> int:
        if self._file_size <= self.parallel_workers * 1024:
            return 1
        return self.parallel_workers

    def close(self) -> None:
        if getattr(self, "_books_mm", None):
            self._books_mm.close()
        if getattr(self, "_books_file", None):
            self._books_file.close()

    def __del__(self) -> None:  # pragma: no cover - defensive cleanup
        try:
            self.close()
        except Exception:
            pass

    def _book_author_names(self, book: Dict[str, Any]) -> List[str]:
        names = []
        for author in book.get("authors", []) or []:
            author_id = str(author.get("author_id"))
            if not author_id:
                continue
            names.append(self._authors.get(author_id, author_id))
        return names

    def _matches_title(self, book: Dict[str, Any], title_norm: str) -> bool:
        for field in ("title", "title_without_series"):
            raw = book.get(field)
            if isinstance(raw, str) and title_norm in _normalize(raw):
                return True
        return False

    def _matches_author(self, book: Dict[str, Any], author_norm: str) -> bool:
        for name in self._book_author_names(book):
            if author_norm in _normalize(name):
                return True
        return False

    def find_books(
        self,
        title: Optional[str] = None,
        author: Optional[str] = None,
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        if not title and not author:
            raise ValueError("Provide at least a book title or author name.")

        title_norm = _normalize(title) if title else None
        author_norm = _normalize(author) if author else None

        worker_count = self._desired_workers()
        if worker_count <= 1:
            return self._scan_books_sequential(
                title_norm=title_norm,
                author_norm=author_norm,
                limit=limit,
            )
        return self._scan_books_parallel(
            title_norm=title_norm,
            author_norm=author_norm,
            limit=limit,
            worker_count=worker_count,
        )

    def _scan_books_sequential(
        self,
        *,
        title_norm: Optional[str],
        author_norm: Optional[str],
        limit: int,
    ) -> List[Dict[str, Any]]:
        matches: List[Dict[str, Any]] = []
        for book in self._iter_books():
            if not self._book_matches(book, title_norm, author_norm):
                continue
            matches.append(self._format_match(book))
            if len(matches) >= limit:
                break
        return matches

    def _scan_books_parallel(
        self,
        *,
        title_norm: Optional[str],
        author_norm: Optional[str],
        limit: int,
        worker_count: int,
    ) -> List[Dict[str, Any]]:
        matches: List[Dict[str, Any]] = []
        ctx = mp.get_context("fork" if os.name != "nt" else "spawn")
        tasks: List[tuple[Any, ...]] = []
        for start, end in self._chunk_bounds:
            segment_start = start
            while segment_start < end:
                segment_end = min(end, segment_start + SEGMENT_SIZE_BYTES)
                tasks.append(
                    (
                        self.books_path,
                        segment_start,
                        segment_end,
                        title_norm,
                        author_norm,
                        limit,
                    )
                )
                segment_start = segment_end
        with ctx.Pool(
            processes=worker_count,
            initializer=_mp_init_worker,
            initargs=(self._authors,),
        ) as pool:
            try:
                for chunk_matches in pool.imap_unordered(_mp_scan_chunk, tasks):
                    if not chunk_matches:
                        continue
                    matches.extend(chunk_matches)
                    if len(matches) >= limit:
                        pool.terminate()
                        break
            finally:
                pool.close()
                pool.join()
        return matches

    def _book_matches(
        self,
        book: Dict[str, Any],
        title_norm: Optional[str],
        author_norm: Optional[str],
    ) -> bool:
        if title_norm and not self._matches_title(book, title_norm):
            return False
        if author_norm and not self._matches_author(book, author_norm):
            return False
        return True

    def _format_match(self, book: Dict[str, Any]) -> Dict[str, Any]:
        return _format_match_data(book, self._authors)


def create_book_lookup_tool(
    *,
    books_path: Path | str = BOOKS_PATH,
    authors_path: Path | str = AUTHORS_PATH,
    description: Optional[str] = None,
    trace: bool = False,
    parallel_workers: int = 20,
) -> FunctionTool:
    """
    Build a LlamaIndex FunctionTool that verifies if a Goodreads book exists.

    Parameters
    ----------
    books_path:
        Path to ``goodreads_books.json`` (newline-delimited JSON).
    authors_path:
        Path to ``goodreads_book_authors.json`` (newline-delimited JSON).
    description:
        Optional override for the tool description presented to the LLM.

    Returns
    -------
    FunctionTool
        Ready-to-use tool that exposes a ``title``, ``author``, and ``limit``
        signature. The tool returns the top matches plus query metadata.
    """

    try:
        from llama_index.core.tools import FunctionTool
    except ImportError as exc:  # pragma: no cover - handled at runtime
        raise ImportError(
            "llama-index is required to build the Goodreads lookup tool. "
            "Install it via `uv sync` or `pip install llama-index`."
        ) from exc

    catalog = GoodreadsCatalog(
        books_path=books_path,
        authors_path=authors_path,
        parallel_workers=parallel_workers,
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

        def add_candidates(candidates: List[Dict[str, Any]]) -> None:
            for entry in candidates:
                book_id = entry.get("book_id")
                if not book_id:
                    continue
                if book_id in seen_ids:
                    continue
                seen_ids.add(book_id)
                matches.append(entry)
                if len(matches) >= limit:
                    break

        capped_limit = min(limit, 20)
        if title:
            add_candidates(
                catalog.find_books(title=title, author=None, limit=capped_limit)
            )
        if len(matches) < limit and author:
            add_candidates(
                catalog.find_books(title=None, author=author, limit=capped_limit)
            )
        if len(matches) < limit and title and author:
            add_candidates(
                catalog.find_books(title=title, author=author, limit=capped_limit)
            )

        if trace:
            print(
                "[goodreads_tool] lookup results:",
                json.dumps(
                    {"query": {"title": title, "author": author}, "matches": matches}
                ),
            )
        return {
            "query": {"title": title, "author": author, "limit": limit},
            "matches_found": len(matches),
            "matches": matches,
        }

    tool_description = description or (
        "Searches Goodreads edition metadata (title + authors). "
        "Provide a partial title, author, or both to verify whether a book exists."
    )
    return FunctionTool.from_defaults(
        fn=lookup_book,
        name="goodreads_book_lookup",
        description=tool_description,
    )
