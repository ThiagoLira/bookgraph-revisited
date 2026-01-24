import asyncio
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Sequence
from dataclasses import dataclass

from lib.extract_citations import (
    ExtractionConfig,
    ProgressCallback,
    process_book,
    write_output,
)
from .preprocess_citations import preprocess_data
from lib.bibliography_agent.citation_workflow import CitationWorkflow
from lib.bibliography_agent.llm_utils import build_llm

try:
    from tqdm import tqdm  # type: ignore
except ImportError:
    tqdm = None

def progress_iter_items(iterable: Sequence[Any], **kwargs: Any) -> Sequence[Any]:
    if tqdm is None:
        return iterable
    return tqdm(iterable, **kwargs)

@dataclass
class PipelineConfig:
    # Extraction
    extract_base_url: str = "http://localhost:8080/v1"
    extract_api_key: str = "test"
    extract_model: str = "Qwen/Qwen3-30B-A3B"
    extract_chunk_size: int = 50
    extract_max_context: int = 6144
    extract_max_completion: int = 2048
    
    # Workflow
    agent_base_url: str = "https://openrouter.ai/api/v1"
    agent_api_key: str = ""
    agent_model: str = "qwen/qwen3-next-80b-a3b-instruct"
    agent_concurrency: int = 10
    
    # Data
    books_db: str = "datasets/books_index.db"
    authors_json: str = "datasets/goodreads_book_authors.json"
    wiki_db: str = "datasets/wiki_people_index.db"
    
    debug_trace: bool = False

class BookPipeline:
    def __init__(self, config: PipelineConfig):
        self.config = config
        self._setup_workflow()
        
    def _setup_workflow(self):
        # Initialize LLM and Workflow once
        self.llm = build_llm(
            model=self.config.agent_model, 
            api_key=self.config.agent_api_key, 
            base_url=self.config.agent_base_url
        )
        # Note: CitationWorkflow tracks state per run, but we can reuse the instance 
        # as long as we call run() which creates a new Context.
        # WAIT: CitationWorkflow in llama-index might store state in self. 
        # Checking implementation: It uses `ctx` for state. So it should be safe to reuse?
        # Actually, let's create a new one per run effectively to be safe, 
        # or share the catalog instances.
        
        # We'll create the workflow instance here, as catalogs are heavy to load.
        self.workflow = CitationWorkflow(
            books_db_path=self.config.books_db,
            authors_path=self.config.authors_json,
            wiki_people_path=self.config.wiki_db,
            llm=self.llm,
            verbose=self.config.debug_trace,
            timeout=120.0,
        )

    async def run_file(
        self,
        input_text_path: Path,
        output_dir: Path,
        source_metadata: Dict[str, Any],
        book_id: str,
        force: bool = False
    ):
        """
        Run the full pipeline for a single book file.
        
        stages:
        1. Extract (LLM) -> raw_dir
        2. Preprocess (Heuristic) -> pre_dir
        3. Workflow (Agent) -> final_dir
        """
        raw_dir = output_dir / "raw_extracted_citations"
        pre_dir = output_dir / "preprocessed_extracted_citations"
        final_dir = output_dir / "final_citations_metadata_goodreads"
        
        raw_dir.mkdir(parents=True, exist_ok=True)
        pre_dir.mkdir(parents=True, exist_ok=True)
        final_dir.mkdir(parents=True, exist_ok=True)
        
        raw_path = raw_dir / f"{book_id}.json"
        pre_path = pre_dir / f"{book_id}.json"
        final_path = final_dir / f"{book_id}.json"
        
        # 1. Extraction
        if not raw_path.exists() or force:
            print(f"[pipeline] Extracting {book_id}...")
            await self._run_extraction(input_text_path, raw_path)
        
        # 2. Preprocess
        if not pre_path.exists() or force:
             # We always re-run preprocess if raw changed, but here we check existence
             print(f"[pipeline] Preprocessing {book_id}...")
             self._run_preprocessing(raw_path, pre_path, source_metadata)
             
        # 3. Workflow
        if not final_path.exists() or force:
             print(f"[pipeline] Running Workflow {book_id}...")
             await self._run_workflow(pre_path, final_path, source_metadata)
             
        return final_path

    async def _run_extraction(self, input_path: Path, output_path: Path):
        config = ExtractionConfig(
            input_path=input_path,
            chunk_size=self.config.extract_chunk_size,
            max_concurrency=10, # Internal concurrency for chunks
            max_context_per_request=self.config.extract_max_context,
            max_completion_tokens=self.config.extract_max_completion,
            base_url=self.config.extract_base_url,
            api_key=self.config.extract_api_key,
            model=self.config.extract_model,
            tokenizer_name=self.config.extract_model,
        )
        
        # Optional progress bar for chunks
        pbar = None
        def on_progress(done, total):
            nonlocal pbar
            if tqdm and not pbar:
                pbar = tqdm(total=total, desc="  Extracting Chunks", leave=False)
            if pbar:
                pbar.n = done
                pbar.refresh()
                
        try:
            result = await process_book(config, progress_callback=on_progress)
            write_output(result, output_path)
        finally:
            if pbar: pbar.close()

    def _run_preprocessing(self, raw_path: Path, pre_path: Path, meta: Dict[str, Any]):
        raw_data = json.loads(raw_path.read_text())
        processed = preprocess_data(
            raw_data,
            source_name=raw_path.name,
            source_title=meta.get("title"),
            source_authors=meta.get("authors")
        )
        pre_path.write_text(json.dumps(processed, indent=2, ensure_ascii=False))

    async def _run_workflow(self, pre_path: Path, final_path: Path, meta: Dict[str, Any]):
        data = json.loads(pre_path.read_text())
        citations = data.get("citations", [])
        
        if not citations:
            # Write empty result
            final_path.write_text(json.dumps({"source": meta, "citations": []}, indent=2))
            return

        # Prepare tasks
        sem = asyncio.Semaphore(self.config.agent_concurrency)
        
        async def process_safe(cit):
            async with sem:
                try:
                    return await self.workflow.run(citation=cit)
                except Exception as e:
                    print(f"Error in workflow: {e}")
                    return {"error": str(e)}

        pbar = tqdm(total=len(citations), desc="  Resolving Citations", leave=False) if tqdm else None
        
        results = []
        for cit in citations:
            res = await process_safe(cit)
            # Merge result with citation
            if "error" in res:
                continue
                
            match_type = res.get("match_type", "unknown")
            metadata = res.get("metadata", {})
            
            # Build Edge
            target_book_id = metadata.get("book_id")
            target_author_ids = []
            if metadata.get("author_id"):
                 target_author_ids.append(str(metadata.get("author_id")))
            elif metadata.get("author_ids"):
                 target_author_ids = [str(a) for a in metadata.get("author_ids")]

            wiki_match = metadata.get("wikipedia_match")

            results.append({
                "raw": cit,
                "goodreads_match": metadata,
                "wikipedia_match": wiki_match,
                "edge": {
                    "target_type": match_type,
                    "target_book_id": target_book_id,
                    "target_author_ids": target_author_ids,
                    "target_person": wiki_match
                }
            })
            if pbar: pbar.update(1)
            
        if pbar: pbar.close()
        
        output = {
            "source": meta,
            "citations": results
        }
        final_path.write_text(json.dumps(output, indent=2, ensure_ascii=False))
