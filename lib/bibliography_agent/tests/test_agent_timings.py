import sys
import time
from pathlib import Path

import pytest

MODULE_DIR = Path(__file__).resolve().parents[1]
if str(MODULE_DIR) not in sys.path:
    sys.path.insert(0, str(MODULE_DIR))

from agent import GoodreadsAgentRunner  # type: ignore[attr-defined]
from bibliography_agent.bibliography_tool import GoodreadsCatalog  # type: ignore[attr-defined]

DATASET_EXISTS = Path("goodreads_data/goodreads_books.json").exists()
TARGETS = [
    ("tenth", "The Devil's Notebook", "Anton Szandor LaVey"),
    ("middle", "El Espejo de mi Alma", "Tannia E. Ortiz-Lopes"),
    (
        "last",
        "The Spanish Duke's Virgin Bride (Innocent Mistress, Virgin Bride, #1) (Harlequin Presents, #2679)",
        "Chantelle Shaw",
    ),
]


@pytest.mark.skipif(not DATASET_EXISTS, reason="Requires the full Goodreads dataset.")
@pytest.mark.parametrize("label,title,author", TARGETS)
def test_lookup_timing(label: str, title: str, author: str) -> None:
    catalog = GoodreadsCatalog()  # type: ignore[arg-type]
    try:
        start = time.perf_counter()
        matches = catalog.find_books(title=title, author=author, limit=1)
        elapsed = time.perf_counter() - start
        print(f"[timing] {label} lookup took {elapsed:.6f}s for {title}")
        assert matches, f"{label} lookup failed for {title!r}"
        returned_title = (matches[0]["title"] or "").lower()
        assert returned_title == title.lower(), (
            f"{label} lookup returned {returned_title!r} instead of {title!r}"
        )
    finally:
        catalog.close()
