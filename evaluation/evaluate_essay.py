
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
        print("\n=== Evaluation Report ===")
        print(f"Total Citations: {self.total}")
        print(f"Processed: {self.processed}")
        print(f"Goodreads Matches Found: {self.goodreads_hits}")
        print(f"Enrichment Matches Found: {self.enrichment_hits}")
        print(f"Enrichment Missed (Expected but not found): {self.enrichment_missed}")
        print("=========================\n")

def fuzzy_match(s1: str, s2: str) -> bool:
    if not s1 or not s2: return False
    return s1.lower() in s2.lower() or s2.lower() in s1.lower()

async def run_evaluation():
    print("Starting Evaluation Pipeline...")
    
    # Configuration
    books_db = repo_root / "datasets/books_index.db"
    authors_file = repo_root / "datasets/goodreads_book_authors.json"
    wiki_db = repo_root / "datasets/wiki_people_index.db"
    
    # Load input (Simulated Preprocessed Citations)
    input_path = repo_root / "calibre_outputs/manual_test/preprocessed_extracted_citations/1000.json"
    if not input_path.exists():
        print(f"Error: Input file {input_path} not found.")
        return

    input_data = json.loads(input_path.read_text())
    citations = input_data.get("citations", [])
    
    # Load Ground Truth
    gt_path = repo_root / "evaluation/ground_truth.json"
    enrich_gt_path = repo_root / "evaluation/enrichment_ground_truth.json"
    
    gt_data = json.loads(gt_path.read_text())
    enrich_data = json.loads(enrich_gt_path.read_text())
    
    # Initialize Workflow
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    base_url = os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    model = "openai/gpt-oss-120b"
    
    # Load .env if key missing
    if not api_key:
        env_path = repo_root / ".env"
        if env_path.exists():
            print(f"Loading .env from {env_path}")
            with open(env_path) as f:
                for line in f:
                    if line.strip() and not line.startswith("#") and "=" in line:
                        k, v = line.strip().split("=", 1)
                        if k == "OPENROUTER_API_KEY":
                            api_key = v
    
    # Manually build LLM with the fix
    from llama_index.llms.openai_like import OpenAILike
    llm = OpenAILike(
        model=model,
        api_key=api_key,
        api_base=base_url,
        is_chat_model=True,
        is_function_calling_model=False, # The Fix
        context_window=131072,
        max_tokens=1024
    )
    
    workflow = CitationWorkflow(
        books_db_path=str(books_db),
        authors_path=str(authors_file),
        wiki_people_path=str(wiki_db),
        llm=llm,
        verbose=False # Set to True for debugging
    )
    
    metrics = Metrics()
    metrics.total = len(citations)
    
    print(f"Processing {len(citations)} citations...")
    
    for i, cit in enumerate(citations):
        print(f"[{i+1}/{len(citations)}] Processing: {cit.get('title', 'Unknown')} / {cit.get('author', 'Unknown')}")
        
        # 1. Run Workflow
        try:
            result = await workflow.run(citation=cit)
        except Exception as e:
            print(f"  Error running workflow: {e}")
            continue

        metrics.processed += 1
        
        # 2. Analyze Result
        match_type = result.get("match_type")
        metadata = result.get("metadata", {})
        
        print(f"  Result: {match_type}")
        if match_type in ["book", "author"]:
             metrics.goodreads_hits += 1
        
        # 3. Check Enrichment
        # Did we get wiki data?
        wiki_match = metadata.get("wikipedia_match")
        
        # Find expected enrichment from Ground Truth
        # We need to map 'cit' to 'enrich_data' entry
        expected_enrichment = None
        for entry in enrich_data:
            c = entry["citation"]
            # Flexible matching
            t_match = (c.get("title") == cit.get("title"))
            if not c.get("title") and not cit.get("title"): t_match = True
            
            a_match = (c.get("author") == cit.get("author"))
            
            if t_match and a_match:
                expected_enrichment = entry.get("enrichment")
                break
        
        if wiki_match:
            print(f"  Enrichment: FOUND ({wiki_match.get('title')})")
            metrics.enrichment_hits += 1
        else:
            print("  Enrichment: NONE")
            
        if expected_enrichment and not wiki_match:
            print(f"  MISSING ENRICHMENT! Expected: {expected_enrichment.get('wiki_title')}")
            metrics.enrichment_missed += 1
            
    metrics.report()

if __name__ == "__main__":
    asyncio.run(run_evaluation())
