
import json
import sys
from pathlib import Path

def scan_dir(directory):
    base_dir = Path(directory)
    if not base_dir.exists():
        print(f"Directory not found: {base_dir}")
        return

    print(f"Scanning {base_dir} for negative dates...")
    for json_file in base_dir.glob("*.json"):
        if json_file.name in ["manifest.json", "graph.json"]: continue
        try:
            data = json.loads(json_file.read_text())
            for citation in data.get("citations", []):
                gm = citation.get("goodreads_match", {})
                if not gm: continue
                
                # Try author_meta first
                am = gm.get("author_meta", {})
                b_year = am.get("birth_year")
                
                # Try wikipedia_match if no author_meta
                if b_year is None:
                     wm = gm.get("wikipedia_match", {})
                     if wm:
                         b_year = wm.get("birth_year")

                if b_year is not None and isinstance(b_year, int) and b_year < 0:
                    name = gm.get("name")
                    wiki_title = gm.get("wikipedia_match", {}).get("title")
                    name = name or wiki_title or "Unknown"
                    print(f"File: {json_file.name} | Author: {name} | Year: {b_year}")
                    
        except Exception as e:
            print(f"Error {json_file}: {e}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        scan_dir(sys.argv[1])
    else:
        print("Usage: python scan_dates_generic.py <directory>")
