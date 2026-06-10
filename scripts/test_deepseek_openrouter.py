#!/usr/bin/env python3
"""Quick smoke test for DeepSeek v3.2 via OpenRouter.

Tests:
  1. Basic completion (no structured output)
  2. Structured JSON output (response_format=json_schema) — same as pipeline
  3. Reasoning/thinking mode (enable_thinking)

Usage:
    uv run python scripts/test_deepseek_openrouter.py
"""

import asyncio
import copy
import json
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from openai import AsyncOpenAI
from pydantic import BaseModel, Field

load_dotenv()

API_KEY = os.environ.get("OPENROUTER_API_KEY")
BASE_URL = os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
MODEL = "deepseek/deepseek-v3.2"

if not API_KEY:
    print("ERROR: OPENROUTER_API_KEY not set. Add it to .env")
    sys.exit(1)


# ── Pydantic schema (mirrors pipeline's ModelChunkCitations) ──

class BookCitation(BaseModel):
    title: str | None = Field(None, description="Title of the referenced book.")
    author: str = Field(..., description="Author mentioned")
    citation_excerpt: str = Field(..., description="Exact text snippet")
    commentary: str = Field(..., description="Brief third-person commentary")

class ChunkCitations(BaseModel):
    citations: list[BookCitation] = Field(default_factory=list)

SCHEMA = ChunkCitations.model_json_schema(ref_template="#/$defs/{model}")


def response_format():
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "chunk_extraction",
            "strict": True,
            "schema": copy.deepcopy(SCHEMA),
        },
    }


EXCERPT = """In his famous essay, Borges mentions Pierre Menard's attempt to rewrite
Don Quixote by Cervantes word for word. He also references Dante's Divine Comedy
as a supreme literary achievement, and cites Schopenhauer's The World as Will
and Representation as a key influence on his philosophical outlook."""


async def test_basic():
    """Test 1: Plain completion, no structured output."""
    print("\n═══ Test 1: Basic Completion ═══")
    client = AsyncOpenAI(api_key=API_KEY, base_url=BASE_URL)
    t0 = time.time()
    try:
        resp = await client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "Name three books by Jorge Luis Borges. Reply in one sentence."},
            ],
            max_tokens=200,
            temperature=0.0,
            timeout=30.0,
        )
        content = resp.choices[0].message.content
        print(f"  Response: {content}")
        print(f"  Tokens: {resp.usage.prompt_tokens} in / {resp.usage.completion_tokens} out")
        print(f"  Time: {time.time()-t0:.1f}s")
        print("  ✓ PASS")
        return True
    except Exception as e:
        print(f"  ✗ FAIL: {e}")
        return False


async def test_structured_json():
    """Test 2: Structured JSON output with json_schema response_format (pipeline mode)."""
    print("\n═══ Test 2: Structured JSON (json_schema) ═══")
    client = AsyncOpenAI(api_key=API_KEY, base_url=BASE_URL)

    system = (
        "You are an expert research librarian. Extract only citations that refer to "
        "books or book authors mentioned as sources of ideas."
    )
    user = f"""You are extracting book citations from a bounded excerpt.

Return ONLY JSON with this shape:
{{
  "citations": [
    {{
      "title": str | null,
      "author": str,
      "citation_excerpt": str,
      "commentary": str
    }}
  ]
}}

===== BEGIN BOOK EXCERPT =====
{EXCERPT}
===== END BOOK EXCERPT =====
"""

    t0 = time.time()
    try:
        resp = await client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            max_tokens=2048,
            temperature=0.0,
            response_format=response_format(),
            timeout=60.0,
        )
        content = resp.choices[0].message.content
        parsed = json.loads(content)
        citations = parsed.get("citations", [])
        print(f"  Extracted {len(citations)} citations:")
        for c in citations:
            print(f"    - {c.get('author')}: {c.get('title')}")
        print(f"  Finish reason: {resp.choices[0].finish_reason}")
        print(f"  Tokens: {resp.usage.prompt_tokens} in / {resp.usage.completion_tokens} out")
        print(f"  Time: {time.time()-t0:.1f}s")
        # Validate with Pydantic
        validated = ChunkCitations.model_validate(parsed)
        print(f"  Pydantic validation: ✓ ({len(validated.citations)} citations)")
        print("  ✓ PASS")
        return True
    except Exception as e:
        print(f"  ✗ FAIL: {e}")
        return False


async def test_thinking_mode():
    """Test 3: Thinking/reasoning mode (enable_thinking) — same as pipeline."""
    print("\n═══ Test 3: Thinking Mode (enable_thinking) ═══")
    client = AsyncOpenAI(api_key=API_KEY, base_url=BASE_URL)

    system = (
        "You are an expert research librarian. Extract only citations that refer to "
        "books or book authors mentioned as sources of ideas."
    )
    user = f"""You are extracting book citations from a bounded excerpt.

Return ONLY JSON with this shape:
{{
  "citations": [
    {{
      "title": str | null,
      "author": str,
      "citation_excerpt": str,
      "commentary": str
    }}
  ]
}}

===== BEGIN BOOK EXCERPT =====
{EXCERPT}
===== END BOOK EXCERPT =====
"""

    t0 = time.time()
    try:
        resp = await client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            max_tokens=4096,
            temperature=0.0,
            response_format=response_format(),
            extra_body={
                "chat_template_kwargs": {"enable_thinking": True},
            },
            timeout=90.0,
        )
        choice = resp.choices[0]
        content = (choice.message.content or "").strip()
        reasoning = getattr(choice.message, "reasoning_content", None)

        if reasoning:
            preview = reasoning[:200].replace("\n", " ")
            print(f"  Reasoning (preview): {preview}...")

        if content:
            parsed = json.loads(content)
            citations = parsed.get("citations", [])
            print(f"  Extracted {len(citations)} citations:")
            for c in citations:
                print(f"    - {c.get('author')}: {c.get('title')}")
        else:
            print(f"  WARNING: Empty content, finish_reason={choice.finish_reason}")

        print(f"  Finish reason: {choice.finish_reason}")
        print(f"  Tokens: {resp.usage.prompt_tokens} in / {resp.usage.completion_tokens} out")
        print(f"  Time: {time.time()-t0:.1f}s")
        print("  ✓ PASS")
        return True
    except Exception as e:
        print(f"  ✗ FAIL: {e}")
        return False


async def main():
    print(f"Model:    {MODEL}")
    print(f"Base URL: {BASE_URL}")
    print(f"API Key:  {API_KEY[:8]}...{API_KEY[-4:]}")

    results = []
    results.append(("Basic Completion", await test_basic()))
    results.append(("Structured JSON", await test_structured_json()))
    results.append(("Thinking Mode", await test_thinking_mode()))

    print("\n═══ Summary ═══")
    for name, ok in results:
        print(f"  {'✓' if ok else '✗'} {name}")

    all_pass = all(r[1] for r in results)
    print(f"\n{'All tests passed!' if all_pass else 'Some tests FAILED.'}")
    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    asyncio.run(main())
