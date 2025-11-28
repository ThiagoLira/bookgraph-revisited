import asyncio
import os
import logging
import sys
from pathlib import Path

logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)
logging.getLogger().addHandler(logging.StreamHandler(stream=sys.stdout))

sys.path.append(os.getcwd())

from lib.bibliography_agent.citation_workflow import CitationWorkflow
from lib.bibliography_agent.agent import build_llm

async def run_debug_test():
    citation = {"title": "Of the Farm", "author": "John Updike"}
    print(f"Testing citation: {citation}")

    # Config
    books_db = "goodreads_data/books_index.db"
    authors_json = "goodreads_data/goodreads_book_authors.json"
    wiki_db = "goodreads_data/wiki_people_index.db"
    
    # Load .env
    env_path = Path(".env")
    if env_path.exists():
        with open(env_path, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    os.environ[key] = value

    # LLM Config
    base_url = os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    api_key = os.environ.get("OPENROUTER_API_KEY")
    model_id = "qwen/qwen3-next-80b-a3b-instruct"

    llm = build_llm(model=model_id, api_key=api_key, base_url=base_url)
    
    workflow = CitationWorkflow(
        books_db_path=books_db,
        authors_path=authors_json,
        wiki_people_path=wiki_db,
        llm=llm,
        verbose=True
    )
    
    try:
        result = await workflow.run(citation=citation)
        print(f"Result: {result}")
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(run_debug_test())
