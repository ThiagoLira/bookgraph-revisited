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
from lib.bibliography_agent.citation_workflow import CitationWorkflow

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


def load_goodreads_metadata(book_ids: Set[str], db_path: str = "goodreads_data/books_index.db") -> Dict[str, Any]:
    """Load metadata for a set of Goodreads book IDs from the SQLite index."""
    if not book_ids:
        return {}
    
    if not os.path.exists(db_path):
        print(f"[pipeline] Warning: Books DB not found at {db_path}, cannot load source metadata.")
        return {}

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    placeholders = ",".join("?" for _ in book_ids)
    query = f"SELECT data FROM books WHERE book_id IN ({placeholders})"
    
    results = {}
    try:
        cur.execute(query, list(book_ids))
        for row in cur.fetchall():
            try:
                data = json.loads(row["data"])
                results[str(data["book_id"])] = data
            except (json.JSONDecodeError, KeyError):
                continue
    except Exception as e:
        print(f"[pipeline] Error loading Goodreads metadata: {e}")
    finally:
        conn.close()
        
    return results

async def run_extraction(
    txt_path: Path,
    output_path: Path,
    base_url: str,
    api_key: str,
    model_id: str,
    chunk_size: int,
    max_context: int,
    progress_callback: Optional[ProgressCallback] = None,
    verbose: bool = False,
) -> None:
    config = ExtractionConfig(
        input_path=txt_path,
        chunk_size=chunk_size,
        max_concurrency=EXTRACT_MAX_CONCURRENCY,
        max_context_per_request=max_context,
        max_completion_tokens=EXTRACT_MAX_COMPLETION,
        verbose=verbose,
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
    debug_trace: bool = False,
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
                        base_url, api_key, model_id, chunk_size, max_context, verbose=debug_trace))
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
                    verbose=debug_trace,
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


from lib.bibliography_agent.llm_utils import build_llm

async def stage_workflow_async(
    books: Iterable[CalibreBook],
    pre_dir: Path,
    output_dir: Path,
    books_db: str,
    authors_db: str,
    wiki_db: str,
    base_url: str,
    api_key: str,
    model_id: str,
    debug_trace: bool = False,
    max_concurrency: int = 10,
) -> None:
    books = list(books)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Prefetch source Goodreads metadata for source nodes
    book_ids_needed: Set[str] = {b.goodreads_id for b in books}
    source_goodreads_meta = load_goodreads_metadata(book_ids_needed)

    # Initialize LLM
    llm = build_llm(model=model_id, api_key=api_key, base_url=base_url)

    # Initialize workflow
    # We use a single workflow instance (or one per book if we want to reset state, 
    # but CitationWorkflow is stateless per run call).
    workflow = CitationWorkflow(
        books_db_path=books_db,
        authors_path=authors_db,
        wiki_people_path=wiki_db,
        llm=llm,
        verbose=debug_trace,
        timeout=150.0,
    )

    sem = asyncio.Semaphore(max_concurrency)

    async def process_citation_safe(citation: Dict[str, Any], bar: Optional[tqdm]) -> Dict[str, Any]:
        async with sem:
            try:
                # Enforce a strict timeout on the workflow execution
                result = await asyncio.wait_for(workflow.run(citation=citation), timeout=160.0)
                if bar:
                    bar.update(1)
                return {
                    "citation": citation,
                    "result": result
                }
            except asyncio.TimeoutError:
                print(f"[workflow] Timeout processing citation {citation}", flush=True)
                if bar:
                    bar.update(1)
                return {
                    "citation": citation,
                    "error": "Timeout"
                }
            except Exception as e:
                print(f"[workflow] Error processing citation {citation}: {e}")
                if bar:
                    bar.update(1)
                return {
                    "citation": citation,
                    "error": str(e)
                }

    for book in progress_iter_items(books, desc="Stage 3/3: Citation Workflow", unit="book"):
        pre_path = pre_dir / f"{book.goodreads_id}.json"
        final_path = output_dir / f"{book.goodreads_id}.json"
        
        if final_path.exists():
            print(f"[workflow] Skip {book.title} (cached).")
            continue
        if not pre_path.exists():
            print(f"[workflow] Missing preprocessed JSON for {book.title}, skipping.")
            continue

        data = json.loads(pre_path.read_text(encoding="utf-8"))
        citations = data.get("citations", [])
        print(f"[workflow] Processing {len(citations)} citations for {book.title}")

        # Build source record
        source_meta = source_goodreads_meta.get(book.goodreads_id, {})
        source_author_ids = []
        if source_meta.get("authors"):
            source_author_ids = [str(a.get("author_id")) for a in source_meta.get("authors", []) if a.get("author_id")]
        elif source_meta.get("author_ids"):
            source_author_ids = [str(a) for a in source_meta.get("author_ids") if a]
            
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

        output_payload: Dict[str, Any] = {"source": source_record, "citations": []}

        if not citations:
            final_path.write_text(json.dumps(output_payload, indent=2, ensure_ascii=False), encoding="utf-8")
            continue

        # Process citations
        citation_bar = None
        if tqdm is not None:
            citation_bar = tqdm(total=len(citations), desc=f"  citations for {book.title}", unit="citation", leave=False)

        # Prepare tasks, truncating excerpts to avoid context explosion
        tasks = []
        for c in citations:
            # Create a copy to avoid modifying the original data which might be used elsewhere (though here it's fine)
            c_input = c.copy()
            if "excerpts" in c_input and isinstance(c_input["excerpts"], list):
                # Keep top 5 excerpts (longest? random? first?)
                # First 5 is fine as they are likely from the beginning of the book or random if not sorted.
                # Preprocess doesn't sort excerpts, just appends.
                c_input["excerpts"] = c_input["excerpts"][:5]
            
            tasks.append(process_citation_safe(c_input, citation_bar))

        results = await asyncio.gather(*tasks)
        
        if citation_bar:
            citation_bar.close()

        for res in results:
            if "error" in res:
                continue
            
            citation = res["citation"]
            result = res["result"]
            
            # Format output based on result
            match_type = result.get("match_type", "unknown")
            metadata = result.get("metadata", {})
            
            if match_type == "not_found" or match_type == "unknown":
                continue

            # Construct edge data
            target_book_id = metadata.get("book_id")
            target_author_ids = []
            if metadata.get("author_id"):
                target_author_ids.append(str(metadata.get("author_id")))
            elif metadata.get("author_ids"):
                target_author_ids = [str(a) for a in metadata.get("author_ids")]
            
            wiki_person = metadata.get("wikipedia_match")

            output_payload["citations"].append({
                "raw": citation,
                "goodreads_match": metadata,
                "wikipedia_match": wiki_person,
                "edge": {
                    "target_type": match_type,
                    "target_book_id": target_book_id,
                    "target_author_ids": target_author_ids,
                    "target_person": wiki_person,
                }
            })

        final_path.write_text(json.dumps(output_payload, indent=2, ensure_ascii=False), encoding="utf-8")


def stage_workflow(
    books: Iterable[CalibreBook],
    pre_dir: Path,
    output_dir: Path,
    books_db: str,
    authors_db: str,
    wiki_db: str,
    base_url: str,
    api_key: str,
    model_id: str,
    debug_trace: bool = False,
    max_concurrency: int = 10,
) -> None:
    asyncio.run(stage_workflow_async(
        books, pre_dir, output_dir, books_db, authors_db, wiki_db, 
        base_url, api_key, model_id, debug_trace, max_concurrency
    ))


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
        "--books-db",
        default="goodreads_data/books_index.db",
        help="Path to Goodreads books SQLite index.",
    )
    parser.add_argument(
        "--authors-json",
        default="goodreads_data/goodreads_book_authors.json",
        help="Path to Goodreads authors JSON.",
    )
    parser.add_argument(
        "--wiki-db",
        default="goodreads_data/wiki_people_index.db",
        help="Path to Wikipedia people SQLite index.",
    )
    parser.add_argument(
        "--only-goodreads-ids",
        type=str,
        default=None,
        help="Comma-separated list of Goodreads IDs to process. Others are skipped if present.",
    )
    parser.add_argument(
        "--extract-model",
        default=EXTRACT_MODEL_ID,
        help="Model ID for extraction stage.",
    )
    parser.add_argument(
        "--extract-chunk-size",
        type=int,
        default=EXTRACT_CHUNK_SIZE,
        help="Chunk size for extraction.",
    )
    parser.add_argument(
        "--extract-max-context-per-request",
        type=int,
        default=EXTRACT_MAX_CONTEXT,
        help="Max context tokens per request.",
    )
    parser.add_argument(
        "--agent-base-url",
        default=os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
        help="Base URL for bibliography agent.",
    )
    parser.add_argument(
        "--agent-api-key",
        default=os.environ.get("OPENROUTER_API_KEY", ""),
        help="API key for bibliography agent.",
    )
    parser.add_argument(
        "--agent-model",
        default="qwen/qwen3-next-80b-a3b-instruct",
        help="Model ID for bibliography agent.",
    )
    parser.add_argument(
        "--debug-trace",
        action="store_true",
        help="Enable verbose debug tracing.",
    )
    parser.add_argument(
        "--agent-max-concurrency",
        type=int,
        default=10,
        help="Max concurrent agent workflows.",
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
        debug_trace=args.debug_trace,
    )
    stage_preprocess(raw_dir, pre_dir, books)
    stage_workflow(
        books,
        pre_dir,
        final_dir,
        args.books_db,
        args.authors_json,
        args.wiki_db,
        args.agent_base_url,
        args.agent_api_key,
        args.agent_model,
        debug_trace=args.debug_trace,
        max_concurrency=args.agent_max_concurrency,
    )

    print(f"Pipeline complete. Outputs at {output_base}")


if __name__ == "__main__":
    main()
