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
from typing import TYPE_CHECKING, Optional, Sequence, List, Dict

from llama_index.core.agent import FunctionAgent
from llama_index.llms.openai import OpenAI
from pydantic import BaseModel, Field
from typing import Literal

if TYPE_CHECKING:  # pragma: no cover
    from llama_index.core.llms import ChatMessage, LLM

CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in os.sys.path:  # pragma: no cover
    os.sys.path.insert(0, str(CURRENT_DIR))

from goodreads_tool import (
    BOOKS_DB_PATH,
    SQLiteGoodreadsCatalog,
    create_book_lookup_tool,
    create_author_lookup_tool,
)

# llama.cpp REST API expects legacy tool message structure where `content` is a string.
# LlamaIndex recently switched to the new OpenAI Responses schema (object-based),
# which triggers parsing errors on llama-server. Patch the conversion helper so
# tool outputs are serialized as plain strings again.
try:
    from llama_index.llms.openai import utils as _openai_utils

    _orig_to_openai_message_dict = _openai_utils.to_openai_message_dict

    def _legacy_tool_message_adapter(message, *args, **kwargs):
        result = _orig_to_openai_message_dict(message, *args, **kwargs)
        if isinstance(result, dict) and result.get("type") == "function_call_output":
            return {
                "role": "tool",
                "content": result.get("output") or "",
                "tool_call_id": result.get("call_id"),
            }
        return result

    _openai_utils.to_openai_message_dict = _legacy_tool_message_adapter
except Exception:
    # If the import fails we simply skip the compatibility shim.
    pass



class BookMetadata(BaseModel):
    type: Literal["book"] = "book"
    title: str = Field(..., description="Book title as listed on Goodreads.")
    title_without_series: Optional[str] = Field(
        None, description="Title stripped of series information when available."
    )
    authors: List[str] = Field(default_factory=list, description="List of author names.")
    publication_year: Optional[int] = None
    publication_month: Optional[int] = None
    publication_day: Optional[int] = None
    book_id: Optional[str] = Field(None, description="Goodreads book_id.")
    num_pages: Optional[int] = None
    publisher: Optional[str] = None
    ratings_count: Optional[int] = None
    average_rating: Optional[float] = None


class AuthorMetadata(BaseModel):
    type: Literal["author"] = "author"
    author_id: str = Field(..., description="Goodreads author_id.")
    name: str = Field(..., description="Canonical author name.")
    ratings_count: Optional[int] = None


SYSTEM_PROMPT = (
    "You verify whether bibliographic entries exist on Goodreads.\n"
    "• Normalize search queries aggressively: strip punctuation, accents, edition notes, "
    "and try multiple variations (e.g., swapped word order, removing subtitles) until you "
    "exhaust reasonable options.\n"
    "• When a citation includes a title, call `goodreads_book_lookup` first to gather "
    "candidate editions, then compare the returned authors to the citation.\n"
    "• When only an author is supplied, call `goodreads_author_lookup` to disambiguate "
    "the identity before concluding.\n"
    "• Respond with a JSON object describing the best Goodreads match. Include fields from "
    "`BookMetadata` (title, title_without_series, authors, publication_year, publication_month, "
    "publication_day, book_id, num_pages, optional extras) or `AuthorMetadata` "
    "(author_id, name, ratings_count). If nothing matches, respond with an empty JSON object `{}`."
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
    verbose: bool = False

    async def _chat_async(
        self,
        prompt: str,
        chat_history: Optional[Sequence["ChatMessage"]] = None,
    ) -> str:
        if self.verbose:
            print(f"[GoodreadsAgent] Prompt:\n{prompt}\n{'-' * 40}")
        handler = self.agent.run(
            user_msg=prompt,
            chat_history=list(chat_history or []),
        )
        if self.verbose:
            print("[GoodreadsAgent] Waiting for LLM response...")
        agent_output = await handler
        response = agent_output.response.content or ""
        if self.verbose:
            print(f"[GoodreadsAgent] Response:\n{response}\n{'=' * 40}")
        return response

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
    memory_catalog = SQLiteGoodreadsCatalog(
        db_path=BOOKS_DB_PATH,
        trace=trace_tool,
    )
    book_tool = create_book_lookup_tool(
        description=(
            "Use this when you need to confirm a book exists on Goodreads by title "
            "or author."
        ),
        db_path=memory_catalog.db_path,
        catalog=memory_catalog,
        trace=trace_tool,
    )
    author_tool = create_author_lookup_tool(
        authors_path=authors_path,
        description="Use this when you only have the author name and must disambiguate.",
        trace=trace_tool,
    )
    agent = FunctionAgent(
        name="goodreads_validator",
        description="Validates bibliography entries with Goodreads metadata.",
        system_prompt=SYSTEM_PROMPT,
        tools=[book_tool, author_tool],
        llm=llm,
        verbose=verbose,
        streaming=False,
        allow_parallel_tool_calls=False,
        initial_tool_choice=None,
    )
    return GoodreadsAgentRunner(agent=agent, verbose=verbose)


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
