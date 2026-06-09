"""Shared CLI utilities for pipeline entry points."""

import argparse
import logging
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def ensure_repo_root():
    """Ensure repo root is in sys.path and .env is loaded."""
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass


def add_llm_args(parser: argparse.ArgumentParser):
    """Add standard LLM arguments to a parser."""
    parser.add_argument(
        "--base-url",
        default="https://openrouter.ai/api/v1",
        help="Base URL for OpenRouter API.",
    )
    parser.add_argument(
        "--api-key",
        default=os.environ.get("OPENROUTER_API_KEY", ""),
        help="OpenRouter API key.",
    )
    parser.add_argument(
        "--model",
        default="deepseek/deepseek-v4-flash",
        help="Model ID.",
    )


def add_pipeline_args(parser: argparse.ArgumentParser):
    """Add standard pipeline arguments to a parser."""
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=50,
        help="Maximum number of sentences per chunk (extraction).",
    )
    parser.add_argument(
        "--max-context-per-request",
        type=int,
        default=6144,
        help="Context window for extraction.",
    )
    parser.add_argument(
        "--agent-concurrency",
        type=int,
        default=20,
        help="Max concurrent agent workflows for citation resolution.",
    )
    parser.add_argument(
        "--extract-concurrency",
        type=int,
        default=20,
        help="Max concurrent extraction requests.",
    )
    parser.add_argument(
        "--force-llm-queries",
        action="store_true",
        help="Force LLM-based query generation for all citations (bypass deterministic).",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose debug logging.",
    )


def build_config_from_args(args: argparse.Namespace):
    """Build PipelineConfig from parsed CLI args."""
    from lib.main_pipeline import PipelineConfig
    from lib.llm_client import LLMConfig

    llm_config = LLMConfig(
        base_url=args.base_url,
        api_key=args.api_key,
        model=args.model,
    )

    return PipelineConfig(
        extract_llm=llm_config,
        agent_llm=llm_config,
        extract_chunk_size=getattr(args, "chunk_size", 50),
        extract_max_context=getattr(args, "max_context_per_request", 6144),
        agent_concurrency=getattr(args, "agent_concurrency", 20),
        extract_concurrency=getattr(args, "extract_concurrency", 20),
        books_db=str(REPO_ROOT / "datasets/books_index.db"),
        authors_json=str(REPO_ROOT / "datasets/goodreads_book_authors.json"),
        wiki_db=str(REPO_ROOT / "datasets/wiki_people_index.db"),
        dates_json=str(REPO_ROOT / "datasets/original_publication_dates.json"),
        author_meta_json=str(REPO_ROOT / "datasets/authors_metadata.json"),
        debug_trace=getattr(args, "verbose", False) or getattr(args, "debug_trace", False),
        force_llm_queries=getattr(args, "force_llm_queries", False),
    )


def setup_logging(output_dir: Path, verbose: bool = False) -> Path:
    """Configure logging to both file and console. Returns log file path."""
    log_file = output_dir / "pipeline.log"
    output_dir.mkdir(parents=True, exist_ok=True)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    root_logger.handlers = []

    # File handler — captures everything
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    root_logger.addHandler(file_handler)

    # Console handler — INFO+ (or DEBUG if verbose)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG if verbose else logging.INFO)
    console_handler.setFormatter(logging.Formatter("%(message)s"))
    root_logger.addHandler(console_handler)

    # Our modules
    for mod in ("lib.main_pipeline", "lib.metadata_enricher",
                "lib.bibliography_agent.citation_workflow"):
        logging.getLogger(mod).setLevel(logging.DEBUG)

    # Quiet noisy libs
    for mod in ("httpx", "httpcore", "urllib3", "asyncio", "pyppeteer",
                "pyppeteer.connection"):
        logging.getLogger(mod).setLevel(logging.WARNING)

    logging.info(f"Logging initialized. Log file: {log_file}")
    return log_file
