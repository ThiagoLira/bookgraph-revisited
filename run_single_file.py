#!/usr/bin/env python3
"""CLI for extracting citations from a single text file."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from extract_citations import ExtractionConfig, process_book, write_output


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract citations from a single plaintext book."
    )
    parser.add_argument(
        "input_path",
        type=Path,
        help="Path to the plaintext book file.",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=50,
        help="Maximum number of sentences per chunk.",
    )
    parser.add_argument(
        "--max-concurrency",
        type=int,
        default=4,
        help="Maximum number of concurrent LLM calls.",
    )
    parser.add_argument(
        "--base-url",
        default="http://localhost:8080/v1",
        help="OpenAI-compatible base URL for the local LLM.",
    )
    parser.add_argument(
        "--api-key",
        default="test",
        help="API key for the local server.",
    )
    parser.add_argument(
        "--model",
        default="Qwen/Qwen3-30B-A3B",
        help="Model identifier to include in requests.",
    )
    parser.add_argument(
        "--max-completion-tokens",
        type=int,
        default=1024,
        help="Maximum number of tokens to generate per completion.",
    )
    parser.add_argument(
        "--max-input-tokens",
        type=int,
        default=2048,
        help="Token ceiling for prompts (before completion tokens).",
    )
    parser.add_argument(
        "--tokenizer-name",
        default="Qwen/Qwen3-30B-A3B",
        help="Tokenizer name or path used for token counting.",
    )
    parser.add_argument(
        "--debug-limit",
        type=int,
        help="When set, only process the first N chunks.",
    )
    parser.add_argument(
        "--book-title",
        help="Override the detected book title (default: derived from file name).",
    )
    return parser.parse_args()


def build_progress_reporter() -> tuple[callable, callable]:
    bar_length = 30

    def render(completed: int, total: int) -> None:
        if total <= 0:
            message = "No work to process"
        else:
            filled = int(bar_length * completed / total)
            bar = "#" * filled + "-" * (bar_length - filled)
            message = f"[{bar}] {completed}/{total} chunks"
        print(f"\r{message}", end="", flush=True)
        if total > 0 and completed >= total:
            print()

    def reset() -> None:
        print("\r", end="", flush=True)

    return render, reset


async def run(args: argparse.Namespace):
    config = ExtractionConfig(
        input_path=args.input_path,
        chunk_size=args.chunk_size,
        max_concurrency=args.max_concurrency,
        base_url=args.base_url,
        api_key=args.api_key,
        model=args.model,
        max_completion_tokens=args.max_completion_tokens,
        max_input_tokens=args.max_input_tokens,
        tokenizer_name=args.tokenizer_name,
        book_title=args.book_title or args.input_path.stem,
    )
    progress_callback, reset_output = build_progress_reporter()
    result = await process_book(
        config,
        debug_limit=args.debug_limit,
        progress_callback=progress_callback,
    )
    reset_output()
    repo_root = Path(__file__).resolve().parent
    output_name = f"{args.input_path.name}.json"
    output_path = repo_root / output_name
    write_output(result, output_path)
    print(f"Wrote results to {output_path}", file=sys.stderr)


def main() -> None:
    args = parse_args()
    try:
        asyncio.run(run(args))
    except Exception as exc:  # pragma: no cover - CLI guard
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
