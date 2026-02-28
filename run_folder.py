#!/usr/bin/env python3
"""CLI for processing all files in a folder using the standard BookPipeline."""

from __future__ import annotations

import argparse
import asyncio
import logging
import re
import sys
from datetime import datetime
from pathlib import Path

from lib.cli_common import (
    ensure_repo_root, add_llm_args, add_pipeline_args,
    build_config_from_args, setup_logging, REPO_ROOT,
)

ensure_repo_root()

from lib.main_pipeline import BookPipeline


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Process every file in a directory using BookPipeline."
    )
    parser.add_argument("input_dir", type=Path, help="Directory containing plaintext book files.")
    parser.add_argument("--output-dir", type=Path, default=None,
                        help="Directory to save outputs (default: creates timestamped run folder).")
    add_llm_args(parser)
    add_pipeline_args(parser)
    parser.add_argument("--pattern", default="*.txt",
                        help="Glob pattern to select text files (default: *.txt).")
    parser.add_argument("--workers", type=int, default=1,
                        help="Number of files to process in parallel.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be processed without running.")
    return parser.parse_args()


async def process_file(pipeline: BookPipeline, input_path: Path, output_dir: Path):
    logger = logging.getLogger(__name__)
    logger.info(f"Starting: {input_path.name}")
    print(f"Starting: {input_path.name}")

    match = re.search(r'_(\d+)\.txt$', input_path.name)
    extracted_id = None
    clean_title = input_path.stem

    if match:
        extracted_id = match.group(1)
        clean_title = input_path.name[:match.start()].replace("_", " ")
    else:
        logger.warning(f"No ID in filename for '{input_path.name}'. Attempting DB lookup...")
        from lib.bibliography_agent.bibliography_tool import SQLiteGoodreadsCatalog
        catalog = SQLiteGoodreadsCatalog(pipeline.config.books_db, trace=False)
        heuristic_title = input_path.stem.replace("_", " ").split("__")[0]
        matches = catalog.find_books(title=heuristic_title, limit=1)
        if matches:
            best = matches[0]
            extracted_id = best['book_id']
            clean_title = best['title']
            print(f"  [LOOKUP] Found match: {clean_title} (ID: {extracted_id})")
        else:
            print(f"  [FAIL] Could not find book in DB for '{heuristic_title}'. Using slug as ID.")
            clean_title = heuristic_title

    source_metadata = {
        "title": clean_title,
        "authors": [],
        "goodreads_id": extracted_id,
        "calibre_id": None,
    }
    final_book_id = str(extracted_id) if extracted_id else input_path.stem

    try:
        await pipeline.run_file(
            input_text_path=input_path,
            output_dir=output_dir,
            source_metadata=source_metadata,
            book_id=final_book_id,
        )
        logger.info(f"Finished: {input_path.name} -> {final_book_id}.json")
        print(f"Finished: {input_path.name} -> {final_book_id}.json")
    except Exception as e:
        logger.error(f"Error processing {input_path.name}: {e}", exc_info=True)
        print(f"Error processing {input_path.name}: {e}")
        import traceback
        traceback.print_exc()


async def run(args: argparse.Namespace):
    input_dir = args.input_dir
    if not input_dir.is_dir():
        potential_path = REPO_ROOT / "input_books" / "libraries" / input_dir.name
        if potential_path.is_dir():
            print(f"Found library at: {potential_path}")
            input_dir = potential_path
        else:
            print(f"Error: Input directory {input_dir} does not exist.")
            sys.exit(1)

    files = sorted(p for p in input_dir.glob(args.pattern) if p.is_file())
    if not files:
        print("No matching files found.")
        sys.exit(1)

    output_dir = args.output_dir or (
        REPO_ROOT / "outputs" / "folder_runs" / f"run_{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    )

    if args.dry_run:
        print(f"[DRY-RUN] Would process {len(files)} files:")
        for f in files[:10]:
            print(f"  - {f.name}")
        if len(files) > 10:
            print(f"  ... and {len(files) - 10} more")
        print(f"[DRY-RUN] Output directory would be: {output_dir}")
        return

    setup_logging(output_dir, verbose=args.verbose)
    logger = logging.getLogger(__name__)

    config = build_config_from_args(args)
    pipeline = BookPipeline(config)

    logger.info(f"Processing {len(files)} files from {args.input_dir}")
    print(f"Processing {len(files)} files from {args.input_dir}")
    print(f"Output Directory: {output_dir}")
    print(f"Model: {args.model}")

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
