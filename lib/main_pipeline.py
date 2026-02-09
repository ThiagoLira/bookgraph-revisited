import asyncio
import copy
import json
import logging
import os
import unicodedata
from difflib import SequenceMatcher
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
from .validate_citations import validate_citations
from lib.bibliography_agent.citation_workflow import CitationWorkflow
from lib.bibliography_agent.llm_utils import build_llm
from lib.bibliography_agent.bibliography_tool import SQLiteWikiPeopleIndex, SQLiteGoodreadsCatalog
from lib.metadata_enricher import MetadataEnricher

# Configure module logger
logger = logging.getLogger(__name__)

try:
    from tqdm import tqdm  # type: ignore
except ImportError:
    tqdm = None

def progress_iter_items(iterable: Sequence[Any], **kwargs: Any) -> Sequence[Any]:
    if tqdm is None:
        return iterable
    return tqdm(iterable, **kwargs)

def _normalize_author(name: str) -> str:
    """Normalize author name for cache lookup.

    Strips accents, lowercases, removes periods/commas, and strips common
    prefixes like 'St.' or 'Saint'.
    """
    # Strip accents
    name = unicodedata.normalize('NFD', name)
    name = ''.join(c for c in name if unicodedata.category(c) != 'Mn')
    # Lowercase, strip periods/commas, normalize whitespace
    name = name.lower().replace('.', '').replace(',', '').strip()
    name = ' '.join(name.split())
    # Strip common prefixes
    for prefix in ('st ', 'saint '):
        if name.startswith(prefix):
            name = name[len(prefix):]
    return name


def _find_cached_author(name: str, cache: Dict[str, dict]) -> Optional[dict]:
    """Look up an author in the cache, with fuzzy fallback."""
    key = _normalize_author(name)
    if key in cache:
        return cache[key]
    # Fuzzy fallback: check existing keys with SequenceMatcher
    for cached_key, cached_val in cache.items():
        if SequenceMatcher(None, key, cached_key).ratio() >= 0.9:
            return cached_val
    return None


@dataclass
class PipelineConfig:
    # Extraction
    extract_base_url: str = "http://localhost:8080/v1"
    extract_api_key: str = "test"
    extract_model: str = "deepseek/deepseek-v3.2"
    extract_chunk_size: int = 50
    extract_max_context: int = 6144
    extract_max_completion: int = 2048

    # Workflow
    agent_base_url: str = "https://openrouter.ai/api/v1"
    agent_api_key: str = ""
    agent_model: str = "deepseek/deepseek-v3.2"
    agent_concurrency: int = 20
    extract_concurrency: int = 20

    # Validation
    validate_concurrency: int = 5

    # Data
    books_db: str = "datasets/books_index.db"
    authors_json: str = "datasets/goodreads_book_authors.json"
    wiki_db: str = "datasets/wiki_people_index.db"

    # Enrichment Paths
    dates_json: str = "datasets/original_publication_dates.json"
    author_meta_json: str = "datasets/authors_metadata.json"
    legacy_dates_json: Optional[str] = None  # legacy no longer needed by default

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

        # Keep reference to wiki catalog for enricher
        self.wiki_catalog = self.workflow.wiki_catalog

        # Keep reference to books catalog for source enrichment
        self.books_catalog = SQLiteGoodreadsCatalog(self.config.books_db, trace=self.config.debug_trace)

    def _setup_enricher(self):
        self.enricher = MetadataEnricher(
            dates_path=self.config.dates_json,
            authors_path=self.config.author_meta_json,
            legacy_dates_path=self.config.legacy_dates_json,
            llm=self.llm,
            auto_update=True,
            wiki_catalog=self.wiki_catalog  # Pass local wiki DB to enricher
        )

    async def _enrich_source_metadata(self, source_metadata: Dict[str, Any], book_id: str) -> Dict[str, Any]:
        """
        Enrich source book metadata before processing.

        Uses local DB lookups first, then LLM fallback for missing data.
        Returns enriched metadata dict with:
        - authors: list of author names
        - publication_year: original publication year
        - author_metadata: dict with birth/death years for primary author
        """
        enriched = dict(source_metadata)
        title = source_metadata.get("title", "")
        goodreads_id = source_metadata.get("goodreads_id") or book_id

        logger.info(f"[source-enrich] Enriching source: '{title}' (ID: {goodreads_id})")

        # 1. Try local Goodreads catalog for author names and publication year
        authors = enriched.get("authors", [])
        pub_year = enriched.get("publication_year")

        if goodreads_id and (not authors or not pub_year):
            try:
                # Query by title to get full metadata including authors
                matches = self.books_catalog.find_books(title=title, limit=3)

                # Find match with same ID
                book_match = None
                for m in matches:
                    if str(m.get("book_id")) == str(goodreads_id):
                        book_match = m
                        break

                # Fallback: just use best match if no ID match
                if not book_match and matches:
                    book_match = matches[0]

                if book_match:
                    if not authors and book_match.get("authors"):
                        authors = book_match["authors"]
                        enriched["authors"] = authors
                        logger.info(f"[source-enrich] Found authors from catalog: {authors}")

                    if not pub_year and book_match.get("publication_year"):
                        pub_year = book_match["publication_year"]
                        enriched["publication_year"] = pub_year
                        logger.info(f"[source-enrich] Found publication year from catalog: {pub_year}")
            except Exception as e:
                logger.warning(f"[source-enrich] Catalog lookup failed: {e}")

        # 2. Fallback to LLM for missing author/year
        if not authors or not pub_year:
            logger.debug(f"[source-enrich] Using LLM fallback for source: '{title}'")
            try:
                prompt = (
                    f"Provide metadata for the book titled '{title}'.\n"
                    f"Return JSON ONLY with: {{'author': 'Primary Author Name', 'publication_year': YYYY}}\n"
                    f"Use the ORIGINAL publication year, not reprint dates.\n"
                    f"Return ONLY valid JSON, no explanation."
                )
                resp = await self.llm.acomplete(prompt)
                text = resp.text.strip()

                # Clean markdown code blocks
                if text.startswith("```"):
                    text = text.split("\n", 1)[1]
                    if text.endswith("```"):
                        text = text.rsplit("\n", 1)[0]

                data = json.loads(text)

                if not authors and data.get("author"):
                    authors = [data["author"]] if isinstance(data["author"], str) else data["author"]
                    enriched["authors"] = authors
                    logger.info(f"[source-enrich] LLM found authors: {authors}")

                if not pub_year and data.get("publication_year"):
                    pub_year = int(data["publication_year"])
                    enriched["publication_year"] = pub_year
                    logger.info(f"[source-enrich] LLM found publication year: {pub_year}")

            except Exception as e:
                logger.warning(f"[source-enrich] LLM fallback failed: {e}")

        # 3. Enrich primary author metadata (birth/death years)
        if authors:
            primary_author = authors[0] if isinstance(authors, list) else authors
            try:
                author_meta = await self.enricher.enrich_author(primary_author)
                if author_meta:
                    enriched["author_metadata"] = author_meta
                    logger.info(f"[source-enrich] Author metadata: {primary_author} -> birth={author_meta.get('birth_year')}, death={author_meta.get('death_year')}")
            except Exception as e:
                logger.warning(f"[source-enrich] Author enrichment failed for '{primary_author}': {e}")

        # 4. Get original publication year if still missing
        if not pub_year and title:
            try:
                year = await self.enricher.enrich_book(str(goodreads_id), title, authors[0] if authors else "")
                if year:
                    enriched["publication_year"] = year
                    logger.info(f"[source-enrich] Enricher found publication year: {year}")
            except Exception as e:
                logger.warning(f"[source-enrich] Book year enrichment failed: {e}")

        logger.info(f"[source-enrich] Final source metadata: title='{enriched.get('title')}', authors={enriched.get('authors')}, year={enriched.get('publication_year')}")
        return enriched

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
        0. Enrich source metadata (author, publication year)
        1. Extract (LLM) -> raw_dir
        2. Preprocess (Heuristic) -> pre_dir
        3. Validate (LLM) -> val_dir
        4. Workflow (Agent) -> final_dir
        """
        # 0. Enrich source metadata first
        logger.info(f"[pipeline] Enriching source metadata for: {source_metadata.get('title', book_id)}")
        print(f"[pipeline] Enriching source metadata...")
        source_metadata = await self._enrich_source_metadata(source_metadata, book_id)

        raw_dir = output_dir / "raw_extracted_citations"
        pre_dir = output_dir / "preprocessed_extracted_citations"
        val_dir = output_dir / "validated_citations"
        final_dir = output_dir / "final_citations_metadata_goodreads"

        raw_dir.mkdir(parents=True, exist_ok=True)
        pre_dir.mkdir(parents=True, exist_ok=True)
        val_dir.mkdir(parents=True, exist_ok=True)
        final_dir.mkdir(parents=True, exist_ok=True)

        raw_path = raw_dir / f"{book_id}.json"
        pre_path = pre_dir / f"{book_id}.json"
        val_path = val_dir / f"{book_id}.json"
        final_path = final_dir / f"{book_id}.json"

        # 1. Extraction
        if not raw_path.exists() or force:
            logger.info(f"[pipeline] Extracting {book_id}...")
            print(f"[pipeline] Extracting {book_id}...")
            await self._run_extraction(input_text_path, raw_path)

        # 2. Preprocess
        if not pre_path.exists() or force:
             logger.info(f"[pipeline] Preprocessing {book_id}...")
             print(f"[pipeline] Preprocessing {book_id}...")
             self._run_preprocessing(raw_path, pre_path, source_metadata)

        # 3. Validate
        if not val_path.exists() or force:
             logger.info(f"[pipeline] Validating {book_id}...")
             print(f"[pipeline] Validating {book_id}...")
             await self._run_validation(pre_path, val_path, source_metadata)

        # 4. Workflow
        if not final_path.exists() or force:
             logger.info(f"[pipeline] Running Workflow {book_id}...")
             print(f"[pipeline] Running Workflow {book_id}...")
             await self._run_workflow(val_path, final_path, source_metadata)

        return final_path

    async def _run_extraction(self, input_path: Path, output_path: Path):
        config = ExtractionConfig(
            input_path=input_path,
            chunk_size=self.config.extract_chunk_size,
            max_concurrency=self.config.extract_concurrency,
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

    async def _run_validation(self, pre_path: Path, val_path: Path, meta: Dict[str, Any]):
        data = json.loads(pre_path.read_text())
        citations = data.get("citations", [])
        source_title = meta.get("title", "")
        source_authors = meta.get("authors", [])

        if not citations:
            val_path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
            return

        validated, stats = await validate_citations(
            citations,
            source_title,
            source_authors,
            base_url=self.config.agent_base_url,
            api_key=self.config.agent_api_key,
            model=self.config.agent_model,
            concurrency=self.config.validate_concurrency,
        )

        output = {
            "source": data.get("source", pre_path.name),
            "total": len(validated),
            "validation_stats": stats,
            "citations": validated,
        }
        val_path.write_text(json.dumps(output, indent=2, ensure_ascii=False))

        logger.info(f"[pipeline] Validation: {len(citations)} → {len(validated)} citations "
                     f"(removed={stats['removed']}, fixed={stats['fixed']})")
        print(f"[pipeline] Validation: {len(citations)} → {len(validated)} citations "
              f"(removed={stats['removed']}, fixed={stats['fixed']})")

    def _save_checkpoint(self, path: Path, meta: Dict, results: List):
        """Save checkpoint with partial results."""
        path.write_text(json.dumps({"source": meta, "citations": results, "complete": False}, indent=2, ensure_ascii=False))
        logger.debug(f"[pipeline] Checkpoint saved: {len(results)} citations")

    def _add_to_author_cache(self, cache: Dict[str, dict], author_name: str, result_dict: dict):
        """Add a resolved result to the author cache, including bare last-name variant."""
        key = _normalize_author(author_name)
        cache[key] = result_dict
        # Also cache bare last name for fuzzy matching (e.g. "Plutarch" from "Lucius Plutarch")
        parts = key.split()
        if len(parts) > 1:
            cache[parts[-1]] = result_dict

    async def _run_workflow(self, pre_path: Path, final_path: Path, meta: Dict[str, Any]):
        data = json.loads(pre_path.read_text())
        citations = data.get("citations", [])

        if not citations:
            # Write empty result
            final_path.write_text(json.dumps({"source": meta, "citations": []}, indent=2))
            return

        # Checkpoint support
        checkpoint_path = final_path.with_suffix('.checkpoint.json')

        # Load existing checkpoint if resuming
        existing_results = []
        processed_keys = set()
        if checkpoint_path.exists():
            checkpoint = json.loads(checkpoint_path.read_text())
            existing_results = checkpoint.get("citations", [])
            processed_keys = {(r["raw"].get("author"), r["raw"].get("title")) for r in existing_results}
            logger.info(f"[pipeline] Resuming from checkpoint: {len(existing_results)} already processed")
            print(f"[pipeline] Resuming from checkpoint: {len(existing_results)} already processed")

        # Filter out already-processed citations
        citations_to_process = [
            cit for cit in citations
            if (cit.get("author"), cit.get("title")) not in processed_keys
        ]

        # --- Per-book resolution cache ---
        # Caches fully-resolved result_dicts keyed by normalized author name.
        # For author-only citations (no title): full cache hit -> skip workflow.
        # For book citations: not cached (title-specific), run workflow normally.
        author_cache: Dict[str, dict] = {}

        # Seed cache from checkpoint results
        for r in existing_results:
            raw = r.get("raw", {})
            author = raw.get("author")
            if author:
                self._add_to_author_cache(author_cache, author, r)

        # Prepare tasks
        sem = asyncio.Semaphore(self.config.agent_concurrency)

        # Stats for logging
        stats = {
            "total": len(citations),
            "cache_hits": 0,
            "workflow_success": 0,
            "workflow_error": 0,
            "fallback_triggered": 0,
            "fallback_success": 0,
            "enrichment_success": 0,
        }

        # Count already-processed successes from checkpoint
        for r in existing_results:
            edge = r.get("edge", {})
            target_type = edge.get("target_type", "unknown")
            if target_type not in ["not_found", "unknown", "error"]:
                stats["workflow_success"] += 1

        async def process_safe(cit):
            async with sem:
                cit_desc = f"'{cit.get('author', '?')}' - '{cit.get('title', '[no title]')}'"
                try:
                    res = await self.workflow.run(citation=cit)
                    return (cit, res)
                except Exception as e:
                    logger.error(f"[workflow] Error processing {cit_desc}: {type(e).__name__}: {e}")
                    logger.debug(f"[workflow] Full citation that failed: {json.dumps(cit, ensure_ascii=False)}")
                    return (cit, {"error": str(e), "match_type": "error"})

        # Separate citations into cache-hittable (author-only) and must-run (has title)
        cached_results: List[dict] = []
        citations_needing_workflow: List[dict] = []

        for cit in citations_to_process:
            author = cit.get("author")
            title = cit.get("title")
            is_author_only = author and not title

            if is_author_only and author:
                cached = _find_cached_author(author, author_cache)
                if cached:
                    # Full cache hit for author-only citation
                    cloned = copy.deepcopy(cached)
                    cloned["raw"] = cit  # Use the current citation's raw data
                    cached_results.append(cloned)
                    stats["cache_hits"] += 1
                    logger.info(f"[cache] Hit for author-only citation: '{author}'")
                    continue

            citations_needing_workflow.append(cit)

        logger.info(f"[cache] {stats['cache_hits']} cache hits, {len(citations_needing_workflow)} citations need workflow")

        pbar = tqdm(total=len(citations_to_process), desc="  Resolving Citations", leave=False) if tqdm else None

        # Count cached results in progress bar
        if pbar and cached_results:
            pbar.update(len(cached_results))

        tasks = [process_safe(cit) for cit in citations_needing_workflow]
        results = list(existing_results)  # Start with checkpoint results
        results.extend(cached_results)  # Add cache hits

        # Use as_completed to update progress bar as items finish
        for future in asyncio.as_completed(tasks):
            cit, res = await future

            match_type = res.get("match_type", "unknown")
            metadata = res.get("metadata", {})
            had_error = "error" in res

            if had_error:
                stats["workflow_error"] += 1
            elif match_type not in ["not_found", "unknown", "error"]:
                stats["workflow_success"] += 1

            # --- FALLBACK: Trigger for errors, not_found, or unknown ---
            if match_type in ["not_found", "unknown", "error"]:
                stats["fallback_triggered"] += 1
                logger.info(f"[fallback] Triggering for: title='{cit.get('title')}', author='{cit.get('author')}' (reason: {match_type})")

                try:
                    fallback_res = await self.enricher.resolve_citation_fallback(cit, meta)
                    fallback_match = fallback_res.get("match_type", "not_found")

                    if fallback_match in ["book", "person"]:
                        stats["fallback_success"] += 1
                        match_type = fallback_match
                        metadata = fallback_res.get("metadata", {})
                        logger.info(f"[fallback] Success: {match_type} - {metadata.get('title') or metadata.get('authors', ['?'])[0] if metadata.get('authors') else '?'}")

                        # Generate synthetic ID for books without one
                        if match_type == "book" and not metadata.get("book_id"):
                            import hashlib
                            slug = f"{metadata.get('title', '')}{metadata.get('original_year', '')}"
                            metadata["book_id"] = f"web_{hashlib.md5(slug.encode()).hexdigest()[:8]}"
                    else:
                        logger.debug(f"[fallback] No match found for: {cit.get('author')}")
                except Exception as e:
                    logger.error(f"[fallback] Error during fallback: {e}")

            # Build Edge
            target_book_id = metadata.get("book_id")
            target_author_ids = []
            if metadata.get("author_id"):
                 target_author_ids.append(str(metadata.get("author_id")))
            elif metadata.get("author_ids"):
                 target_author_ids = [str(a) for a in metadata.get("author_ids")]

            wiki_match = metadata.get("wikipedia_match")

            # --- ENRICHMENT ---
            enrichment = {}

            # 1. Enrich Book (get publication year)
            target_title = metadata.get("title") or cit.get("title")
            target_authors = metadata.get("authors") or [cit.get("author")]
            target_author_name = target_authors[0] if target_authors else None

            if target_book_id and target_title:
                try:
                    year = await self.enricher.enrich_book(str(target_book_id), target_title, target_author_name or "")
                    if year:
                        enrichment["original_year"] = year
                        logger.debug(f"[enrich] Book year: {target_title} -> {year}")
                except Exception as e:
                    logger.warning(f"[enrich] Book enrichment failed: {e}")
            elif match_type == "book" and target_title:
                 try:
                     year = await self.enricher.enrich_book(None, target_title, target_author_name or "")
                     if year:
                        enrichment["original_year"] = year
                 except Exception as e:
                    logger.warning(f"[enrich] Book enrichment (no ID) failed: {e}")

            # 2. Enrich Author (get birth/death years)
            if target_author_name:
                try:
                    auth_meta = await self.enricher.enrich_author(target_author_name)
                    if auth_meta:
                        stats["enrichment_success"] += 1
                        enrichment["author_meta"] = auth_meta
                        logger.debug(f"[enrich] Author: {target_author_name} -> birth={auth_meta.get('birth_year')}, death={auth_meta.get('death_year')}")

                        # IMPORTANT: Merge author dates into wiki_match / target_person
                        if not wiki_match:
                            wiki_match = {"title": target_author_name}

                        # Only add dates if not already present
                        if auth_meta.get("birth_year") and not wiki_match.get("birth_year"):
                            wiki_match["birth_year"] = auth_meta["birth_year"]
                        if auth_meta.get("death_year") and not wiki_match.get("death_year"):
                            wiki_match["death_year"] = auth_meta["death_year"]
                except Exception as e:
                    logger.warning(f"[enrich] Author enrichment failed for '{target_author_name}': {e}")

            # Merge enrichment into metadata
            metadata.update(enrichment)

            result_dict = {
                "raw": cit,
                "goodreads_match": metadata if match_type == "book" else None,
                "wikipedia_match": wiki_match,
                "edge": {
                    "target_type": match_type,
                    "target_book_id": target_book_id,
                    "target_author_ids": target_author_ids,
                    "target_person": wiki_match  # Now includes enriched birth/death
                }
            }
            results.append(result_dict)

            # Add to author cache for future citations in this book
            author = cit.get("author")
            if author and match_type not in ["error"]:
                self._add_to_author_cache(author_cache, author, result_dict)

            # Save checkpoint every 5 results
            if len(results) % 5 == 0:
                self._save_checkpoint(checkpoint_path, meta, results)

            if pbar: pbar.update(1)

        if pbar: pbar.close()

        # Log stats
        logger.info(f"[pipeline] Resolution Stats: {json.dumps(stats)}")

        # Print summary report
        print("\n" + "="*50)
        print("           RESOLUTION SUMMARY")
        print("="*50)
        print(f"  Total Citations:    {stats['total']}")
        print(f"  Cache Hits:         {stats['cache_hits']}")
        print(f"  Workflow Success:   {stats['workflow_success']} ({100*stats['workflow_success']//max(1,stats['total'])}%)")
        print(f"  Not Found:          {stats['total'] - stats['workflow_success'] - stats['workflow_error'] - stats['cache_hits']}")
        print(f"  Errors:             {stats['workflow_error']}")
        print(f"  Fallback Triggered: {stats['fallback_triggered']}")
        print(f"  Fallback Success:   {stats['fallback_success']}")
        print(f"  Authors Enriched:   {stats['enrichment_success']}")
        print("="*50 + "\n")

        # Flush enrichment updates
        logger.info("[pipeline] Saving enriched metadata...")
        print("[pipeline] Saving enriched metadata...")
        self.enricher.save()

        output = {
            "source": meta,
            "citations": results
        }
        final_path.write_text(json.dumps(output, indent=2, ensure_ascii=False))

        # Remove checkpoint after successful completion
        if checkpoint_path.exists():
            checkpoint_path.unlink()
            logger.info("[pipeline] Checkpoint removed after successful completion")
