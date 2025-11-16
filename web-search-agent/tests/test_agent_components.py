"""
Highly verbose unit tests for the Goodreads agent stack.

Each test focuses on a distinct layer:
1. Agent runner behavior without any Goodreads tool wiring.
2. Raw Goodreads lookup tool invocation using synthetic catalog files.
3. Full wiring of `build_agent` so the stubbed FunctionAgent + tool cooperate.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from typing import List, Optional, Sequence

import pytest

MODULE_DIR = Path(__file__).resolve().parents[1]
if str(MODULE_DIR) not in sys.path:
    sys.path.insert(0, str(MODULE_DIR))

from agent import GoodreadsAgentRunner, SYSTEM_PROMPT, build_agent  # type: ignore[attr-defined]
from goodreads_tool import (
    GoodreadsCatalog,
    create_book_lookup_tool,
    create_author_lookup_tool,
)  # type: ignore[attr-defined]


class _ToolLessStubAgent:
    """Minimal stub that mimics the FunctionAgent interface without tools."""

    def __init__(self, scripted_response: str) -> None:
        self.scripted_response = scripted_response
        self.run_calls: List[dict] = []

    def run(
        self,
        user_msg: str,
        chat_history: Optional[Sequence[str]] = None,
        **_: object,
    ):
        """Record inputs and return a coroutine yielding the scripted response."""

        snapshot = {
            "user_msg": user_msg,
            "chat_history": list(chat_history or []),
        }
        self.run_calls.append(snapshot)

        async def _finish():
            return SimpleNamespace(
                response=SimpleNamespace(content=self.scripted_response)
            )

        return _finish()


def test_agent_runner_without_tool_emits_explicit_message() -> None:
    """
    Even without a Goodreads tool, GoodreadsAgentRunner.chat should surface the LLM text.

    This test is intentionally verbose: we capture every input the stub agent saw and
    assert that the synchronous helper returns the exact scripted sentence.
    """

    tool_less_agent = _ToolLessStubAgent(
        scripted_response="FOUND - synthetic baseline without Goodreads cross-check"
    )
    runner = GoodreadsAgentRunner(agent=tool_less_agent)  # type: ignore[arg-type]

    prompt = "Does the imaginary volume 'The Dream of Codes' exist?"
    answer = runner.chat(prompt)

    assert (
        answer == "FOUND - synthetic baseline without Goodreads cross-check"
    ), f"The runner should echo the stubbed answer verbatim, but got {answer!r}"
    assert tool_less_agent.run_calls == [
        {"user_msg": prompt, "chat_history": []}
    ], (
        "Runner.chat must forward the user prompt exactly once with an empty chat history; "
        f"recorded calls: {tool_less_agent.run_calls!r}"
    )


def test_goodreads_tool_returns_matches_for_synthetic_catalog(tmp_path) -> None:
    """
    Exercise the raw FunctionTool against hand-authored JSON lines.

    The catalog is intentionally tiny so we can reason about every field that the tool
    returns; assertions print full context if anything diverges.
    """

    authors_path = tmp_path / "authors.json"
    books_path = tmp_path / "books.json"

    authors = [
        {"author_id": 1, "name": "Ada Lovelace"},
        {"author_id": 2, "name": "Charles Babbage"},
    ]
    books = [
        {
            "book_id": 101,
            "title": "Analytical Engine Memoirs",
            "title_without_series": "Analytical Engine Memoirs",
            "authors": [{"author_id": 1}],
            "publication_year": 1843,
            "publisher": "Compute Press",
            "average_rating": 4.8,
            "ratings_count": 128,
            "text_reviews_count": 32,
            "link": "https://goodreads.example/book/101",
        },
        {
            "book_id": 102,
            "title": "Notes on Airships",
            "title_without_series": "Notes on Airships",
            "authors": [{"author_id": 2}],
            "publication_year": 1860,
        },
    ]
    authors_path.write_text("\n".join(json.dumps(row) for row in authors))
    books_path.write_text("\n".join(json.dumps(row) for row in books))

    tool = create_book_lookup_tool(
        books_path=books_path,
        authors_path=authors_path,
        description="Synthetic Goodreads lookup for unit tests.",
    )

    payload = tool.fn(title="Analytical Engine", author="Lovelace", limit=3)
    assert payload["matches_found"] == 1
    match = payload["matches"][0]
    assert match["title"] == "Analytical Engine Memoirs", (
        "Tool should return the full title from the JSON lines entry; "
        f"raw match object: {match}"
    )
    assert match["authors"] == ["Ada Lovelace"], (
        "Author IDs must resolve to human-readable names. "
        f"Resolved authors: {match['authors']}"
    )


def test_author_lookup_returns_matches(tmp_path) -> None:
    authors_path = tmp_path / "authors.json"
    rows = [
        {"author_id": 1, "name": "William Shakespeare", "works_count": 10},
        {"author_id": 2, "name": "John Milton", "works_count": 5},
    ]
    authors_path.write_text("\n".join(json.dumps(row) for row in rows))

    tool = create_author_lookup_tool(authors_path=authors_path)
    payload = tool.fn(author="Shakespeare", limit=5)
    assert payload["matches_found"] == 1
    assert payload["matches"][0]["name"] == "William Shakespeare"




def _write_linear_catalog(tmp_path: Path, total_rows: int) -> tuple[Path, Path]:
    authors_path = tmp_path / "linear_authors.json"
    books_path = tmp_path / "linear_books.json"
    with authors_path.open("w", encoding="utf-8") as a_fh, books_path.open(
        "w", encoding="utf-8"
    ) as b_fh:
        for idx in range(total_rows):
            author_id = idx + 1
            author_name = f"Author {author_id:05d}"
            a_fh.write(json.dumps({"author_id": author_id, "name": author_name}) + "\n")
            b_fh.write(
                json.dumps(
                    {
                        "book_id": author_id,
                        "title": f"Catalog Book {author_id:05d}",
                        "title_without_series": f"Catalog Book {author_id:05d}",
                        "authors": [{"author_id": author_id}],
                    }
                )
                + "\n"
            )
    return authors_path, books_path


def test_catalog_lookup_timings(tmp_path) -> None:
    """
    Measure how long it takes to find books near the 10th, middle, and last record.

    The mmap-backed catalog should keep all three probes well below ~50ms each even
    though the final probe forces iteration through the entire JSONL file.
    """

    total = 3000
    authors_path, books_path = _write_linear_catalog(tmp_path, total)
    catalog = GoodreadsCatalog(
        books_path=books_path, authors_path=authors_path  # type: ignore[arg-type]
    )

    try:
        targets = {
            "tenth": 10,
            "middle": total // 2,
            "last": total,
        }
        max_expected = 0.2
        timings = {}
        for label, position in targets.items():
            title = f"Catalog Book {position:05d}"
            author = f"Author {position:05d}"
            start = time.perf_counter()
            matches = catalog.find_books(title=title, author=author, limit=1)
            elapsed = time.perf_counter() - start
            timings[label] = elapsed
            print(f"[timing] {label} lookup took {elapsed:.6f}s")
            assert matches, f"Expected at least one match for {title}"
            assert matches[0]["title"] == title
            assert (
                elapsed < max_expected
            ), f"{label} lookup exceeded {max_expected}s (took {elapsed}s)"
    finally:
        catalog.close()



def test_build_agent_uses_tool_and_agent_integration(monkeypatch):
    """
    Patch build_agent internals so we can inspect every argument handed to FunctionAgent.

    The stub agent immediately invokes the synthetic tool to fabricate a FOUND verdict.
    Assertions confirm:
    - system prompt wiring
    - initial tool choice selection
    - that the tool received a call through the stub agent
    """

    import agent as agent_mod  # type: ignore[import-not-found]

    class RecordingBookTool:
        def __init__(self):
            self.metadata = SimpleNamespace(name="goodreads_book_lookup")
            self.calls: list[dict] = []

        def fn(self, title=None, author=None, limit=5):
            self.calls.append({"title": title, "author": author, "limit": limit})
            return {
                "query": {"title": title, "author": author},
                "matches_found": 1,
                "matches": [{"title": title, "authors": [author]}],
            }

    class RecordingAuthorTool:
        def __init__(self):
            self.metadata = SimpleNamespace(name="goodreads_author_lookup")
            self.calls: list[dict] = []

        def fn(self, author=None, limit=5):
            self.calls.append({"author": author, "limit": limit})
            return {
                "query": {"author": author},
                "matches_found": 1,
                "matches": [{"name": author, "author_id": "123"}],
            }

    class StubFunctionAgent:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.run_history: list[dict] = []

        def run(self, user_msg, chat_history=None, **_):
            self.run_history.append(
                {"user_msg": user_msg, "chat_history": list(chat_history or [])}
            )
            tool = self.kwargs["tools"][0]

            async def _finish():
                payload = tool.fn(title="Synthetic Geometry", author="Test Author")
                status = (
                    "FOUND - Synthetic Geometry located"
                    if payload["matches_found"]
                    else "NOT FOUND - Synthetic Geometry missing"
                )
                return SimpleNamespace(response=SimpleNamespace(content=status))

            return _finish()

    recording_book_tool = RecordingBookTool()
    recording_author_tool = RecordingAuthorTool()
    monkeypatch.setattr(agent_mod, "FunctionAgent", StubFunctionAgent)
    monkeypatch.setattr(
        agent_mod, "create_book_lookup_tool", lambda **_: recording_book_tool
    )
    monkeypatch.setattr(
        agent_mod, "create_author_lookup_tool", lambda **_: recording_author_tool
    )
    monkeypatch.setattr(agent_mod, "build_llm", lambda **__: "dummy-llm")

    runner = build_agent(
        model="stub-model",
        api_key="stub-key",
        base_url=None,
        books_path="irrelevant-books-path",
        authors_path="irrelevant-authors-path",
        verbose=True,
        trace_tool=True,
    )

    outcome = runner.chat("Please confirm Synthetic Geometry by Test Author.")
    assert outcome.startswith(
        "FOUND -"
    ), f"Combined flow should yield a FOUND verdict, received: {outcome!r}"

    stub_agent: StubFunctionAgent = runner.agent  # type: ignore[assignment]
    assert (
        stub_agent.kwargs["system_prompt"] == SYSTEM_PROMPT
    ), "build_agent must propagate the curated bibliography system prompt."
    assert stub_agent.kwargs["initial_tool_choice"] is None
    assert [tool.metadata.name for tool in stub_agent.kwargs["tools"]] == [
        "goodreads_book_lookup",
        "goodreads_author_lookup",
    ]
    assert stub_agent.kwargs["llm"] == "dummy-llm", (
        "Custom build_llm patch should feed directly into the FunctionAgent arguments; "
        f"observed kwargs: {stub_agent.kwargs}"
    )
    assert recording_book_tool.calls == [
        {"title": "Synthetic Geometry", "author": "Test Author", "limit": 5}
    ], (
        "The stub agent should have invoked the synthetic tool exactly once with the "
        f"scripted query; recorded tool calls: {recording_book_tool.calls}"
    )
