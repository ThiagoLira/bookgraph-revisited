#!/usr/bin/env python3
"""
Run only the Goodreads metadata agent (stage 3 of process_citations_pipeline.py)
against preprocessed citation JSON files.

Inputs:
- Preprocessed citation JSON files (stage 2 outputs).
- OpenAI-compatible endpoint for the Goodreads agent.

Outputs:
- One JSONL per input file with `{citation, agent_response}` records.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

# Ensure imports work when launched from within this experiment folder.
REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.append(str(REPO_ROOT))

from lib.bibliography_agent.agent import build_agent
from lib.bibliography_agent.goodreads_tool import SQLiteGoodreadsCatalog
from lib.bibliography_agent.test_agent import build_prompts

try:
    from tqdm import tqdm  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    tqdm = None


def progress_iter(iterable: Iterable[Path], **kwargs: object) -> Iterable[Path]:
    if tqdm is None:
        return iterable
    return tqdm(iterable, **kwargs)


def find_preprocessed_files(folder: Path, pattern: str = "*.json") -> List[Path]:
    return sorted(p for p in folder.glob(pattern) if p.suffix.lower() == ".json")


def build_agent_runner(
    base_url: str,
    api_key: str,
    model_id: str,
    trace_tool: bool,
    wiki_people_path: str = str(REPO_ROOT / "goodreads_data" / "wiki_people_index.db"),
) -> "GoodreadsAgentRunner":
    return build_agent(
        model=model_id,
        api_key=api_key,
        base_url=base_url,
        books_path=str(REPO_ROOT / "goodreads_data" / "goodreads_books.json"),
        authors_path=str(REPO_ROOT / "goodreads_data" / "goodreads_book_authors.json"),
        wiki_people_path=wiki_people_path,
        verbose=trace_tool,
        trace_tool=trace_tool,
    )


async def run_agent_stage(
    pre_dir: Path,
    output_dir: Path,
    pattern: str,
    base_url: str,
    api_key: str,
    model_id: str,
    trace_tool: bool,
    agent_max_workers: int,
) -> None:
    if agent_max_workers < 1:
        raise ValueError("--agent-max-workers must be at least 1.")

    pre_files = find_preprocessed_files(pre_dir, pattern)
    if not pre_files:
        print(f"No preprocessed files found under {pre_dir} (pattern: {pattern}).")
        return

    output_dir.mkdir(parents=True, exist_ok=True)

    runners = [build_agent_runner(base_url, api_key, model_id, trace_tool) for _ in range(agent_max_workers)]
    runner_queue: asyncio.Queue["GoodreadsAgentRunner"] = asyncio.Queue()
    for runner in runners:
        runner_queue.put_nowait(runner)

    catalogs = [SQLiteGoodreadsCatalog(trace=trace_tool) for _ in range(agent_max_workers)]
    catalog_queue: asyncio.Queue[SQLiteGoodreadsCatalog] = asyncio.Queue()
    for catalog in catalogs:
        catalog_queue.put_nowait(catalog)

    iterator = progress_iter(
        pre_files,
        desc="Stage 3/3: Goodreads agent",
        unit="file",
    )

    async def process_single_citation(
        idx: int,
        citation: Dict[str, Any],
        prompt: str,
    ) -> tuple[int, Optional[str]]:
        runner = await runner_queue.get()
        catalog = await catalog_queue.get()
        try:
            start = time.perf_counter()
            response = await runner.query(prompt)
        finally:
            runner_queue.put_nowait(runner)

        try:
            response_str = response.strip()
            if response_str.startswith("<tool_call>"):
                try:
                    tool_payload = json.loads(response_str.split(">", 1)[1].strip())
                    if tool_payload.get("name") == "goodreads_book_lookup":
                        args = tool_payload.get("arguments", {})
                        matches = catalog.find_books(
                            title=args.get("title"),
                            author=args.get("author"),
                            limit=5,
                        )
                        if matches:
                            response = json.dumps(
                                {"result": "FOUND", "metadata": matches[0]},
                                ensure_ascii=False,
                            )
                        else:
                            response = json.dumps(
                                {"result": "NOT_FOUND", "metadata": {}},
                                ensure_ascii=False,
                            )
                except Exception as exc:  # pragma: no cover - debug aid
                    print(f"[agent] Warning: failed to interpret tool call {response_str}: {exc}")
        finally:
            catalog_queue.put_nowait(catalog)

        elapsed = time.perf_counter() - start
        if trace_tool:
            title = citation.get("title") or citation.get("author") or "unknown citation"
            preview = response[:120] + ("..." if len(response) > 120 else "")
            print(f"[agent] Completed '{title}' in {elapsed:.3f}s -> {preview}")

        try:
            payload = json.loads(response)
        except Exception as exc:  # pragma: no cover - debug aid
            print(f"[agent] Warning: failed to parse response {response}: {exc}")
            return idx, None

        record = {"citation": citation, "agent_response": payload}
        return idx, json.dumps(record, ensure_ascii=False)

    for pre_file in iterator:
        final_path = output_dir / f"{pre_file.stem}.jsonl"
        if final_path.exists():
            print(f"[agent] Skip {pre_file.name} (cached).")
            continue
        if not pre_file.exists():
            print(f"[agent] Missing preprocessed JSON for {pre_file.name}, skipping.")
            continue

        data = json.loads(pre_file.read_text(encoding="utf-8"))
        citations = data.get("citations", [])
        prompts = build_prompts(
            citations,
            source_title=txt.stem,
            source_authors=[],
            source_description=None,
        )
        print(f"[agent] Processing {len(citations)} citations for {pre_file.name}")

        if not citations:
            final_path.write_text("", encoding="utf-8")
            continue

        citation_bar = None
        if tqdm is not None:
            citation_bar = tqdm(
                total=len(citations),
                desc=f"  citations for {pre_file.name}",
                unit="citation",
                leave=False,
            )

        try:
            tasks = [
                asyncio.create_task(process_single_citation(idx, citation, prompt))
                for idx, (citation, prompt) in enumerate(zip(citations, prompts))
            ]
            results: List[Optional[str]] = [None] * len(tasks)
            for task in asyncio.as_completed(tasks):
                idx, record_line = await task
                if record_line is not None:
                    results[idx] = record_line
                if citation_bar is not None:
                    citation_bar.update(1)
            kept = 0
            with final_path.open("w", encoding="utf-8") as out:
                for record_line in results:
                    if record_line is None:
                        continue
                    try:
                        payload = json.loads(record_line)
                    except Exception:
                        continue
                    agent_resp = payload.get("agent_response") or {}
                    meta = {}
                    if isinstance(agent_resp, dict):
                        if agent_resp.get("result") == "FOUND" and isinstance(agent_resp.get("metadata"), dict):
                            meta = agent_resp["metadata"]
                        elif agent_resp.get("result") == "NOT_FOUND":
                            meta = {}
                        else:
                            meta = agent_resp
                    has_book = bool(meta.get("book_id"))
                    author_ids = meta.get("author_ids") or []
                    if not has_book and not author_ids:
                        continue  # drop entries without a resolved Goodreads target
                    out.write(json.dumps(payload, ensure_ascii=False) + "\n")
                    kept += 1
            if kept == 0:
                print(f"[agent] Warning: no validated citations kept for {pre_file.name}")
        finally:
            if citation_bar is not None:
                citation_bar.close()


def parse_args() -> argparse.Namespace:
    base_dir = Path(__file__).resolve().parent
    default_pre_dir = base_dir / "inputs" / "preprocessed_extracted_citations"
    default_output_dir = base_dir / "outputs" / "final_citations_metadata_goodreads"

    parser = argparse.ArgumentParser(
        description="Run only the Goodreads agent stage against preprocessed citation JSON files.",
    )
    parser.add_argument(
        "--pre-dir",
        type=Path,
        default=default_pre_dir,
        help=f"Directory containing preprocessed citations (default: {default_pre_dir}).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=default_output_dir,
        help=f"Directory to write agent outputs (default: {default_output_dir}).",
    )
    parser.add_argument(
        "--pattern",
        default="*.json",
        help="Glob pattern for preprocessed citation files (default: *.json).",
    )
    parser.add_argument(
        "--agent-base-url",
        default=os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
        help="Base URL for Goodreads agent.",
    )
    parser.add_argument(
        "--agent-api-key",
        default=os.environ.get("OPENROUTER_API_KEY") or os.environ.get("OPENAI_API_KEY") or "",
        help="API key for Goodreads agent.",
    )
    parser.add_argument(
        "--agent-model",
        default="qwen/qwen3-next-80b-a3b-instruct",
        help="Model identifier to use for the Goodreads metadata agent.",
    )
    parser.add_argument(
        "--agent-max-workers",
        type=int,
        default=5,
        help="Maximum concurrent Goodreads agent calls (default: 5).",
    )
    parser.add_argument(
        "--agent-trace",
        action="store_true",
        help="Enable verbose tracing of Goodreads tool activity.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.pre_dir.exists():
        raise SystemExit(f"Input directory {args.pre_dir} does not exist.")

    asyncio.run(
        run_agent_stage(
            args.pre_dir,
            args.output_dir,
            args.pattern,
            args.agent_base_url,
            args.agent_api_key,
            args.agent_model,
            args.agent_trace,
            args.agent_max_workers,
        )
    )


if __name__ == "__main__":
    main()
