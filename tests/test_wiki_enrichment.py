
import sys
import json
from pathlib import Path
from pprint import pprint

# Add repo root to path
repo_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repo_root))

from lib.bibliography_agent.bibliography_tool import SQLiteWikiPeopleIndex

def main():
    db_path = "datasets/wiki_people_index.db"
    
    if not Path(db_path).exists():
        print(f"Error: {db_path} not found.")
        return

    print(f"Loading Wiki Index from {db_path}...")
    wiki = SQLiteWikiPeopleIndex(db_path=db_path)
    
    test_cases = [
        "Plato",                       # Famous, likely in Wiki
        "George Gilder",               # Has override in authors_metadata.json
        "David Foster Wallace",        # Author, check if in Wiki
        "Robert Coover",               # Has override
        "NonExistentPerson12345",      # Should fail
    ]

    print("\n--- Testing Wiki People Lookup ---")
    for name in test_cases:
        print(f"\nQuery: '{name}'")
        matches = wiki.find_people(name, limit=1)
        if matches:
            m = matches[0]
            print(f"  Found: {m['title']} (ID: {m['page_id']})")
            print(f"  Dates: {m.get('birth_year')} - {m.get('death_year')}")
            print(f"  Categories: {m.get('categories')[:2]}") # Show first few
        else:
            print("  Not found.")

if __name__ == "__main__":
    main()
