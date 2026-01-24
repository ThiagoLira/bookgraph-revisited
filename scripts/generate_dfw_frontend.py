import asyncio
import json
import logging
import sys
from pathlib import Path

# Add repo root to sys.path
repo_root = Path(__file__).resolve().parent.parent
sys.path.append(str(repo_root))

from typing import Dict, Any

from llama_index.core import Settings
from lib.bibliography_agent.citation_workflow import CitationWorkflow
from lib.bibliography_agent.llm_utils import build_llm
from lib.metadata_enricher import MetadataEnricher, build_llm as build_enricher_llm
from lib.logging_config import setup_logging

# Setup Logging
import os

# ...

setup_logging(Path("frontend/data/dfw_test"), verbose=True)
logger = logging.getLogger(__name__)

async def main():
    repo_root = Path(__file__).resolve().parent.parent
    
    # Load .env manually to get keys
    env_path = repo_root / ".env"
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    base_url = os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    model = "openai/gpt-4o-mini" # or similar

    if not api_key and env_path.exists():
        logger.info(f"Loading .env from {env_path}")
        with open(env_path) as f:
             for line in f:
                if line.strip() and not line.startswith("#") and "=" in line:
                    k, v = line.strip().split("=", 1)
                    if k == "OPENROUTER_API_KEY":
                        api_key = v.strip()

    if not api_key:
        logger.error("No API key found")
        sys.exit(1)

    # Configuration
    books_db = repo_root / "datasets/books_index.db"
    people_db = repo_root / "datasets/wiki_people_index.db"
    authors_json = repo_root / "datasets/goodreads_book_authors.json"
    
    llm = build_llm(model=model, api_key=api_key, base_url=base_url)

    # Init Workflow
    workflow = CitationWorkflow(
        books_db_path=str(books_db),
        authors_path=str(authors_json),
        wiki_people_path=str(people_db),
        llm=llm,
        verbose=True
    )
    
    # Init Enricher
    enricher_llm = build_llm(model=model, api_key=api_key, base_url=base_url)
    
    # Use temp paths to force live lookup
    dates_json = repo_root / "datasets/temp_dfw_dates.json"
    author_meta_json = repo_root / "datasets/temp_dfw_authors.json"

    if dates_json.exists(): dates_json.unlink()
    if author_meta_json.exists(): author_meta_json.unlink()
    
    enricher = MetadataEnricher(
        dates_path=str(dates_json),
        authors_path=str(author_meta_json),
        llm=enricher_llm,
        auto_update=True
    )

    # Load Ground Truth
    gt_path = repo_root / "evaluation/ground_truth.json"
    if not gt_path.exists():
        logger.error("Ground truth file not found")
        sys.exit(1)
        
    gt_entries = json.loads(gt_path.read_text())
    
    # Output structure
    output_data = {
        "source": {
            "title": "E Unibus Pluram: Television and U.S. Fiction",
            "authors": ["David Foster Wallace"],
            "goodreads_id": "dfw_test",
            "calibre_id": None
        },
        "citations": []
    }
    
    logger.info(f"Processing {len(gt_entries)} citations with concurrency...")
    
    semaphore = asyncio.Semaphore(10) # 10 concurrent requests
    
    async def process_entry(entry):
        async with semaphore:
            cit = entry["citation"]
            logger.info(f"Processing: {cit.get('title')} / {cit.get('author')}")
            try:
                result = await workflow.run(citation=cit)
                match_type = result.get("match_type")
                metadata = result.get("metadata", {})
                
                # Enrich
                title = metadata.get("title") or cit.get("title")
                # Author logic
                author = None
                if metadata.get("authors"):
                     author = metadata.get("authors")[0]
                elif cit.get("author"):
                     author = cit.get("author")

                book_id = metadata.get("goodreads_id") or metadata.get("book_id")
                
                if match_type == "book":
                    await enricher.enrich_book(str(book_id) if book_id else None, title, author)
                
                # Enrich Author
                author_to_enrich = None
                if match_type == "book":
                     authors = metadata.get("authors", [])
                     if authors: author_to_enrich = authors[0]
                elif match_type in ["author", "person"]:
                     author_to_enrich = metadata.get("name") or cit.get("author")
                
                enriched_author = {}
                if author_to_enrich:
                     enriched_author = await enricher.enrich_author(author_to_enrich)
                     if enriched_author:
                         metadata["author_meta"] = enriched_author

                # Build Citation Object compatible with frontend
                citation_obj = {
                    "raw": cit,
                    "goodreads_match": None,
                    "wikipedia_match": None,
                    "edge": {
                        "target_type": match_type,
                        "target_book_id": metadata.get("book_id"),
                        "target_author_ids": [metadata.get("author_id")] if metadata.get("author_id") else ([] if metadata.get("author_ids") is None else metadata.get("author_ids")),
                        "target_person": None
                    }
                }
                
                if match_type == "book":
                    citation_obj["goodreads_match"] = metadata
                    if enriched_author:
                        citation_obj["goodreads_match"]["author_meta"] = enriched_author
                        
                elif match_type == "author":
                    citation_obj["goodreads_match"] = metadata
                    if enriched_author:
                        citation_obj["goodreads_match"]["author_meta"] = enriched_author

                elif match_type == "person":
                     citation_obj["wikipedia_match"] = metadata
                     citation_obj["edge"]["target_person"] = metadata

                return citation_obj
                
            except Exception as e:
                logger.error(f"Error processing {cit}: {e}", exc_info=True)
                return None

    tasks = [process_entry(entry) for entry in gt_entries]
    results = await asyncio.gather(*tasks)
    
    # Filter None results
    output_data["citations"] = [r for r in results if r is not None]
            
    # Save Output
    output_path = Path("frontend/data/dfw_test/graph.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output_data, indent=2))
    logger.info(f"Saved DFW graph data to {output_path}")

if __name__ == "__main__":
    asyncio.run(main())
