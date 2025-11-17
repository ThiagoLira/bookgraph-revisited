#!/usr/bin/env python3
"""
Run a hardcoded suite of "real world" Goodreads checks and record agent outputs.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Dict, List

from dotenv import load_dotenv
import os

MODULE_DIR = Path(__file__).resolve().parent
if str(MODULE_DIR) not in sys.path:
    sys.path.insert(0, str(MODULE_DIR))

from agent import build_agent  # type: ignore[attr-defined]
from test_agent import build_prompts  # type: ignore[attr-defined]

REAL_CASES: List[Dict[str, str]] = [
    {"title": "A Trick to Catch the Old One", "author": "Middleton"},
    {"title": "As You Like It", "author": "Shakespeare"},
    {"title": "All's Well That Ends Well", "author": "Shakespeare"},
    {"title": "The Plain Dealer", "author": "Wycherley"},
    {"title": "Tartuffe", "author": "Molière"},
    {"title": "The Malcontent", "author": "Marston"},
    {"title": "Peace", "author": "Aristophanes"},
    {"title": "The Beggar's Opera", "author": "John Gay"},
    {"title": "Heartbreak House", "author": "Shaw"},
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run hardcoded Goodreads agent tests and save responses."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(f"real_agent_tests_{int(time.time())}.json"),
        help="Output JSON file (default: timestamped in CWD).",
    )
    parser.add_argument(
        "--model",
        default="qwen/qwen3-next-80b-a3b-instruct",
        help="Model identifier for the agent.",
    )
    parser.add_argument(
        "--base-url",
        default="https://openrouter.ai/api/v1",
        help="OpenAI-compatible endpoint.",
    )
    parser.add_argument(
        "--books-path",
        default="goodreads_data/goodreads_books.json",
        help="Path to goodreads_books.json",
    )
    parser.add_argument(
        "--authors-path",
        default="goodreads_data/goodreads_book_authors.json",
        help="Path to goodreads_book_authors.json",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable agent verbose logging.",
    )
    parser.add_argument(
        "--trace-tool",
        action="store_true",
        help="Print every Goodreads lookup from the tool.",
    )
    parser.add_argument(
        "--api-key",
        default=None,
        help="API key override (default: env OPENROUTER_API_KEY/OPENAI_API_KEY).",
    )
    return parser.parse_args()


def main() -> None:
    load_dotenv()
    args = parse_args()
    api_key = args.api_key or os.environ.get("OPENROUTER_API_KEY") or os.environ.get("OPENAI_API_KEY") or ""
    if not api_key:
        raise SystemExit("Missing API key: set OPENROUTER_API_KEY/OPENAI_API_KEY or pass --api-key.")
    agent = build_agent(
        model=args.model,
        api_key=api_key,
        base_url=args.base_url,
        books_path=args.books_path,
        authors_path=args.authors_path,
        verbose=args.verbose,
        trace_tool=args.trace_tool,
    )
    prompts = build_prompts(REAL_CASES)
    results = []
    for case, prompt in zip(REAL_CASES, prompts):
        response = agent.chat(prompt)
        results.append(
            {
                "title": case["title"],
                "author": case["author"],
                "response": response,
            }
        )
        print(f"{case['title']} — {case['author']}: {response}")
    payload = {
        "model": args.model,
        "base_url": args.base_url,
        "cases": results,
        "generated_at": int(time.time()),
    }
    args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    print(f"Wrote results to {args.output}")


if __name__ == "__main__":
    main()
