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
from pathlib import Path
from typing import Iterable, List

from lib.extract_citations import ExtractionConfig, process_book, write_output
from preprocess_citations import preprocess as preprocess_citations
from lib.goodreads_agent.agent import build_agent
from lib.goodreads_agent.test_agent import build_prompts

# ---------- Tunable defaults ----------

EXTRACT_CHUNK_SIZE = 50
EXTRACT_MAX_CONCURRENCY = 20
EXTRACT_MAX_CONTEXT = 6144
EXTRACT_MAX_COMPLETION = 2048
EXTRACT_MODEL_ID = "Qwen/Qwen3-30B-A3B"

AGENT_MODEL_ID = "qwen/qwen3-next-80b-a3b-instruct"


def find_txt_files(folder: Path) -> List[Path]:
    return sorted(p for p in folder.iterdir() if p.suffix.lower() == ".txt")


async def run_extraction(
    txt_path: Path,
    output_path: Path,
    base_url: str,
    api_key: str,
    model_id: str,
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
    result = await process_book(config)
    write_output(result, output_path)


def stage_extract(
    txt_files: Iterable[Path],
    output_dir: Path,
    base_url: str,
    api_key: str,
    model_id: str,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for txt in txt_files:
        out_path = output_dir / f"{txt.stem}.json"
        if out_path.exists():
            print(f"[extract] Skip {txt.name} (cached).")
            continue
        print(f"[extract] Processing {txt.name} -> {out_path}")
        asyncio.run(run_extraction(txt, out_path, base_url, api_key, model_id))


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
) -> "GoodreadsAgentRunner":
    return build_agent(
        model=model_id,
        api_key=api_key,
        base_url=base_url,
        books_path="goodreads_data/goodreads_books.json",
        authors_path="goodreads_data/goodreads_book_authors.json",
        verbose=False,
        trace_tool=False,
    )


def stage_agent(
    pre_dir: Path,
    output_dir: Path,
    txt_files: Iterable[Path],
    base_url: str,
    api_key: str,
    model_id: str,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    runner = build_agent_runner(base_url, api_key, model_id)
    for txt in txt_files:
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
        prompts = build_prompts(citations)
        print(f"[agent] Processing {len(citations)} citations for {txt.name}")
        with final_path.open("w", encoding="utf-8") as out:
            for citation, prompt in zip(citations, prompts):
                response = runner.chat(prompt)
                try:
                    payload = json.loads(response)
                except Exception as exc:
                    print(f"[agent] Warning: failed to parse response {response}: {exc}")
                    continue
                record = {"citation": citation, "agent_response": payload}
                out.write(json.dumps(record, ensure_ascii=False) + "\n")


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
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.input_dir.exists():
        raise SystemExit(f"Input directory {args.input_dir} does not exist.")
    txt_files = find_txt_files(args.input_dir)
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
    )

    print("Pipeline complete.")


if __name__ == "__main__":
    main()
