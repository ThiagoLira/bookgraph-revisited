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
from lib.metadata_enricher import MetadataEnricher

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
    
    # Enrichment Paths
    dates_json: str = "frontend/data/stalin_library/original_publication_dates.json"
    author_meta_json: str = "frontend/data/stalin_library/authors_metadata.json"
    legacy_dates_json: Optional[str] = "datasets/original_publication_dates.json" # Default legacy
    
    debug_trace: bool = False

class BookPipeline:
    def __init__(self, config: PipelineConfig):
        self.config = config
        self._setup_workflow()
        self._setup_enricher()
        
    def _setup_workflow(self):
        # Initialize LLM and Workflow once
        self.llm = build_llm(
            model=self.config.agent_model, 
            api_key=self.config.agent_api_key, 
            base_url=self.config.agent_base_url
        )
        
        self.workflow = CitationWorkflow(
            books_db_path=self.config.books_db,
            authors_path=self.config.authors_json,
            wiki_people_path=self.config.wiki_db,
            llm=self.llm,
            verbose=self.config.debug_trace,
            timeout=120.0,
        )

    def _setup_enricher(self):
        self.enricher = MetadataEnricher(
            dates_path=self.config.dates_json,
            authors_path=self.config.author_meta_json,
            legacy_dates_path=self.config.legacy_dates_json,
            llm=self.llm,
            auto_update=True
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
                    res = await self.workflow.run(citation=cit)
                    return (cit, res)
                except Exception as e:
                    print(f"Error in workflow: {e}")
                    return (cit, {"error": str(e)})

        pbar = tqdm(total=len(citations), desc="  Resolving Citations", leave=False) if tqdm else None
        
        # We can also batch enrichment, but let's do it sequentially per item 
        # post-resolution for simplicity, or inside the loop.
        # To avoid blocking the semaphore with enrichment logic (LLM calls), 
        # we might want to do it in parallel too.
        
        tasks = [process_safe(cit) for cit in citations]
        results = []
        
        # Use as_completed to update progress bar as items finish
        for future in asyncio.as_completed(tasks):
            cit, res = await future
            
            # Merge result with citation
            if "error" in res:
                if pbar: pbar.update(1)
                continue
                
            match_type = res.get("match_type", "unknown")
            metadata = res.get("metadata", {})
            
            # --- FALLBACK START ---
            if match_type in ["not_found", "unknown"]:
                # Try fallback resolution
                # Pass source context (meta is the source_metadata passed to _run_workflow)
                fallback_res = await self.enricher.resolve_citation_fallback(cit, meta)
                if fallback_res.get("match_type") in ["book", "person"]:
                    match_type = fallback_res["match_type"]
                    metadata = fallback_res["metadata"]
                    # If it's a book, we might generate a fake ID or just rely on title/author
                    if match_type == "book":
                        # Generate a deterministic ID from title to allow graph linking? 
                        # Or leave ID null and reliance is on title matching in frontend (which defaults to ID)
                        # Let's generate a synthetic ID if missing
                        if not metadata.get("book_id"):
                            import hashlib
                            slug = f"{metadata.get('title')}{metadata.get('original_year')}"
                            metadata["book_id"] = f"web_{hashlib.md5(slug.encode()).hexdigest()[:8]}"
            # --- FALLBACK END ---
            
            # Build Edge
            target_book_id = metadata.get("book_id")
            target_author_ids = []
            if metadata.get("author_id"):
                 target_author_ids.append(str(metadata.get("author_id")))
            elif metadata.get("author_ids"):
                 target_author_ids = [str(a) for a in metadata.get("author_ids")]

            wiki_match = metadata.get("wikipedia_match")

            # --- ENRICHMENT START ---
            enrichment = {}
            
            # 1. Enrich Book
            target_title = metadata.get("title") or cit.get("title")
            target_authors = metadata.get("authors") or [cit.get("author")]
            target_author_name = target_authors[0] if target_authors else "Unknown"

            if target_book_id and target_title:
                year = await self.enricher.enrich_book(str(target_book_id), target_title, target_author_name)
                if year:
                    enrichment["original_year"] = year
            elif match_type == "book" and target_title:
                 # Even if no ID (rare for 'book' match type but possible if partial), try enrich by title
                 year = await self.enricher.enrich_book(None, target_title, target_author_name)
                 if year:
                    enrichment["original_year"] = year

            # 2. Enrich Authors
            # Enrich all found author IDs/Names
            for auth_id in target_author_ids:
                # We need name map... metadata usually has 'authors' list but not id->name map
                # We'll just assume the main author or iterate if we have names
                pass 
            
            # If we have a name from the citation or metadata
            main_author_name = target_author_name
            if main_author_name:
                auth_meta = await self.enricher.enrich_author(main_author_name)
                if auth_meta:
                    enrichment["author_meta"] = auth_meta
            # --- ENRICHMENT END ---
            
            # Merge enrichment into metadata for valid JSON output
            metadata.update(enrichment)

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
        
        # Flush enrichment updates
        print("[pipeline] Saving enriched metadata...")
        self.enricher.save()
        
        output = {
            "source": meta,
            "citations": results
        }
        final_path.write_text(json.dumps(output, indent=2, ensure_ascii=False))
