#!/usr/bin/env python3
"""
CLI for processing a single text file using the standard BookPipeline.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

# Fix: Ensure repo root is in python path
REPO_ROOT = Path(__file__).resolve().parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Attempt to load .env manually if python-dotenv is not installed or just to be safe
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from lib.main_pipeline import BookPipeline, PipelineConfig


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Process a single plaintext book using BookPipeline."
    )
    parser.add_argument(
        "input_path",
        type=Path,
        help="Path to the plaintext book file.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("outputs") / "single_runs",
        help="Directory to save outputs.",
    )
    
    # LLM / Extraction Config
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=50,
        help="Maximum number of sentences per chunk (extraction).",
    )
    parser.add_argument(
        "--max-context-per-request",
        type=int,
        default=6144,
        help="Context window for extraction.",
    )
    parser.add_argument(
        "--base-url",
        default="https://openrouter.ai/api/v1",
        help="Base URL for LLM API (Extraction & Agent).",
    )
    parser.add_argument(
        "--api-key",
        default=os.environ.get("OPENROUTER_API_KEY", ""),
        help="API Key.",
    )
    parser.add_argument(
        "--model",
        default="deepseek/deepseek-v3.2",
        help="Model ID.",
    )

    # Optional Overrides
    parser.add_argument(
        "--book-title",
        default=None,
        help="Override book title metadata.",
    )
    parser.add_argument(
        "--author",
        default=None,
        help="Override author metadata.",
    )
    parser.add_argument(
        "--goodreads-id",
        default="manual_run",
        help="Override Goodreads ID.",
    )
    parser.add_argument(
        "--agent-concurrency",
        type=int,
        default=20,
        help="Max concurrent agent workflows for citation resolution (default: 20).",
    )
    parser.add_argument(
        "--extract-concurrency",
        type=int,
        default=20,
        help="Max concurrent extraction requests (default: 20).",
    )
    parser.add_argument(
        "--force-llm-queries",
        action="store_true",
        help="Force LLM-based query generation for all citations (bypass deterministic).",
    )

    return parser.parse_args()


async def run(args: argparse.Namespace):
    input_path = args.input_path
    if not input_path.exists():
        # Check in input_books/one_off_books
        repo_root = Path(__file__).resolve().parent
        potential_path = repo_root / "input_books" / "one_off_books" / input_path.name
        if potential_path.exists():
             print(f"Found input file at: {potential_path}")
             input_path = potential_path
        else:
             print(f"Error: Input file {input_path} not found.")
             sys.exit(1)

    # Initialize Pipeline
    config = PipelineConfig(
        extract_base_url=args.base_url,
        extract_api_key=args.api_key,
        extract_model=args.model,
        extract_chunk_size=args.chunk_size,
        extract_max_context=args.max_context_per_request,
        
        agent_base_url=args.base_url,
        agent_api_key=args.api_key,
        agent_model=args.model,
        agent_concurrency=args.agent_concurrency,
        extract_concurrency=args.extract_concurrency,

        # Default DB paths relative to repo root
        books_db=str(REPO_ROOT / "datasets/books_index.db"),
        authors_json=str(REPO_ROOT / "datasets/goodreads_book_authors.json"),
        wiki_db=str(REPO_ROOT / "datasets/wiki_people_index.db"),
        
        # Enrichment Paths (Consolidated in datasets/)
        dates_json=str(REPO_ROOT / "datasets/original_publication_dates.json"),
        author_meta_json=str(REPO_ROOT / "datasets/authors_metadata.json"),
        # legacy_dates_json is now the same as dates_json, so we can omit it or pass None
        legacy_dates_json=None,
        
        debug_trace=True,
        force_llm_queries=args.force_llm_queries,
    )
    
    pipeline = BookPipeline(config)
    
    # Build minimal source metadata
    source_metadata = {
        "title": args.book_title or args.input_path.stem,
        "authors": [args.author] if args.author else [],
        "goodreads_id": args.goodreads_id,
        "calibre_id": None
    }
    
    print(f"Processing: {args.input_path}")
    print(f"Output Dir: {args.output_dir}")
    print(f"Model: {args.model}")
    
    try:
        await pipeline.run_file(
            input_text_path=args.input_path,
            output_dir=args.output_dir,
            source_metadata=source_metadata,
            book_id=args.goodreads_id
        )
        print("Done.")
    except Exception as e:
        print(f"Error processing file: {e}")
        import traceback
        traceback.print_exc()

def main() -> None:
    args = parse_args()
    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    main()
