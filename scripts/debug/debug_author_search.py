import sys
import os
from pathlib import Path

# Add root to path
sys.path.append(os.getcwd())

from lib.bibliography_agent.bibliography_tool import GoodreadsAuthorCatalog

def test_author_search():
    print("Initializing GoodreadsAuthorCatalog...")
    catalog = GoodreadsAuthorCatalog("datasets/goodreads_book_authors.json")
    
    print("Testing find_authors with 'query' arg...")
    try:
        results = catalog.find_authors(query="Tolkien", limit=5)
        print(f"Success! Found {len(results)} authors.")
    except Exception as e:
        print(f"Failed with query arg: {e}")

    print("Testing find_authors with 'author' arg (expecting failure)...")
    try:
        results = catalog.find_authors(author="Tolkien", limit=5)
        print(f"Success! Found {len(results)} authors.")
    except Exception as e:
        print(f"Failed with author arg: {e}")

if __name__ == "__main__":
    test_author_search()
