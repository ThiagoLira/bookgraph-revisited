import asyncio
import json
import os
import logging
import sys
from pathlib import Path

logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)
logging.getLogger().addHandler(logging.StreamHandler(stream=sys.stdout))

# Add root to path
sys.path.append(os.getcwd())

from lib.bibliography_agent.citation_workflow import CitationWorkflow
from lib.bibliography_agent.agent import build_llm

async def run_real_test():
    input_file = Path("/Users/thlira/Documents/bookgraph-revisited/calibre_outputs/calibre_bookgraph/preprocessed_extracted_citations/61535.json")
    if not input_file.exists():
        print(f"File not found: {input_file}")
        return

    data = json.loads(input_file.read_text(encoding="utf-8"))
    citations = data.get("citations", [])
    print(f"Loaded {len(citations)} citations from {input_file.name}")

    # Config
    books_db = "datasets/books_index.db"
    authors_json = "datasets/goodreads_book_authors.json"
    wiki_db = "datasets/wiki_people_index.db"
    
    # Load .env manually
    env_path = Path(".env")
    if env_path.exists():
        print(f"Loading .env from {env_path.absolute()}")
        with open(env_path, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    os.environ[key] = value

    # LLM Config
    base_url = os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        print("Error: OPENROUTER_API_KEY not found in environment or .env")
        return

    model_id = "qwen/qwen3-next-80b-a3b-instruct"

    print(f"Initializing Workflow with model: {model_id} via {base_url}")
    llm = build_llm(model=model_id, api_key=api_key, base_url=base_url)
    
    workflow = CitationWorkflow(
        books_db_path=books_db,
        authors_path=authors_json,
        wiki_people_path=wiki_db,
        llm=llm,
        verbose=True
    )
    
    results = []
    print(f"Running for all {len(citations)} citations...")
    
    for i, citation in enumerate(citations):
        print(f"\n--- Processing Citation {i+1}/{len(citations)} ---")
        print(f"Raw: {json.dumps(citation, ensure_ascii=False)}")
        try:
            result = await workflow.run(citation=citation)
            print(f"Result: {json.dumps(result, indent=2, ensure_ascii=False)}")
            results.append({
                "citation": citation,
                "result": result
            })
        except Exception as e:
            print(f"Error: {e}")
            results.append({
                "citation": citation,
                "error": str(e)
            })
            
    output_path = Path("workflow_results.json")
    output_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSaved results to {output_path.absolute()}")

if __name__ == "__main__":
    asyncio.run(run_real_test())
