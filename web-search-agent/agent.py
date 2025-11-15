"""
LlamaIndex-powered agent that can verify Goodreads metadata via a custom tool.

Usage
-----
    uv run python web-search-agent/agent.py --prompt "Does 'The Hobbit' by Tolkien exist?"

Environment
-----------
- API key pulled from OPENROUTER_API_KEY or OPENAI_API_KEY unless --api-key provided.
- Default base URL targets OpenRouter, but you can pass any OpenAI-compatible host.
"""

from __future__ import annotations

import argparse
import asyncio
import os
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Optional, Sequence

from llama_index.core.agent import FunctionAgent
from llama_index.llms.openai import OpenAI

if TYPE_CHECKING:  # pragma: no cover
    from llama_index.core.llms import ChatMessage, LLM

CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in os.sys.path:  # pragma: no cover
    os.sys.path.insert(0, str(CURRENT_DIR))

from goodreads_tool import create_book_lookup_tool

SYSTEM_PROMPT = (
    "You verify whether bibliographic entries exist on Goodreads. Prefer a staged "
    "strategy: first search by title only, inspect authors, then (if still ambiguous) "
    "search under the author name alone to find likely matches. If neither lookup yields "
    "a confident pairing, try simple variations (e.g., stripping accents, swapping word "
    "order) before concluding failure. Respond strictly with either "
    "'FOUND - <short reason>' or 'NOT FOUND - <short reason>'."
)


def build_llm(model: str, api_key: str, base_url: Optional[str]) -> LLM:
    """
    Create an OpenAI-compatible LLM wrapper for LlamaIndex.

    Prefers `OpenAILike` so we can target OpenRouter or any self-hosted endpoint.
    Falls back to the builtin OpenAI wrapper if base_url is omitted.
    """
    if not base_url:
        return OpenAI(model=model, api_key=api_key)

    try:
        from llama_index.llms.openai_like import OpenAILike

        return OpenAILike(
            model=model,
            api_key=api_key,
            api_base=base_url,
            is_chat_model=True,
            is_function_calling_model=True,
        )
    except ModuleNotFoundError:
        return OpenAI(model=model, api_key=api_key, base_url=base_url)


@dataclass
class GoodreadsAgentRunner:
    agent: FunctionAgent

    async def _chat_async(
        self,
        prompt: str,
        chat_history: Optional[Sequence["ChatMessage"]] = None,
    ) -> str:
        handler = self.agent.run(
            user_msg=prompt,
            chat_history=list(chat_history or []),
        )
        agent_output = await handler
        return agent_output.response.content or ""

    async def query(
        self,
        prompt: str,
        chat_history: Optional[Sequence["ChatMessage"]] = None,
    ) -> str:
        return await self._chat_async(prompt, chat_history)

    def chat(
        self,
        prompt: str,
        chat_history: Optional[Sequence["ChatMessage"]] = None,
    ) -> str:
        return asyncio.run(self._chat_async(prompt, chat_history))


def build_agent(
    *,
    model: str,
    api_key: str,
    base_url: Optional[str],
    books_path: str,
    authors_path: str,
    verbose: bool,
    trace_tool: bool = False,
) -> GoodreadsAgentRunner:
    """Construct a function-calling agent with our Goodreads lookup tool."""
    llm = build_llm(model=model, api_key=api_key, base_url=base_url)
    search_tool = create_book_lookup_tool(
        books_path=books_path,
        authors_path=authors_path,
        description=(
            "Use this when you need to confirm a book exists on Goodreads by title "
            "and/or author."
        ),
        trace=trace_tool,
    )
    agent = FunctionAgent(
        name="goodreads_validator",
        description="Validates bibliography entries with Goodreads metadata.",
        system_prompt=SYSTEM_PROMPT,
        tools=[search_tool],
        llm=llm,
        verbose=verbose,
        streaming=False,
        allow_parallel_tool_calls=False,
        initial_tool_choice=search_tool.metadata.name,
    )
    return GoodreadsAgentRunner(agent=agent)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Query Goodreads metadata via an agent.")
    parser.add_argument(
        "--prompt",
        required=True,
        help="User question for the agent, e.g. 'Does The Hobbit by Tolkien exist?'",
    )
    parser.add_argument(
        "--model",
        default="gpt-4o-mini",
        help="OpenAI-compatible chat model identifier.",
    )
    parser.add_argument(
        "--api-key",
        default=os.environ.get("OPENROUTER_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
        or "",
        help="API key for the OpenAI-compatible endpoint (defaults to env vars).",
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
        help="OpenAI-compatible base URL. Leave blank to use official OpenAI.",
    )
    parser.add_argument(
        "--books-path",
        default="goodreads_data/goodreads_books.json",
        help="Path to goodreads_books.json (or .json.gz)",
    )
    parser.add_argument(
        "--authors-path",
        default="goodreads_data/goodreads_book_authors.json",
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


def main() -> None:
    args = parse_args()
    if not args.api_key:
        raise SystemExit(
            "Missing API key. Provide --api-key or set OPENROUTER_API_KEY / OPENAI_API_KEY."
        )

    base_url = args.base_url.strip() or None

    runner = build_agent(
        model=args.model,
        api_key=args.api_key,
        base_url=base_url,
        books_path=args.books_path,
        authors_path=args.authors_path,
        verbose=args.verbose,
        trace_tool=args.trace_tool,
    )

    content = runner.chat(args.prompt)
    print(content)


if __name__ == "__main__":
    main()
