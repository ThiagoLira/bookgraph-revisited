#!/usr/bin/env python3
"""
Calibre-aware citation pipeline.

Input: a Calibre library directory (metadata.db + book folders with TXT exports).
Pipeline stages:
  1) Extract raw citations from each book's TXT (stage 1 cache).
  2) Preprocess/dedupe citations (stage 2 cache).
  3) Goodreads agent to resolve metadata/IDs and emit graph-friendly JSON (stage 3 cache).

Outputs are written under a derived folder name: ./calibre_outputs/<library_basename>/,
with subfolders for each stage. Each book's files are named by its Goodreads ID.
Books without a Goodreads ID are skipped with a warning.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sqlite3
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from lib.extract_citations import (
    ExtractionConfig,
    ProgressCallback,
    process_book,
    write_output,
)
from preprocess_citations import preprocess as preprocess_citations
from lib.bibliography_agent.agent import SYSTEM_PROMPT, build_agent
from lib.bibliography_agent.test_bibliography_agent import build_prompts

try:
    from tqdm import tqdm  # type: ignore
except ImportError:  # pragma: no cover
    tqdm = None

# Tunable defaults (aligned with existing pipeline)
EXTRACT_CHUNK_SIZE = 50
EXTRACT_MAX_CONCURRENCY = 20
EXTRACT_MAX_CONTEXT = 6144
EXTRACT_MAX_COMPLETION = 2048
EXTRACT_MODEL_ID = "Qwen/Qwen3-30B-A3B"

AGENT_MODEL_ID = "qwen/qwen3-next-80b-a3b-instruct"


def progress_iter(iterable: Iterable[Path], **kwargs: object) -> Iterable[Path]:
    if tqdm is None:
        return iterable
    return tqdm(iterable, **kwargs)


def progress_iter_items(iterable: Iterable[Any], **kwargs: object) -> Iterable[Any]:
    if tqdm is None:
        return iterable
    return tqdm(iterable, **kwargs)


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
            print(f"[calibre] Skipping book {
                  title!r} (Calibre ID {calibre_id}) with no Goodreads ID.")
            continue
        if allowed_goodreads_ids is not None and str(goodreads_id) not in allowed_goodreads_ids:
            continue
        if fmt != "TXT":
            # We only process TXT sources in this pipeline.
            continue
        book_dir = library_dir / rel_path
        txt_path = book_dir / f"{name}.txt"
        epub_path = book_dir / f"{name}.epub"
        if not txt_path.exists():
            print(f"[calibre] Skipping Goodreads {goodreads_id} ({
                  title}) because TXT not found at {txt_path}")
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


async def run_extraction(
    txt_path: Path,
    output_path: Path,
    base_url: str,
    api_key: str,
    model_id: str,
    chunk_size: int,
    max_context: int,
    progress_callback: Optional[ProgressCallback] = None,
) -> None:
    config = ExtractionConfig(
        input_path=txt_path,
        chunk_size=chunk_size,
        max_concurrency=EXTRACT_MAX_CONCURRENCY,
        max_context_per_request=max_context,
        max_completion_tokens=EXTRACT_MAX_COMPLETION,
        base_url=base_url,
        api_key=api_key,
        model=model_id,
        tokenizer_name=model_id,
    )
    result = await process_book(config, progress_callback=progress_callback)
    write_output(result, output_path)


def stage_extract(
    books: Iterable[CalibreBook],
    output_dir: Path,
    base_url: str,
    api_key: str,
    model_id: str,
    chunk_size: int,
    max_context: int,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    iterator = progress_iter_items(
        books,
        desc="Stage 1/3: Extraction",
        unit="book",
    )
    for book in iterator:
        out_path = output_dir / f"{book.goodreads_id}.json"
        if out_path.exists():
            print(f"[extract] Skip {book.title} (cached).")
            continue
        print(f"[extract] Processing {book.title} -> {out_path}")
        if tqdm is None:
            asyncio.run(run_extraction(book.txt_path, out_path,
                        base_url, api_key, model_id, chunk_size, max_context))
            continue
        chunk_bar = tqdm(
            desc=f"  chunks for {book.title}",
            unit="chunk",
            leave=False,
        )

        def on_chunk_progress(done: int, total: int) -> None:
            if chunk_bar.total != total:
                chunk_bar.total = total
            chunk_bar.n = done
            chunk_bar.refresh()

        try:
            asyncio.run(
                run_extraction(
                    book.txt_path,
                    out_path,
                    base_url,
                    api_key,
                    model_id,
                    chunk_size,
                    max_context,
                    progress_callback=on_chunk_progress,
                )
            )
        finally:
            chunk_bar.close()


def stage_preprocess(raw_dir: Path, output_dir: Path, books: Iterable[CalibreBook]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for book in progress_iter_items(books, desc="Stage 2/3: Preprocess", unit="book"):
        raw_path = raw_dir / f"{book.goodreads_id}.json"
        pre_path = output_dir / f"{book.goodreads_id}.json"
        if pre_path.exists():
            print(f"[preprocess] Skip {book.title} (cached).")
            continue
        if not raw_path.exists():
            print(f"[preprocess] Missing raw JSON for {book.title}, skipping.")
            continue
        print(f"[preprocess] {raw_path} -> {pre_path}")
        processed = preprocess_citations(
            raw_path,
            source_title=book.title,
            source_authors=[book.author_sort],
        )
        pre_path.write_text(json.dumps(processed, indent=2,
                            ensure_ascii=False), encoding="utf-8")


def build_agent_runner(
    base_url: str,
    api_key: str,
    model_id: str,
    trace_tool: bool,
    system_prompt: Optional[str] = None,
    wiki_people_path: str = "goodreads_data/wiki_people_index.db",
) -> "GoodreadsAgentRunner":
    return build_agent(
        model=model_id,
        api_key=api_key,
        base_url=base_url,
        books_path="goodreads_data/goodreads_books.json",
        authors_path="goodreads_data/goodreads_book_authors.json",
        wiki_people_path=wiki_people_path,
        verbose=trace_tool,
        trace_tool=trace_tool,
        system_prompt=system_prompt,
    )


def format_system_prompt(book: CalibreBook) -> str:
    desc = book.description.strip() if book.description else "No Calibre description available."
    return (
        f"{SYSTEM_PROMPT}\n\n"
        "SOURCE BOOK CONTEXT\n"
        f"- Title: {book.title}\n"
        f"- Authors: {book.author_sort}\n"
        f"- Goodreads ID: {book.goodreads_id}\n"
        f"- Calibre description: {desc}\n"
        "Use this source context to disambiguate citations; never fabricate metadata."
    )


def load_goodreads_metadata(book_ids: Set[str]) -> Dict[str, Dict[str, Any]]:
    """Load a small subset of Goodreads book metadata for the given IDs."""
    result: Dict[str, Dict[str, Any]] = {}
    books_path = Path("goodreads_data/goodreads_books.json")
    if not books_path.exists() or not book_ids:
        return result
    remaining = set(book_ids)
    with books_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            bid = str(row.get("book_id")) if row.get(
                "book_id") is not None else None
            if bid and bid in remaining:
                result[bid] = row
                remaining.discard(bid)
                if not remaining:
                    break
    return result


def pick_match_type(payload: Dict[str, Any]) -> Tuple[str, Optional[str], List[str], Optional[Dict[str, Any]]]:
    """
    Decide whether a match is a book, author, or person and return:
      (target_type, book_id, author_ids, wiki_person)
    """
    book_id = payload.get("book_id") or payload.get("id") or None
    author_ids = []
    if "author_ids" in payload and isinstance(payload["author_ids"], list):
        author_ids = [str(a) for a in payload["author_ids"] if a]
    elif "author_id" in payload and payload["author_id"]:
        author_ids = [str(payload["author_id"])]
    wiki_match = payload.get("wikipedia_match") or {}
    wiki_page_id = payload.get("wikipedia_page_id") or wiki_match.get("page_id")
    wiki_title = wiki_match.get("title") or payload.get("wikipedia_title")
    wiki_person = None
    if wiki_page_id:
        wiki_person = {"wikipedia_page_id": wiki_page_id, "wikipedia_title": wiki_title}
    if book_id:
        return ("book", str(book_id), author_ids, wiki_person)
    if author_ids:
        return ("author", None, author_ids, wiki_person)
    if wiki_person:
        return ("person", None, [], wiki_person)
    return ("unknown", None, [], None)


async def stage_agent_async(
    books: Iterable[CalibreBook],
    pre_dir: Path,
    output_dir: Path,
    base_url: str,
    api_key: str,
    model_id: str,
    trace_tool: bool,
    agent_max_workers: int,
    debug_trace: bool = False,
) -> None:
    from lib.bibliography_agent.bibliography_tool import SQLiteGoodreadsCatalog

    books = list(books)

    if agent_max_workers < 1:
        raise ValueError("--agent-max-workers must be at least 1.")

    output_dir.mkdir(parents=True, exist_ok=True)

    # Prefetch source Goodreads metadata for source nodes
    book_ids_needed: Set[str] = {b.goodreads_id for b in books}
    source_goodreads_meta = load_goodreads_metadata(book_ids_needed)

    for book in progress_iter_items(books, desc="Stage 3/3: Goodreads agent", unit="book"):
        system_prompt = format_system_prompt(book)
        runners = [
            build_agent_runner(base_url, api_key, model_id,
                               trace_tool or debug_trace, system_prompt=system_prompt)
            for _ in range(agent_max_workers)
        ]
        runner_queue: asyncio.Queue["GoodreadsAgentRunner"] = asyncio.Queue()
        for idx, runner in enumerate(runners):
            runner_queue.put_nowait((idx, runner))

        # Per-worker catalogs to avoid SQLite thread issues
        catalogs = [SQLiteGoodreadsCatalog(
            trace=trace_tool) for _ in range(agent_max_workers)]
        catalog_queue: asyncio.Queue[SQLiteGoodreadsCatalog] = asyncio.Queue()
        for idx, catalog in enumerate(catalogs):
            catalog_queue.put_nowait((idx, catalog))

        pre_path = pre_dir / f"{book.goodreads_id}.json"
        final_path = output_dir / f"{book.goodreads_id}.json"
        if final_path.exists():
            print(f"[agent] Skip {book.title} (cached).")
            continue
        if not pre_path.exists():
            print(f"[agent] Missing preprocessed JSON for {
                  book.title}, skipping.")
            continue

        data = json.loads(pre_path.read_text(encoding="utf-8"))
        citations = data.get("citations", [])
        prompts = build_prompts(
            citations,
            source_title=book.title,
            source_authors=[book.author_sort],
            source_description=book.description,
        )
        print(f"[agent] Processing {
              len(citations)} citations for {book.title}")

        if not citations:
            final_path.write_text(
                json.dumps(
                    {
                        "source": {
                            "title": book.title,
                            "authors": [book.author_sort],
                            "goodreads_id": book.goodreads_id,
                            "author_ids": [],
                            "calibre": {
                                "id": book.calibre_id,
                                "path": str(book.path),
                                "txt_path": str(book.txt_path),
                                "epub_path": str(book.epub_path) if book.epub_path else None,
                            },
                        },
                        "citations": [],
                    },
                    indent=2,
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            continue

        citation_bar = None
        if tqdm is not None:
            citation_bar = tqdm(
                total=len(citations),
                desc=f"  citations for {book.title}",
                unit="citation",
                leave=False,
            )

        def _extract_json_snippet(text: str) -> Optional[Dict[str, Any]]:
            text = text.strip()
            if not text:
                return None
            try:
                return json.loads(text)
            except Exception:
                pass
            fence = re.search(
                r"```json\s*(\{.*?\})\s*```", text, flags=re.DOTALL)
            if fence:
                snippet = fence.group(1).strip()
                try:
                    return json.loads(snippet)
                except Exception:
                    pass
            brace = re.search(r"(\{.*\})", text, flags=re.DOTALL)
            if brace:
                snippet = brace.group(1)
                try:
                    return json.loads(snippet)
                except Exception:
                    pass
            return None

        async def process_single_citation(
            idx: int,
            citation: Dict[str, Any],
            prompt: str,
        ) -> tuple[int, Optional[Dict[str, Any]]]:
            runner_idx, runner = await runner_queue.get()
            catalog_idx, catalog = await catalog_queue.get()
            if debug_trace:
                print(f"[trace agent={runner_idx}] citation[{
                      idx}] prompt:\n{prompt}\n{'-' * 40}")
            try:
                start = time.perf_counter()
                response = await runner.query(prompt)
            finally:
                runner_queue.put_nowait((runner_idx, runner))

            response_str = response.strip()
            if response_str.startswith("<tool_call>"):
                tool_body = response_str.split(">", 1)[1].strip(
                ) if ">" in response_str else response_str
                tool_payload = _extract_json_snippet(tool_body)
                if tool_payload and isinstance(tool_payload, dict) and tool_payload.get("name") == "goodreads_book_lookup":
                    args = tool_payload.get("arguments", {})
                    if debug_trace:
                        print(f"[trace agent={runner_idx}] citation[{
                              idx}] tool_call args: {args}")
                    matches = catalog.find_books(
                        title=args.get("title"),
                        author=args.get("author"),
                        limit=5,
                    )
                    if matches:
                        response = json.dumps(
                            {"result": "FOUND", "metadata": matches[0]}, ensure_ascii=False)
                    else:
                        response = json.dumps(
                            {"result": "NOT_FOUND", "metadata": {}}, ensure_ascii=False)
                else:
                    # Not a valid tool payload; try to salvage JSON from the full response.
                    recovered = _extract_json_snippet(response_str)
                    if recovered is not None:
                        response = json.dumps(recovered, ensure_ascii=False)
                    else:
                        print(f"[agent {
                              runner_idx}] Warning: failed to interpret tool call response; skipping citation {idx}")
                        catalog_queue.put_nowait((catalog_idx, catalog))
                        return idx, None
            catalog_queue.put_nowait((catalog_idx, catalog))

            elapsed = time.perf_counter() - start
            if trace_tool or debug_trace:
                title = citation.get("title") or citation.get(
                    "author") or "unknown citation"
                preview = response[:120] + \
                    ("..." if len(response) > 120 else "")
                print(f"[agent {runner_idx}] Completed '{
                      title}' in {elapsed:.3f}s -> {preview}")

            payload = _extract_json_snippet(response)
            if payload is None:
                print(
                    f"[agent {runner_idx}] Warning: failed to parse response {response}")
                return idx, None

            record = {"citation": citation, "agent_response": payload}
            return idx, record

        tasks = [
            asyncio.create_task(process_single_citation(idx, citation, prompt))
            for idx, (citation, prompt) in enumerate(zip(citations, prompts))
        ]
        results: List[Optional[Dict[str, Any]]] = [None] * len(tasks)
        try:
            for task in asyncio.as_completed(tasks):
                idx, record = await task
                if record is not None:
                    results[idx] = record
                if citation_bar is not None:
                    citation_bar.update(1)
        finally:
            if citation_bar is not None:
                citation_bar.close()

        # Build final graph-friendly JSON
        source_meta = source_goodreads_meta.get(book.goodreads_id, {})
        source_author_ids = []
        if source_meta.get("authors"):
            source_author_ids = [str(a.get("author_id")) for a in source_meta.get(
                "authors", []) if a.get("author_id")]
        elif source_meta.get("author_ids"):
            source_author_ids = [str(a)
                                 for a in source_meta.get("author_ids") if a]
        source_record = {
            "title": source_meta.get("title") or book.title,
            "authors": source_meta.get("author_names_resolved") or [book.author_sort],
            "goodreads_id": book.goodreads_id,
            "author_ids": source_author_ids,
            "description": book.description,
            "goodreads": {
                "book_id": book.goodreads_id,
                "author_ids": source_author_ids,
                "title": source_meta.get("title") or book.title,
                "authors": source_meta.get("author_names_resolved") or [book.author_sort],
                "publication_year": source_meta.get("publication_year"),
            },
            "calibre": {
                "id": book.calibre_id,
                "path": str(book.path),
                "txt_path": str(book.txt_path),
                "epub_path": str(book.epub_path) if book.epub_path else None,
                "description": book.description,
            },
        }

        output_payload: Dict[str, Any] = {
            "source": source_record, "citations": []}
        for record in results:
            if record is None:
                continue
            citation = record.get("citation", {})
            agent_response = record.get("agent_response") or {}
            metadata = {}
            if isinstance(agent_response, dict):
                if agent_response.get("result") == "FOUND" and isinstance(agent_response.get("metadata"), dict):
                    metadata = agent_response["metadata"]
                elif agent_response.get("result") == "NOT_FOUND":
                    metadata = {}
                else:
                    metadata = agent_response

            target_type, target_book_id, target_author_ids, wiki_person = pick_match_type(
                metadata)
            if target_type == "unknown":
                continue  # drop citations without any validated target
            output_payload["citations"].append(
                {
                    "raw": citation,
                    "goodreads_match": metadata,
                    "wikipedia_match": metadata.get("wikipedia_match"),
                    "edge": {
                        "target_type": target_type,
                        "target_book_id": target_book_id,
                        "target_author_ids": target_author_ids,
                        "target_person": wiki_person,
                    },
                }
            )

        final_path.write_text(json.dumps(
            output_payload, indent=2, ensure_ascii=False), encoding="utf-8")


def stage_agent(
    books: Iterable[CalibreBook],
    pre_dir: Path,
    output_dir: Path,
    base_url: str,
    api_key: str,
    model_id: str,
    trace_tool: bool,
    agent_max_workers: int,
    debug_trace: bool = False,
) -> None:
    asyncio.run(
        stage_agent_async(
            books,
            pre_dir,
            output_dir,
            base_url,
            api_key,
            model_id,
            trace_tool,
            agent_max_workers,
            debug_trace=debug_trace,
        )
    )


def derive_output_base(library_dir: Path) -> Path:
    return Path("calibre_outputs") / library_dir.name


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Calibre citation processing pipeline.")
    parser.add_argument("library_dir", type=Path,
                        help="Calibre library directory (contains metadata.db).")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Base output directory. Defaults to ./calibre_outputs/<library_basename>/",
    )
    parser.add_argument(
        "--extract-base-url",
        default="http://localhost:8080/v1",
        help="Base URL for extraction stage (run_single_file).",
    )
    parser.add_argument(
        "--extract-api-key",
        default=os.environ.get("EXTRACT_API_KEY", "test"),
        help="API key for extraction stage.",
    )
    parser.add_argument(
        "--agent-base-url",
        default="http://localhost:8080/v1",
        help="Base URL for Goodreads agent.",
    )
    parser.add_argument(
        "--agent-api-key",
        default=os.environ.get("OPENROUTER_API_KEY") or os.environ.get(
            "OPENAI_API_KEY") or "",
        help="API key for Goodreads agent.",
    )
    parser.add_argument(
        "--extract-model",
        default=EXTRACT_MODEL_ID,
        help="Model identifier/tokenizer to use for extraction.",
    )
    parser.add_argument(
        "--extract-chunk-size",
        type=int,
        default=EXTRACT_CHUNK_SIZE,
        help="Sentences per chunk for extraction stage.",
    )
    parser.add_argument(
        "--extract-max-context-per-request",
        type=int,
        default=EXTRACT_MAX_CONTEXT,
        help="Total context window per extraction request (input + output).",
    )
    parser.add_argument(
        "--agent-model",
        default=AGENT_MODEL_ID,
        help="Model identifier to use for the Goodreads metadata agent.",
    )
    parser.add_argument(
        "--agent-max-workers",
        type=int,
        default=5,
        help="Maximum concurrent Goodreads agent calls (default: 5).",
    )
    parser.add_argument(
        "--agent-trace",
        action="store_true",
        help="Enable verbose tracing of Goodreads tool activity.",
    )
    parser.add_argument(
        "--debug-trace",
        action="store_true",
        help="Verbose logging of prompts, tool calls, and responses for debugging.",
    )
    parser.add_argument(
        "--only-goodreads-ids",
        type=str,
        default=None,
        help="Comma-separated list of Goodreads IDs to process. Others are skipped if present.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.library_dir.exists():
        raise SystemExit(f"Library directory {
                         args.library_dir} does not exist.")
    allowed_ids: Optional[Set[str]] = None
    if args.only_goodreads_ids:
        allowed_ids = {token.strip() for token in args.only_goodreads_ids.replace(
            ",", " ").split() if token.strip()}
        if not allowed_ids:
            print(
                "No valid Goodreads IDs provided to --only-goodreads-ids; processing all eligible books.")
            allowed_ids = None
    books = load_calibre_books(args.library_dir, allowed_ids)
    if not books:
        print("No eligible Calibre books found (need TXT format and Goodreads ID); nothing to do.")
        return

    output_base = args.output_dir or derive_output_base(args.library_dir)
    raw_dir = output_base / "raw_extracted_citations"
    pre_dir = output_base / "preprocessed_extracted_citations"
    final_dir = output_base / "final_citations_metadata_goodreads"

    stage_extract(
        books,
        raw_dir,
        args.extract_base_url,
        args.extract_api_key,
        args.extract_model,
        args.extract_chunk_size,
        args.extract_max_context_per_request,
    )
    stage_preprocess(raw_dir, pre_dir, books)
    stage_agent(
        books,
        pre_dir,
        final_dir,
        args.agent_base_url,
        args.agent_api_key,
        args.agent_model,
        args.agent_trace or args.debug_trace,
        args.agent_max_workers,
        debug_trace=args.debug_trace,
    )

    print(f"Pipeline complete. Outputs at {output_base}")


if __name__ == "__main__":
    main()
