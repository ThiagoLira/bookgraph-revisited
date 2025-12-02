import json
import glob
import os
from collections import Counter

def scan_missing_metadata():
    files = glob.glob("frontend/data/*.json")
    missing_wiki_match = Counter()
    missing_dates = Counter()
    
    for fpath in files:
        if "manifest" in fpath or "metadata" in fpath or "dates" in fpath: continue
        
        try:
            with open(fpath, "r") as f:
                data = json.load(f)
        except: continue
        
        citations = data.get("citations", [])
        for cit in citations:
            # Check for missing Wikipedia match
            if not cit.get("wikipedia_match"):
                # Try to get author name from goodreads or raw
                name = None
                if cit.get("goodreads_match"):
                    authors = cit["goodreads_match"].get("authors", [])
                    if authors:
                        name = authors[0]
                
                if not name and cit.get("raw"):
                    name = cit["raw"].get("canonical_author") or cit["raw"].get("author")
                
                if name:
                    missing_wiki_match[name] += 1
            
            # Check for missing dates in existing Wikipedia match
            else:
                wiki = cit["wikipedia_match"]
                if wiki.get("birth_year") is None:
                    missing_dates[wiki.get("title")] += 1

    print("Top authors missing Wikipedia match:")
    for name, count in missing_wiki_match.most_common(20):
        print(f"{name}: {count}")
        
    print("\nTop authors with Wikipedia match but missing birth year:")
    for name, count in missing_dates.most_common(20):
        print(f"{name}: {count}")

if __name__ == "__main__":
    scan_missing_metadata()
