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
from bibliography_tool import (
    BOOKS_DB_PATH,
    SQLiteGoodreadsCatalog,
    SQLiteWikiPeopleIndex,
    GoodreadsAuthorCatalog,
    create_book_lookup_tool,
    create_author_lookup_tool,
    create_wiki_people_lookup_tool,
)

import argparse
import asyncio
import json
import os
import re
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
    authors: List[str] = Field(
        default_factory=list, description="List of author names.")
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
    wikipedia_page_id: Optional[int] = Field(
        None, description="Wikipedia page_id when resolved via wikipedia_person_lookup."
    )
    wikipedia_title: Optional[str] = Field(
        None, description="Wikipedia title for the matched person."
    )
    wikipedia_infoboxes: List[str] = Field(
        default_factory=list, description="Infobox roles from Wikipedia."
    )
    wikipedia_categories: List[str] = Field(
        default_factory=list, description="Categories from Wikipedia to help disambiguate domain/role."
    )


SYSTEM_PROMPT = (
    "You are BibliographyAgent. Validate book/author citations using Goodreads IDs and Wikipedia "
    "person metadata to disambiguate identities.\n\n"
    "### AUTHOR-ONLY CITATIONS WORKFLOW (CRITICAL)\n"
    "1) Call `wikipedia_person_lookup` first to disambiguate the person by name and role. "
    "Use categories/infoboxes to judge whether this matches the source book's domain. "
    "2) If a good Wikipedia match is found, then call `goodreads_author_lookup` to attach an author_id. "
    "If Goodreads has no match, return Wikipedia metadata alone. If Wikipedia has no satisfactory match, "
    "fall back to Goodreads author lookup after exhausting Wikipedia.\n"
    "3) If multiple people share the name, pick the one whose roles/categories align with the source book; "
    "otherwise return {}.\n"
    "4) Output JSON should include Wikipedia metadata (title, page_id, categories/infobox hints) and "
    "Goodreads author_id when available. Do not include prose.\n\n"
    "### TOOL USAGE PROTOCOL (CRITICAL)\n"
    "1. SINGLE FIELD ONLY: The `goodreads_book_lookup` tool fails if you provide both "
    "title and author. You must call it with title='...' (and author=None) OR "
    "author='...' (and title=None). NEVER BOTH.\n"
    "2. TITLE FIRST STRATEGY: Always search by Title first. If that fails, search by Author.\n"
    "3. VERIFICATION: The tool returns a list of candidates. You must inspect this list "
    "internally to find the one that matches your citation's author.\n\n"
    "### SEARCH HEURISTICS\n"
    "The database search is strict. You must clean inputs aggressively before calling tools:\n"
    "- Subtitles: REMOVE them. Search 'How to Do Nothing', NOT 'How to Do Nothing: Resisting...'\n"
    "- Punctuation: REMOVE commas/colons. Search 'Bartleby the Scrivener', NOT 'Bartleby, the Scrivener'.\n"
    "- Initials: If an author has initials (e.g., 'B. F. Skinner'), search by surname only "
    "('Skinner') or full name without dots ('Burrhus Skinner') if known. Dots confuse the index.\n\n"
    "### OUTPUT FORMAT\n"
    "Return a JSON object describing the best match (using BookMetadata or AuthorMetadata fields). "
    "If absolutely no match is found after trying simplified variations, return {}.\n"
    "Output STRICTLY as tool calls or raw JSON. Do not include explanations or prose."
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
    authors_path: Path = Path("goodreads_data/goodreads_book_authors.json")
    wiki_people_path: Path = Path("goodreads_data/wiki_people_index.db")

    @staticmethod
    def _normalize_response(raw: str) -> str:
        """
        Ensure downstream stages always receive JSON or a tool_call envelope.

        - Pass through tool calls unchanged (run_agent_stage3 handles them).
        - Try direct JSON parse; if that fails, try fenced ```json``` blocks,
          then a loose first {...} match.
        - Fall back to a structured error payload instead of raising.
        """
        cleaned = raw.strip()
        if not cleaned:
            return json.dumps({})
        if cleaned.startswith("<tool_call>"):
            return cleaned
        try:
            json.loads(cleaned)
            return cleaned
        except Exception:
            pass

        fence = re.search(
            r"```json\s*(\{.*?\})\s*```", cleaned, flags=re.DOTALL)
        if fence:
            snippet = fence.group(1).strip()
            try:
                json.loads(snippet)
                return snippet
            except Exception:
                pass

        brace = re.search(r"(\{.*\})", cleaned, flags=re.DOTALL)
        if brace:
            snippet = brace.group(1)
            try:
                json.loads(snippet)
                return snippet
            except Exception:
                pass

        return json.dumps({"result": "UNPARSEABLE", "raw_response": cleaned}, ensure_ascii=False)

    async def _chat_async(
        self,
        prompt: str,
        chat_history: Optional[Sequence["ChatMessage"]] = None,
    ) -> str:
        detour = self._maybe_handle_author_only(prompt)
        if detour is not None:
            return detour
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
        normalized = self._normalize_response(response)
        if self.verbose:
            print(f"[GoodreadsAgent] Response (raw):\n{response}\n{'-' * 40}")
            print(f"[GoodreadsAgent] Response (normalized):\n{
                  normalized}\n{'=' * 40}")
        return normalized

    def _maybe_handle_author_only(self, prompt: str) -> Optional[str]:
        title = None
        author = None
        for line in prompt.splitlines():
            if line.lower().startswith("book title"):
                title = line.split(":", 1)[1].strip().strip('"')
            if line.lower().startswith("author"):
                author = line.split(":", 1)[1].strip()
        if not author or author.lower() in {"<not provided>", "unknown", "null"}:
            return None
        if title and title.lower() not in {"<not provided>", "unknown", "null", ""}:
            return None

        # Author-only path: use Wikipedia people index then Goodreads authors.
        wiki = SQLiteWikiPeopleIndex(
            db_path=self.wiki_people_path, trace=self.verbose)
        wiki_matches = wiki.find_people(author, limit=3)
        best_wiki = wiki_matches[0] if wiki_matches else None
        gr_catalog = GoodreadsAuthorCatalog(authors_path=self.authors_path)
        gr_matches = gr_catalog.find_authors(author, limit=3)
        author_id = gr_matches[0]["author_id"] if gr_matches else None
        payload = {
            "author": author,
            "author_id": author_id,
            "wikipedia_matches": wiki_matches,
            "wikipedia_match": best_wiki,
            "wikipedia_page_id": best_wiki.get("page_id") if best_wiki else None,
            "goodreads_matches": gr_matches,
        }
        return json.dumps(payload, ensure_ascii=False)

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
    wiki_people_path: str = "goodreads_data/wiki_people_index.db",
    verbose: bool,
    trace_tool: bool = False,
    system_prompt: Optional[str] = None,
) -> GoodreadsAgentRunner:
    """Construct a function-calling agent with our Goodreads lookup tool."""
    llm = build_llm(model=model, api_key=api_key, base_url=base_url)
    memory_catalog = SQLiteGoodreadsCatalog(
        db_path=BOOKS_DB_PATH,
        trace=trace_tool,
    )
    book_tool = create_book_lookup_tool(
        description=(
            "Search for books. IMPORTANT: provide EITHER a 'title' OR an 'author', "
            "but NEVER both in the same call. To search by title, leave author null. "
            "To search by author, leave title null."
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
    wiki_people_tool = create_wiki_people_lookup_tool(
        description="Look up people on Wikipedia by name to disambiguate identities and roles.",
        db_path=wiki_people_path,
        trace=trace_tool,
    )
    prompt = system_prompt or SYSTEM_PROMPT
    agent = FunctionAgent(
        name="goodreads_validator",
        description="Validates bibliography entries with Goodreads metadata.",
        system_prompt=prompt,
        tools=[book_tool, author_tool, wiki_people_tool],
        llm=llm,
        verbose=verbose,
        streaming=False,
        allow_parallel_tool_calls=False,
        initial_tool_choice=None,
    )
    return GoodreadsAgentRunner(
        agent=agent,
        verbose=verbose,
        authors_path=Path(authors_path),
        wiki_people_path=Path(wiki_people_path),
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Query Goodreads metadata via an agent.")
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
        default=os.environ.get("OPENROUTER_BASE_URL",
                               "https://openrouter.ai/api/v1"),
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
        "--wiki-people-path",
        default="goodreads_data/wiki_people_index.db",
        help="Path to wiki_people_index.db",
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
        wiki_people_path=args.wiki_people_path,
        verbose=args.verbose,
        trace_tool=args.trace_tool,
    )

    content = runner.chat(args.prompt)
    print(content)


if __name__ == "__main__":
    main()
