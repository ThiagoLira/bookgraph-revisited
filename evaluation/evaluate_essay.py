
import asyncio
import json
import sys
import os
from pathlib import Path
from typing import List, Dict, Any

# Add repo root to path
repo_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repo_root))

from lib.bibliography_agent.citation_workflow import CitationWorkflow
from lib.bibliography_agent.llm_utils import build_llm
from llama_index.core import Settings
import logging
from lib.logging_config import setup_logging

logger = logging.getLogger(__name__)

# Metrics tracking
class Metrics:
    def __init__(self):
        self.total = 0
        self.processed = 0
        self.goodreads_hits = 0
        self.enrichment_hits = 0
        self.enrichment_missed = 0 # Should have been enriched but wasn't
        self.goodreads_failures = 0
    
    def report(self):
        logger.info("\n=== Evaluation Report ===")
        logger.info(f"Total Citations: {self.total}")
        logger.info(f"Processed: {self.processed}")
        logger.info(f"Goodreads Matches Found: {self.goodreads_hits}")
        logger.info(f"Enrichment Matches Found: {self.enrichment_hits}")
        logger.info(f"Enrichment Missed (Expected but not found): {self.enrichment_missed}")
        logger.info("=========================\n")

def fuzzy_match(s1: str, s2: str) -> bool:
    if not s1 or not s2: return False
    return s1.lower() in s2.lower() or s2.lower() in s1.lower()

async def run_evaluation():
    log_file = setup_logging(Path("evaluation/logs"))
    logger.info(f"Starting Evaluation Pipeline... Logs at {log_file}")
    
    # Configuration
    books_db = repo_root / "datasets/books_index.db"
    authors_file = repo_root / "datasets/goodreads_book_authors.json"
    wiki_db = repo_root / "datasets/wiki_people_index.db"
    
    # Enrichment Paths (Use TEMP to force lookup/test agent)
    dates_json = repo_root / "datasets/temp_original_publication_dates.json"
    author_meta_json = repo_root / "datasets/temp_authors_metadata.json"
    
    # Clean up temp files if they exist from previous runs
    if dates_json.exists(): dates_json.unlink()
    if author_meta_json.exists(): author_meta_json.unlink()
    
    # Load Ground Truths
    gt_path = repo_root / "evaluation/ground_truth.json"
    enrich_gt_path = repo_root / "evaluation/enrichment_ground_truth.json"
    
    if not gt_path.exists() or not enrich_gt_path.exists():
        logger.error("Error: Ground truth files not found.")
        return
        
    gt_entries = json.loads(gt_path.read_text())
    enrich_entries = json.loads(enrich_gt_path.read_text())
    
    # Build a lookup for enrichment GT by (title, author)
    enrich_lookup = {}
    for entry in enrich_entries:
        c = entry["citation"]
        key = (c.get("title"), c.get("author"))
        enrich_lookup[key] = entry.get("enrichment")

    # Initialize Workflow
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    base_url = os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    model = "openai/gpt-oss-120b"
    
    if not api_key:
        env_path = repo_root / ".env"
        if env_path.exists():
            logger.info(f"Loading .env from {env_path}")
            with open(env_path) as f:
                for line in f:
                    if line.strip() and not line.startswith("#") and "=" in line:
                        k, v = line.strip().split("=", 1)
                        if k == "OPENROUTER_API_KEY":
                            api_key = v
                            
    from llama_index.llms.openai_like import OpenAILike
    llm = OpenAILike(
        model=model,
        api_key=api_key,
        api_base=base_url,
        is_chat_model=True,
        is_function_calling_model=False,
        context_window=131072,
        max_tokens=1024
    )
    
    workflow = CitationWorkflow(
        books_db_path=str(books_db),
        authors_path=str(authors_file),
        wiki_people_path=str(wiki_db),
        llm=llm,
        verbose=False
    )
    
    # Initialize Enricher
    from lib.metadata_enricher import MetadataEnricher
    enricher = MetadataEnricher(
        dates_path=str(dates_json),
        authors_path=str(author_meta_json),
        llm=llm
    )
    
    metrics = Metrics()
    metrics.total = len(gt_entries)
    
    logger.info(f"Processing {len(gt_entries)} citations from Ground Truth...")
    
    for i, entry in enumerate(gt_entries):
        cit = entry["citation"]
        logger.info(f"[{i+1}/{len(gt_entries)}] Processing: {cit.get('title', 'Unknown')} / {cit.get('author', 'Unknown')}")
        
        # 1. Run Workflow
        try:
            result = await workflow.run(citation=cit)
        except Exception as e:
            logger.error(f"  Error running workflow: {e}")
            continue

        metrics.processed += 1
        
        match_type = result.get("match_type")
        metadata = result.get("metadata", {})
        
        logger.info(f"  Match: {match_type}")
        if match_type in ["book", "author", "person"]:
             metrics.goodreads_hits += 1
        
        # 2. Enrichment
        enriched_author_meta = {}
        book_year = None
        
        # Identity to enrich
        author_name_to_enrich = None
        
        if match_type == "book":
            book_id = metadata.get("book_id")
            title = metadata.get("title")
            # Author name from metadata or citation
            author_data = metadata.get("author") # string or list?
            # Usually author is inside metadata if it came from GR
            # But duplicate author logic might be tricky.
            # GR metadata usually has 'authors': ['Name'] or similar?
            # Workflow metadata update:
            # if gr_res: metadata.update(gr_res).
            # gr_res usually has 'title', 'book_id', 'author' (string name if single)
            
            author_clean = metadata.get("author") 
            if not author_clean: author_clean = cit.get("author")
            
            # Enrich Book Year
            try:
                book_year = await enricher.enrich_book(str(book_id) if book_id else None, title, author_clean)
            except Exception as e:
                logger.error(f"  Enrich Book Error: {e}")

            if author_clean:
                author_name_to_enrich = author_clean
                
        elif match_type in ["author", "person"]:
            author_name_to_enrich = metadata.get("name") or cit.get("author")

        # Enrich Author
        if author_name_to_enrich:
            try:
                enriched_author_meta = await enricher.enrich_author(author_name_to_enrich)
            except Exception as e:
                logger.error(f"  Enrich Author Error: {e}")
        
        # 3. Validation
        key = (cit.get("title"), cit.get("author"))
        expected = enrich_lookup.get(key)
        
        if expected:
            # Check correctness (Birth/Death Year)
            # Expected format: {"birth_year": 1930, "death_year": 2024, ...}
            
            if enriched_author_meta:
                # Compare fuzzy
                logger.info(f"  Enriched Author: {author_name_to_enrich} -> {enriched_author_meta}")
                
                # Check birth year
                exp_born = expected.get("birth_year")
                got_born = enriched_author_meta.get("birth_year")
                
                if exp_born and got_born:
                    if exp_born == got_born:
                        logger.info(f"    ✅ Birth Year Matches: {got_born}")
                    else:
                        logger.warning(f"    ❌ Birth Year Mismatch: Exp {exp_born} vs Got {got_born}")
                
                metrics.enrichment_hits += 1
            else:
                logger.warning(f"  MISSING ENRICHMENT! Expected for {author_name_to_enrich}")
                metrics.enrichment_missed += 1
        else:
            if enriched_author_meta:
                 logger.info(f"  (Unexpected Enrichment found for {author_name_to_enrich}: {enriched_author_meta})")
            if book_year:
                 logger.info(f"  (Book Year Found: {book_year})")

    metrics.report()

if __name__ == "__main__":
    asyncio.run(run_evaluation())
