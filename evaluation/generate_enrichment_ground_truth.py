
import sys
import json
from pathlib import Path

# Add repo root to path
repo_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repo_root))

from lib.bibliography_agent.bibliography_tool import SQLiteWikiPeopleIndex

def main():
    wiki_db_path = repo_root / "datasets/wiki_people_index.db"
    
    if not wiki_db_path.exists():
        print(f"Error: {wiki_db_path} not found.")
        return

    print(f"Loading Wiki Index from {wiki_db_path}...")
    wiki = SQLiteWikiPeopleIndex(db_path=wiki_db_path)

    # Load existing ground truth to get the list of authors we care about
    gt_path = repo_root / "evaluation/ground_truth.json"
    if not gt_path.exists():
        print("Error: ground_truth.json not found.")
        return
        
    gt_data = json.loads(gt_path.read_text())
    
    enrichment_results = []
    
    print("Generating Enrichment Ground Truth...")
    
    for entry in gt_data:
        citation = entry["citation"]
        expected_match = entry["expected_match"]
        
        # Determine the author name to search for
        author_name = citation.get("author")
        
        # If author is missing in citation but we found a book match, use the author from the match
        if not author_name and expected_match and expected_match.get("match_type") == "book":
             # "book" match might not have "author_names_resolved" directly if it's the simplified dict.
             # The generate_ground_truth script saves "author_ids" list. 
             # We might need to look up the name if we don't have it.
             # But let's check what 'generate_ground_truth.py' actually puts in 'expected_match'.
             # It puts 'title', 'book_id', 'author_ids'. It does NOT put author names in expected_match for books.
             # However, the citation usually has the author name?
             pass

        # If we still don't have an author name, we can't search Wiki easily without looking up the book ID first.
        # But looking at target_citations in generate_ground_truth.py, mostly we have author names.
        
        if not author_name:
            # Skip if we can't identify the author
            enrichment_results.append({
                "citation": citation,
                "enrichment": None,
                "note": "No author name in citation"
            })
            continue

        # Search Wiki
        # We try strict search first or just use the tool's fuzzy search
        matches = wiki.find_people(author_name, limit=1)
        
        enrichment_data = None
        if matches:
            best = matches[0]
            enrichment_data = {
                "wiki_title": best["title"],
                "page_id": best["page_id"],
                "birth_year": best.get("birth_year"),
                "death_year": best.get("death_year"),
                "source": "wiki_index"
            }
            print(f"  FOUND: {author_name} -> {best['title']} ({best.get('birth_year')}-{best.get('death_year')})")
        else:
            print(f"  NOT FOUND: {author_name}")
        
        enrichment_results.append({
            "citation": citation,
            "enrichment": enrichment_data
        })

    output_path = repo_root / "evaluation/enrichment_ground_truth.json"
    output_path.write_text(json.dumps(enrichment_results, indent=2))
    print(f"\nWrote {len(enrichment_results)} enrichment entries to {output_path}")

if __name__ == "__main__":
    main()
