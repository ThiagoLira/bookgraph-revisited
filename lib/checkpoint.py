"""Checkpoint management for resumable citation resolution."""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

logger = logging.getLogger(__name__)


class CheckpointManager:
    """Save/load partial resolution results for crash recovery."""

    def __init__(self, checkpoint_path: Path):
        self.path = checkpoint_path

    def load(self) -> Tuple[List[dict], Set[Tuple[str, str]]]:
        """Load existing checkpoint. Returns (results, processed_keys)."""
        if not self.path.exists():
            return [], set()

        checkpoint = json.loads(self.path.read_text())
        results = checkpoint.get("citations", [])
        keys = {(r["raw"].get("author"), r["raw"].get("title")) for r in results}
        logger.info(f"[checkpoint] Resuming: {len(results)} already processed")
        print(f"[pipeline] Resuming from checkpoint: {len(results)} already processed")
        return results, keys

    def save(self, meta: Dict[str, Any], results: List[dict]):
        """Save checkpoint with partial results."""
        self.path.write_text(json.dumps(
            {"source": meta, "citations": results, "complete": False},
            indent=2, ensure_ascii=False,
        ))
        logger.debug(f"[checkpoint] Saved: {len(results)} citations")

    def remove(self):
        """Remove checkpoint after successful completion."""
        if self.path.exists():
            self.path.unlink()
            logger.info("[checkpoint] Removed after successful completion")
