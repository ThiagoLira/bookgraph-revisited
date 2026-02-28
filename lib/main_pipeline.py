import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence
from dataclasses import dataclass

from lib.extract_citations import (
    ExtractionConfig,
    process_book,
    write_output,
)
from lib.clean_citations import clean_citations
from lib.bibliography_agent.citation_workflow import CitationWorkflow
from lib.bibliography_agent.bibliography_tool import SQLiteGoodreadsCatalog
from lib.metadata_enricher import MetadataEnricher
from lib.llm_client import LLMConfig, build_llama_llm
from lib.checkpoint import CheckpointManager
from lib.author_cache import AuthorCache
from lib.dedup import dedup_resolved_citations
from lib.edge_builder import build_result_dict

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



@dataclass
class PipelineConfig:
    # LLM Endpoints
    extract_llm: LLMConfig = None  # type: ignore[assignment]  # for extraction (local/cheap)
    agent_llm: LLMConfig = None  # type: ignore[assignment]  # for workflow, validation, enrichment

    # Extraction
    extract_chunk_size: int = 50
    extract_max_context: int = 6144
    extract_max_completion: int = 2048
    extract_concurrency: int = 20

    # Workflow
    agent_concurrency: int = 20

    # Validation
    validate_concurrency: int = 5

    # Data
    books_db: str = "datasets/books_index.db"
    authors_json: str = "datasets/goodreads_book_authors.json"
    wiki_db: str = "datasets/wiki_people_index.db"

    # Enrichment Paths
    dates_json: str = "datasets/original_publication_dates.json"
    author_meta_json: str = "datasets/authors_metadata.json"
    legacy_dates_json: Optional[str] = None

    debug_trace: bool = False
    force_llm_queries: bool = False

    def __post_init__(self):
        if self.extract_llm is None:
            self.extract_llm = LLMConfig()
        if self.agent_llm is None:
            self.agent_llm = LLMConfig()


class BookPipeline:
    def __init__(self, config: PipelineConfig):
        self.config = config
        self._setup_workflow()
        self._setup_enricher()

    def _setup_workflow(self):
        # Initialize LLM and Workflow once
        self.llm = build_llama_llm(self.config.agent_llm)

        self.workflow = CitationWorkflow(
            books_db_path=self.config.books_db,
            authors_path=self.config.authors_json,
            wiki_people_path=self.config.wiki_db,
            llm=self.llm,
            verbose=self.config.debug_trace,
            timeout=120.0,
            force_llm_queries=self.config.force_llm_queries,
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
            books_db=self.config.books_db,
            llm=self.llm,
            auto_update=True,
            wiki_catalog=self.wiki_catalog,
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
                    # Merge full catalog metadata (description, rating, pages, etc.)
                    # into source, without overwriting fields already present
                    for k, v in book_match.items():
                        if v is not None and k not in enriched:
                            enriched[k] = v

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
        2. Clean (Heuristics + LLM validation) -> cleaned_dir
        3. Resolve (Workflow + enrichment + dedup) -> final_dir
        """
        # 0. Enrich source metadata first
        logger.info(f"[pipeline] Enriching source metadata for: {source_metadata.get('title', book_id)}")
        print(f"[pipeline] Enriching source metadata...")
        source_metadata = await self._enrich_source_metadata(source_metadata, book_id)

        raw_dir = output_dir / "raw_extracted_citations"
        cleaned_dir = output_dir / "cleaned_citations"
        final_dir = output_dir / "final_citations_metadata_goodreads"

        raw_dir.mkdir(parents=True, exist_ok=True)
        cleaned_dir.mkdir(parents=True, exist_ok=True)
        final_dir.mkdir(parents=True, exist_ok=True)

        raw_path = raw_dir / f"{book_id}.json"
        cleaned_path = cleaned_dir / f"{book_id}.json"
        final_path = final_dir / f"{book_id}.json"

        # Backward compat: check old directories for existing results
        legacy_val_path = output_dir / "validated_citations" / f"{book_id}.json"

        # 1. Extraction
        if not raw_path.exists() or force:
            logger.info(f"[pipeline] Extracting {book_id}...")
            print(f"[pipeline] Extracting {book_id}...")
            await self._run_extraction(input_text_path, raw_path)

        # 2. Clean (heuristics + LLM validation, single stage)
        if not cleaned_path.exists() and not legacy_val_path.exists() or force:
            logger.info(f"[pipeline] Cleaning {book_id}...")
            print(f"[pipeline] Cleaning {book_id}...")
            await self._run_cleaning(raw_path, cleaned_path, source_metadata)

        # Determine which cleaned file to use for workflow
        workflow_input = cleaned_path if cleaned_path.exists() else legacy_val_path

        # 3. Resolve (Workflow)
        if not final_path.exists() or force:
             logger.info(f"[pipeline] Running Workflow {book_id}...")
             print(f"[pipeline] Running Workflow {book_id}...")
             await self._run_workflow(workflow_input, final_path, source_metadata)

        return final_path

    async def _run_extraction(self, input_path: Path, output_path: Path):
        config = ExtractionConfig(
            input_path=input_path,
            chunk_size=self.config.extract_chunk_size,
            max_concurrency=self.config.extract_concurrency,
            max_context_per_request=self.config.extract_max_context,
            max_completion_tokens=self.config.extract_max_completion,
            base_url=self.config.extract_llm.base_url,
            api_key=self.config.extract_llm.api_key,
            model=self.config.extract_llm.model,
            tokenizer_name=self.config.extract_llm.model,
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

    async def _run_cleaning(self, raw_path: Path, cleaned_path: Path, meta: Dict[str, Any]):
        """Combined heuristic preprocessing + LLM validation in a single stage."""
        raw_data = json.loads(raw_path.read_text())

        result = await clean_citations(
            raw_data,
            source_name=raw_path.name,
            source_title=meta.get("title"),
            source_authors=meta.get("authors"),
            llm_config=self.config.agent_llm,
            validate_concurrency=self.config.validate_concurrency,
        )

        cleaned_path.write_text(json.dumps(result, indent=2, ensure_ascii=False))

        total_raw = sum(len(c.get("citations", [])) for c in raw_data.get("chunks", []))
        total_clean = result["total"]
        stats = result.get("validation_stats", {})
        logger.info(f"[pipeline] Cleaning: {total_raw} raw → {total_clean} cleaned "
                     f"(removed={stats.get('removed', 0)}, fixed={stats.get('fixed', 0)})")
        print(f"[pipeline] Cleaning: {total_raw} raw → {total_clean} cleaned "
              f"(removed={stats.get('removed', 0)}, fixed={stats.get('fixed', 0)})")

    async def _run_workflow(self, pre_path: Path, final_path: Path, meta: Dict[str, Any]):
        data = json.loads(pre_path.read_text())
        citations = data.get("citations", [])

        if not citations:
            final_path.write_text(json.dumps({"source": meta, "citations": []}, indent=2))
            return

        # Checkpoint and author cache
        ckpt = CheckpointManager(final_path.with_suffix('.checkpoint.json'))
        existing_results, processed_keys = ckpt.load()

        author_cache = AuthorCache()
        author_cache.seed_from_results(existing_results)

        # Filter out already-processed citations
        citations_to_process = [
            cit for cit in citations
            if (cit.get("author"), cit.get("title")) not in processed_keys
        ]

        sem = asyncio.Semaphore(self.config.agent_concurrency)

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
            target_type = r.get("edge", {}).get("target_type", "unknown")
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

        # Separate author-only cache hits from citations needing workflow
        cached_results: List[dict] = []
        citations_needing_workflow: List[dict] = []

        for cit in citations_to_process:
            cached = author_cache.find_for_author_only(cit)
            if cached:
                cached_results.append(cached)
                stats["cache_hits"] += 1
            else:
                citations_needing_workflow.append(cit)

        logger.info(f"[cache] {stats['cache_hits']} cache hits, {len(citations_needing_workflow)} citations need workflow")

        pbar = tqdm(total=len(citations_to_process), desc="  Resolving Citations", leave=False) if tqdm else None
        if pbar and cached_results:
            pbar.update(len(cached_results))

        tasks = [process_safe(cit) for cit in citations_needing_workflow]
        results = list(existing_results)
        results.extend(cached_results)

        for future in asyncio.as_completed(tasks):
            cit, res = await future

            match_type = res.get("match_type", "unknown")
            metadata = res.get("metadata", {})

            if "error" in res:
                stats["workflow_error"] += 1
            elif match_type not in ["not_found", "unknown", "error"]:
                stats["workflow_success"] += 1

            # Fallback for unresolved citations
            if match_type in ["not_found", "unknown", "error"]:
                match_type, metadata = await self._try_fallback(cit, meta, match_type, metadata, stats)

            wiki_match = metadata.get("wikipedia_match")

            # Enrichment
            wiki_match = await self._enrich_citation(cit, match_type, metadata, wiki_match, stats)

            result_dict = build_result_dict(cit, match_type, metadata, wiki_match)
            results.append(result_dict)

            # Cache for future author-only citations
            author = cit.get("author")
            if author and match_type != "error":
                author_cache.add(author, result_dict)

            if len(results) % 5 == 0:
                ckpt.save(meta, results)

            if pbar: pbar.update(1)

        if pbar: pbar.close()

        # Summary
        logger.info(f"[pipeline] Resolution Stats: {json.dumps(stats)}")
        self._print_resolution_summary(stats)

        # Post-resolution dedup
        results = dedup_resolved_citations(results)

        # Flush enrichment updates
        logger.info("[pipeline] Saving enriched metadata...")
        print("[pipeline] Saving enriched metadata...")
        self.enricher.save()

        output = {"source": meta, "citations": results}
        final_path.write_text(json.dumps(output, indent=2, ensure_ascii=False))
        ckpt.remove()

    async def _try_fallback(self, cit: dict, meta: dict, match_type: str,
                            metadata: dict, stats: dict) -> tuple:
        """Try enricher fallback for unresolved citations. Returns (match_type, metadata)."""
        stats["fallback_triggered"] += 1
        logger.info(f"[fallback] Triggering for: title='{cit.get('title')}', author='{cit.get('author')}' (reason: {match_type})")

        try:
            fallback_res = await self.enricher.resolve_citation_fallback(cit, meta)
            fallback_match = fallback_res.get("match_type", "not_found")

            if fallback_match in ["book", "person"]:
                stats["fallback_success"] += 1
                match_type = fallback_match
                metadata = fallback_res.get("metadata", {})

                # Generate synthetic ID for books without one
                if match_type == "book" and not metadata.get("book_id"):
                    import hashlib
                    slug = f"{metadata.get('title', '')}{metadata.get('original_year', '')}"
                    metadata["book_id"] = f"web_{hashlib.md5(slug.encode()).hexdigest()[:8]}"
            else:
                logger.debug(f"[fallback] No match found for: {cit.get('author')}")
        except Exception as e:
            logger.error(f"[fallback] Error during fallback: {e}")

        return match_type, metadata

    async def _enrich_citation(self, cit: dict, match_type: str, metadata: dict,
                               wiki_match: Optional[dict], stats: dict) -> Optional[dict]:
        """Enrich a resolved citation with publication year and author bio. Returns wiki_match."""
        enrichment = {}
        target_title = metadata.get("title") or cit.get("title")
        target_authors = metadata.get("authors") or [cit.get("author")]
        target_author_name = target_authors[0] if target_authors else None
        target_book_id = metadata.get("book_id")

        # 1. Enrich Book (publication year)
        if metadata.get("original_year"):
            enrichment["original_year"] = metadata["original_year"]
        elif target_book_id and target_title:
            try:
                year = await self.enricher.enrich_book(str(target_book_id), target_title, target_author_name or "")
                if year:
                    enrichment["original_year"] = year
            except Exception as e:
                logger.warning(f"[enrich] Book enrichment failed: {e}")
        elif match_type == "book" and target_title:
            try:
                year = await self.enricher.enrich_book(None, target_title, target_author_name or "")
                if year:
                    enrichment["original_year"] = year
            except Exception as e:
                logger.warning(f"[enrich] Book enrichment (no ID) failed: {e}")

        # 2. Enrich Author (birth/death years)
        fallback_has_bio = metadata.get("birth_year") or metadata.get("death_year")
        if fallback_has_bio:
            auth_meta = {
                k: metadata[k] for k in ("birth_year", "death_year", "nationality", "main_genre")
                if metadata.get(k)
            }
            if auth_meta:
                stats["enrichment_success"] += 1
                enrichment["author_meta"] = auth_meta
                if not wiki_match:
                    wiki_match = {"title": target_author_name}
                if auth_meta.get("birth_year") and not wiki_match.get("birth_year"):
                    wiki_match["birth_year"] = auth_meta["birth_year"]
                if auth_meta.get("death_year") and not wiki_match.get("death_year"):
                    wiki_match["death_year"] = auth_meta["death_year"]
        elif target_author_name:
            try:
                auth_meta = await self.enricher.enrich_author(target_author_name)
                if auth_meta:
                    stats["enrichment_success"] += 1
                    enrichment["author_meta"] = auth_meta
                    if not wiki_match:
                        wiki_match = {"title": target_author_name}
                    if auth_meta.get("birth_year") and not wiki_match.get("birth_year"):
                        wiki_match["birth_year"] = auth_meta["birth_year"]
                    if auth_meta.get("death_year") and not wiki_match.get("death_year"):
                        wiki_match["death_year"] = auth_meta["death_year"]
            except Exception as e:
                logger.warning(f"[enrich] Author enrichment failed for '{target_author_name}': {e}")

        metadata.update(enrichment)
        return wiki_match

    @staticmethod
    def _print_resolution_summary(stats: dict):
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
