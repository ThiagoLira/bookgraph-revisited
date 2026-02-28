#!/usr/bin/env python3
"""CLI for processing a single text file using the standard BookPipeline."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from lib.cli_common import ensure_repo_root, add_llm_args, add_pipeline_args, build_config_from_args, REPO_ROOT

ensure_repo_root()

from lib.main_pipeline import BookPipeline


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Process a single plaintext book using BookPipeline."
    )
    parser.add_argument("input_path", type=Path, help="Path to the plaintext book file.")
    parser.add_argument("--output-dir", type=Path, default=Path("outputs") / "single_runs",
                        help="Directory to save outputs.")
    add_llm_args(parser)
    add_pipeline_args(parser)
    parser.add_argument("--book-title", default=None, help="Override book title metadata.")
    parser.add_argument("--author", default=None, help="Override author metadata.")
    parser.add_argument("--goodreads-id", default="manual_run", help="Override Goodreads ID.")
    return parser.parse_args()


async def run(args: argparse.Namespace):
    input_path = args.input_path
    if not input_path.exists():
        potential_path = REPO_ROOT / "input_books" / "one_off_books" / input_path.name
        if potential_path.exists():
            print(f"Found input file at: {potential_path}")
            input_path = potential_path
        else:
            print(f"Error: Input file {input_path} not found.")
            sys.exit(1)

    config = build_config_from_args(args)
    pipeline = BookPipeline(config)

    source_metadata = {
        "title": args.book_title or args.input_path.stem,
        "authors": [args.author] if args.author else [],
        "goodreads_id": args.goodreads_id,
        "calibre_id": None,
    }

    print(f"Processing: {args.input_path}")
    print(f"Output Dir: {args.output_dir}")
    print(f"Model: {args.model}")

    try:
        await pipeline.run_file(
            input_text_path=input_path,
            output_dir=args.output_dir,
            source_metadata=source_metadata,
            book_id=args.goodreads_id,
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
