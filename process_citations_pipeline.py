#!/usr/bin/env python3
"""
Full citation pipeline:
1. Extract raw citations from each .txt file under an input directory.
2. Preprocess/deduplicate the extracted JSON.
3. Query the Goodreads agent to attach structured metadata and emit a JSONL file.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from lib.extract_citations import (
    ExtractionConfig,
    ProgressCallback,
    process_book,
    write_output,
)
from preprocess_citations import preprocess as preprocess_citations
from lib.bibliography_agent.agent import build_agent
from lib.bibliography_agent.test_agent import build_prompts

try:
    from tqdm import tqdm  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    tqdm = None


def progress_iter(iterable: Iterable[Path], **kwargs: object) -> Iterable[Path]:
    if tqdm is None:
        return iterable
    return tqdm(iterable, **kwargs)

# ---------- Tunable defaults ----------

EXTRACT_CHUNK_SIZE = 50
EXTRACT_MAX_CONCURRENCY = 20
EXTRACT_MAX_CONTEXT = 6144
EXTRACT_MAX_COMPLETION = 2048
EXTRACT_MODEL_ID = "Qwen/Qwen3-30B-A3B"

AGENT_MODEL_ID = "qwen/qwen3-next-80b-a3b-instruct"


def find_txt_files(folder: Path, pattern: str = "*.txt") -> List[Path]:
    return sorted(p for p in folder.glob(pattern) if p.suffix.lower() == ".txt")


async def run_extraction(
    txt_path: Path,
    output_path: Path,
    base_url: str,
    api_key: str,
    model_id: str,
    progress_callback: Optional[ProgressCallback] = None,
) -> None:
    config = ExtractionConfig(
        input_path=txt_path,
        chunk_size=EXTRACT_CHUNK_SIZE,
        max_concurrency=EXTRACT_MAX_CONCURRENCY,
        max_context_per_request=EXTRACT_MAX_CONTEXT,
        max_completion_tokens=EXTRACT_MAX_COMPLETION,
        base_url=base_url,
        api_key=api_key,
        model=model_id,
        tokenizer_name=model_id,
    )
    result = await process_book(config, progress_callback=progress_callback)
    write_output(result, output_path)


def stage_extract(
    txt_files: Iterable[Path],
    output_dir: Path,
    base_url: str,
    api_key: str,
    model_id: str,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    iterator = progress_iter(
        txt_files,
        desc="Stage 1/3: Extraction",
        unit="book",
    )
    for txt in iterator:
        out_path = output_dir / f"{txt.stem}.json"
        if out_path.exists():
            print(f"[extract] Skip {txt.name} (cached).")
            continue
        print(f"[extract] Processing {txt.name} -> {out_path}")
        if tqdm is None:
            asyncio.run(run_extraction(txt, out_path, base_url, api_key, model_id))
            continue
        chunk_bar = tqdm(
            desc=f"  chunks for {txt.name}",
            unit="chunk",
            leave=False,
        )

        def on_chunk_progress(done: int, total: int) -> None:
            if chunk_bar.total != total:
                chunk_bar.total = total
            chunk_bar.n = done
            chunk_bar.refresh()

        try:
            asyncio.run(
                run_extraction(
                    txt,
                    out_path,
                    base_url,
                    api_key,
                    model_id,
                    progress_callback=on_chunk_progress,
                )
            )
        finally:
            chunk_bar.close()


def stage_preprocess(raw_dir: Path, output_dir: Path, txt_files: Iterable[Path]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for txt in txt_files:
        raw_path = raw_dir / f"{txt.stem}.json"
        pre_path = output_dir / f"{txt.stem}.json"
        if pre_path.exists():
            print(f"[preprocess] Skip {txt.name} (cached).")
            continue
        if not raw_path.exists():
            print(f"[preprocess] Missing raw JSON for {txt.name}, skipping.")
            continue
        print(f"[preprocess] {raw_path} -> {pre_path}")
        processed = preprocess_citations(raw_path)
        pre_path.write_text(json.dumps(processed, indent=2, ensure_ascii=False))


def build_agent_runner(
    base_url: str,
    api_key: str,
    model_id: str,
    trace_tool: bool,
    wiki_people_path: str = "goodreads_data/wiki_people_index.db",
) -> "GoodreadsAgentRunner":
    return build_agent(
        model=model_id,
        api_key=api_key,
        base_url=base_url,
        books_path="goodreads_data/goodreads_books.json",
        authors_path="goodreads_data/goodreads_book_authors.json",
        wiki_people_path=wiki_people_path,
        verbose=trace_tool,
        trace_tool=trace_tool,
    )


async def stage_agent_async(
    pre_dir: Path,
    output_dir: Path,
    txt_files: Iterable[Path],
    base_url: str,
    api_key: str,
    model_id: str,
    trace_tool: bool,
    agent_max_workers: int,
) -> None:
    from lib.goodreads_agent.goodreads_tool import SQLiteGoodreadsCatalog

    if agent_max_workers < 1:
        raise ValueError("--agent-max-workers must be at least 1.")

    output_dir.mkdir(parents=True, exist_ok=True)
    runners = [build_agent_runner(base_url, api_key, model_id, trace_tool) for _ in range(agent_max_workers)]
    runner_queue: asyncio.Queue["GoodreadsAgentRunner"] = asyncio.Queue()
    for runner in runners:
        runner_queue.put_nowait(runner)

    # Create one catalog per worker to avoid SQLite thread-safety issues
    catalogs = [SQLiteGoodreadsCatalog(trace=trace_tool) for _ in range(agent_max_workers)]
    catalog_queue: asyncio.Queue[SQLiteGoodreadsCatalog] = asyncio.Queue()
    for catalog in catalogs:
        catalog_queue.put_nowait(catalog)
    iterator = progress_iter(
        txt_files,
        desc="Stage 3/3: Goodreads agent",
        unit="book",
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
                except Exception as exc:
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
        except Exception as exc:
            print(f"[agent] Warning: failed to parse response {response}: {exc}")
            return idx, None

        record = {"citation": citation, "agent_response": payload}
        return idx, json.dumps(record, ensure_ascii=False)

    for txt in iterator:
        pre_path = pre_dir / f"{txt.stem}.json"
        final_path = output_dir / f"{txt.stem}.jsonl"
        if final_path.exists():
            print(f"[agent] Skip {txt.name} (cached).")
            continue
        if not pre_path.exists():
            print(f"[agent] Missing preprocessed JSON for {txt.name}, skipping.")
            continue

        data = json.loads(pre_path.read_text())
        citations = data.get("citations", [])
        prompts = build_prompts(
            citations,
            source_title=txt.stem,
            source_authors=[],
            source_description=None,
        )
        print(f"[agent] Processing {len(citations)} citations for {txt.name}")

        if not citations:
            final_path.write_text("")
            continue

        citation_bar = None
        if tqdm is not None:
            citation_bar = tqdm(
                total=len(citations),
                desc=f"  citations for {txt.name}",
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
            with final_path.open("w", encoding="utf-8") as out:
                for record_line in results:
                    if record_line is not None:
                        out.write(record_line + "\n")
        finally:
            if citation_bar is not None:
                citation_bar.close()


def stage_agent(
    pre_dir: Path,
    output_dir: Path,
    txt_files: Iterable[Path],
    base_url: str,
    api_key: str,
    model_id: str,
    trace_tool: bool,
    agent_max_workers: int,
) -> None:
    asyncio.run(
        stage_agent_async(
            pre_dir,
            output_dir,
            txt_files,
            base_url,
            api_key,
            model_id,
            trace_tool,
            agent_max_workers,
        )
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Full citation processing pipeline.")
    parser.add_argument("input_dir", type=Path, help="Directory containing .txt files.")
    parser.add_argument(
        "--extract-base-url",
        default="http://localhost:8080/v1",
        help="Base URL for extraction stage (run_single_file).",
    )
    parser.add_argument(
        "--extract-api-key",
        default=os.environ.get("EXTRACT_API_KEY", "test"),
        help="API key for extraction stage.",
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
        "--extract-model",
        default=EXTRACT_MODEL_ID,
        help="Model identifier/tokenizer to use for extraction.",
    )
    parser.add_argument(
        "--agent-model",
        default=AGENT_MODEL_ID,
        help="Model identifier to use for the Goodreads metadata agent.",
    )
    parser.add_argument(
        "--pattern",
        default="*.txt",
        help="Glob pattern to select specific .txt files (default: *.txt).",
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
    if not args.input_dir.exists():
        raise SystemExit(f"Input directory {args.input_dir} does not exist.")
    txt_files = find_txt_files(args.input_dir, args.pattern)
    if not txt_files:
        print("No .txt files found; nothing to do.")
        return

    raw_dir = args.input_dir / "raw_extracted_citations"
    pre_dir = args.input_dir / "preprocessed_extracted_citations"
    final_dir = args.input_dir / "final_citations_metadata_goodreads"

    stage_extract(txt_files, raw_dir, args.extract_base_url, args.extract_api_key, args.extract_model)
    stage_preprocess(raw_dir, pre_dir, txt_files)
    stage_agent(
        pre_dir,
        final_dir,
        txt_files,
        args.agent_base_url,
        args.agent_api_key,
        args.agent_model,
        args.agent_trace,
        args.agent_max_workers,
    )

    print("Pipeline complete.")


if __name__ == "__main__":
    main()
