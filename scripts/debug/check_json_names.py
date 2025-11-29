import json
import sys
from pathlib import Path

def check_json(path):
    data = json.loads(Path(path).read_text())
    
    print(f"Checking {path}...")
    
    # Check source
    src = data.get("source", {})
    print(f"Source: {src.get('title')} by {src.get('authors')}")
    if not src.get("authors"):
        print("WARNING: Source has no authors!")
        
    citations = data.get("citations", [])
    print(f"Citations: {len(citations)}")
    
    unknown_count = 0
    missing_name_count = 0
    
    for i, cit in enumerate(citations):
        edge = cit.get("edge", {})
        match = cit.get("goodreads_match", {})
        
        target_type = edge.get("target_type")
        
        if target_type == "author":
            # Should have name in match
            name = match.get("name") or match.get("author")
            if not name:
                print(f"Citation {i}: target_type='author' but no name/author in goodreads_match! Raw: {cit.get('raw')}")
                missing_name_count += 1
                
        elif target_type == "book":
             # Should have title in match
             title = match.get("title")
             if not title:
                 print(f"Citation {i}: target_type='book' but no title in goodreads_match!")
                 
    print(f"Found {missing_name_count} citations with missing names.")

if __name__ == "__main__":
    check_json(sys.argv[1])
