#!/usr/bin/env python3
"""
CLI for processing all files in a folder using the standard BookPipeline.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path

# Fix: Ensure repo root is in python path
REPO_ROOT = Path(__file__).resolve().parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Attempt to load .env manually
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from lib.main_pipeline import BookPipeline, PipelineConfig


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Process every *file in a directory using BookPipeline."
    )
    parser.add_argument(
        "input_dir",
        type=Path,
        help="Directory containing plaintext book files.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Directory to save outputs (default: creates numbered run folder).",
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
        default="qwen/qwen3-next-80b-a3b-instruct",
        help="Model ID.",
    )
    parser.add_argument(
        "--pattern",
        default="*.txt",
        help="Glob pattern to select text files (default: *.txt).",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Number of files to process in parallel (be careful with API limits).",
    )

    return parser.parse_args()


async def process_file(pipeline: BookPipeline, input_path: Path, output_dir: Path):
    print(f"Starting: {input_path.name}")
    source_metadata = {
        "title": input_path.stem,
        "authors": [], # Cannot infer from filename easily
        "goodreads_id": None,
        "calibre_id": None
    }
    try:
        await pipeline.run_file(
            input_text_path=input_path,
            output_dir=output_dir,
            source_metadata=source_metadata,
            book_id=f"folder_run_{input_path.stem}"
        )
        print(f"Finished: {input_path.name}")
    except Exception as e:
        print(f"Error processing {input_path.name}: {e}")
        import traceback
        traceback.print_exc()


async def run(args: argparse.Namespace):
    if not args.input_dir.is_dir():
        print(f"Error: {args.input_dir} is not a directory.")
        sys.exit(1)

    files = sorted(path for path in args.input_dir.glob(args.pattern) if path.is_file())
    if not files:
        print("No matching files found.")
        sys.exit(1)

    # Output Dir
    if args.output_dir:
        output_dir = args.output_dir
    else:
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        output_dir = REPO_ROOT / "outputs" / "folder_runs" / f"run_{timestamp}"
    
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
        
        books_db=str(REPO_ROOT / "datasets/books_index.db"),
        authors_json=str(REPO_ROOT / "datasets/goodreads_book_authors.json"),
        wiki_db=str(REPO_ROOT / "datasets/wiki_people_index.db"),
        
        debug_trace=True
    )
    
    pipeline = BookPipeline(config)
    
    print(f"Processing {len(files)} files from {args.input_dir}")
    print(f"Output Directory: {output_dir}")
    print(f"Model: {args.model}")
    print(f"Parallel Workers: {args.workers}")

    # Semaphore for file-level concurrency
    sem = asyncio.Semaphore(args.workers)
    
    async def worker(fpath):
        async with sem:
            await process_file(pipeline, fpath, output_dir)

    await asyncio.gather(*(worker(f) for f in files))
    
    print("All done.")


def main() -> None:
    args = parse_args()
    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    main()
