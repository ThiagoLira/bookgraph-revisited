"""
Smoke test that feeds the Goodreads agent five citation prompts derived from
`books/susan_sample.txt`.

Example:
    uv run python web-search-agent/test_agent.py --limit 5
"""

from __future__ import annotations

import asyncio
import argparse
import json
import os
from pathlib import Path
from typing import Dict, List

from dotenv import load_dotenv
load_dotenv()


CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in os.sys.path:  # pragma: no cover
    os.sys.path.insert(0, str(CURRENT_DIR))

from agent import build_agent

DEFAULT_MODEL = "qwen/qwen3-next-80b-a3b-instruct"
DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_API_KEY = os.environ.get("OPENROUTER_API_KEY") or os.environ.get("OPENAI_API_KEY")


def load_citation_pairs(json_path: Path, limit: int) -> List[Dict[str, str]]:
    data = json.loads(json_path.read_text())
    pairs: List[Dict[str, str]] = []
    for chunk in data.get("chunks", []):
        for citation in chunk.get("citations", []):
            title = citation.get("title")
            author = citation.get("author")
            if not title or not author:
                continue
            entry = {"title": title, "author": author}
            if entry in pairs:
                continue
            pairs.append(entry)
            if len(pairs) >= limit:
                return pairs
    raise ValueError(
        f"Only found {len(pairs)} usable citations in {json_path}; "
        f"reduce --limit or regenerate the citation JSON."
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Test the Goodreads metadata agent.")
    parser.add_argument(
        "--citations-json",
        default=str(Path("susan_sample.txt.json")),
        help="Path to the JSON output generated from books/susan_sample.txt",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="Number of citation prompts to test.",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help="Model identifier (defaults to the run_openrouter_single.sh value).",
    )
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help="OpenAI-compatible base URL (defaults to OpenRouter).",
    )
    parser.add_argument(
        "--api-key",
        default=DEFAULT_API_KEY or "",
        help="API key for the OpenAI-compatible endpoint.",
    )
    parser.add_argument(
        "--books-path",
        default=str(Path("goodreads_data/goodreads_books.json")),
        help="Path to goodreads_books.json (or .json.gz)",
    )
    parser.add_argument(
        "--authors-path",
        default=str(Path("goodreads_data/goodreads_book_authors.json")),
        help="Path to goodreads_book_authors.json (or .json.gz)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose agent traces.",
    )
    parser.add_argument(
        "--trace-tool",
        action="store_true",
        help="Print every Goodreads lookup call (title/author/limit) for debugging.",
    )
    return parser.parse_args()


def build_prompts(citations: List[Dict[str, str]]) -> List[str]:
    prompts = []
    for citation in citations:
        title = citation["title"]
        author = citation["author"]
        prompts.append(
            (
                "You are validating bibliography metadata. "
                "Use the Goodreads search tool to check whether the specified book exists. "
                "Return a JSON object describing the matching Goodreads metadata. "
                "If no book is found, return an empty JSON object `{}`.\n"
                f'Book title: "{title}"\n'
                f"Author: {author}"
            )
        )
    return prompts


async def main() -> None:
    args = parse_args()
    if not args.api_key:
        raise SystemExit(
            "Missing API key. Pass --api-key or export OPENROUTER_API_KEY / OPENAI_API_KEY."
        )

    citations_path = Path(args.citations_json)
    citations = load_citation_pairs(citations_path, args.limit)
    prompts = build_prompts(citations)

    agent = build_agent(
        model=args.model,
        api_key=args.api_key,
        base_url=args.base_url.strip(),
        books_path=args.books_path,
        authors_path=args.authors_path,
        verbose=args.verbose,
        trace_tool=args.trace_tool,
    )

    for idx, (citation, prompt) in enumerate(zip(citations, prompts), start=1):
        print(f"=== Test #{idx}: {citation['title']} — {citation['author']} ===")
        response = await agent.query(prompt)
        print(response)
        print("=" * 72)


if __name__ == "__main__":
    asyncio.run(main())
