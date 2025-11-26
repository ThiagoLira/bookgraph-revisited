import sys
from pathlib import Path
from typing import List, Dict

import pytest

MODULE_DIR = Path(__file__).resolve().parents[1]
if str(MODULE_DIR) not in sys.path:
    sys.path.insert(0, str(MODULE_DIR))

from test_agent import build_prompts  # type: ignore[attr-defined]
from agent import build_agent  # type: ignore[attr-defined]

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


@pytest.mark.skip("Requires OpenRouter credentials and live LLM")
def test_real_world_cases():
    agent = build_agent(
        model="qwen/qwen3-next-80b-a3b-instruct",
        api_key="",
        base_url="https://openrouter.ai/api/v1",
        books_path="goodreads_data/goodreads_books.json",
        authors_path="goodreads_data/goodreads_book_authors.json",
        verbose=True,
        trace_tool=True,
    )
    prompts = build_prompts(
        REAL_CASES,
        source_title="Test Source",
        source_authors=[],
        source_description=None,
    )
    for case, prompt in zip(REAL_CASES, prompts):
        response = agent.chat(prompt)
        print(f"{case['title']} — {case['author']}: {response}")
