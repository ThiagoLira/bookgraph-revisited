
import json
from pathlib import Path

# Manual overrides for confirmed issues
MANUAL_FIXES = {
    "William Shakespeare": {"birth_year": 1564, "death_year": 1616},
    "Blaise Pascal": {"birth_year": 1623, "death_year": 1662},
    "Otto von Bismarck": {"birth_year": 1815, "death_year": 1898},
    "Augustine of Hippo": {"birth_year": 354, "death_year": 430},
    "Fyodor Dostoyevsky": {"birth_year": 1821, "death_year": 1881},
    "George Orwell": {"birth_year": 1903, "death_year": 1950},
    "Northrop Frye": {"birth_year": 1912, "death_year": 1991},
    "Ernest Renan": {"birth_year": 1823, "death_year": 1892}
}

def main():
    repo_root = Path(".").resolve()
    cache_path = repo_root / "datasets/authors_metadata.json"
    dfw_dir = repo_root / "outputs/folder_runs/dfw_20260126/final_citations_metadata_goodreads"
    
    # Load cache
    if cache_path.exists():
        print(f"Loading cache from {cache_path}")
        cache = json.loads(cache_path.read_text())
    else:
        print("Warning: Cache not found.")
        cache = {}

    # Iterate DFW files
    for json_file in dfw_dir.glob("*.json"):
        print(f"Processing {json_file.name}...")
        changed = False
        try:
            data = json.loads(json_file.read_text())
            
            for citation in data.get("citations", []):
                gm = citation.get("goodreads_match")
                if not gm: continue
                
                name = gm.get("name")
                wiki_title = gm.get("wikipedia_match", {}).get("title")
                name = name or wiki_title or "Unknown"
                
                am = gm.get("author_meta", {})

                # Check for negative years
                b_year = am.get("birth_year")
                if b_year is not None and isinstance(b_year, int) and b_year < 0:
                    original_year = b_year
                    name = name or "Unknown"
                    
                    # 1. Manual Fix
                    if name in MANUAL_FIXES:
                        fix = MANUAL_FIXES[name]
                        am.update(fix)
                        print(f"  [FIX] {name}: {original_year} -> {fix['birth_year']} (Manual)")
                        changed = True
                        
                    # 2. Cache Fix
                    elif name in cache:
                        cached_meta = cache[name]
                        if (cached_meta.get("birth_year") or 0) > 0:
                            am.update(cached_meta)
                            print(f"  [FIX] {name}: {original_year} -> {cached_meta['birth_year']} (Cache)")
                            changed = True
                            
                    # 3. Simple sign flip if it looks like a modern date (simple heuristic)
                    elif -2025 <= original_year <= -1000:
                         # Risky but efficient for this specific mess
                         am["birth_year"] = abs(original_year)
                         if am.get("death_year"): am["death_year"] = abs(am["death_year"])
                         print(f"  [FIX] {name}: {original_year} -> {am['birth_year']} (Heuristic)")
                         changed = True
                         
            if changed:
                json_file.write_text(json.dumps(data, indent=2))
                print(f"Saved {json_file.name}")
                
        except Exception as e:
            print(f"Error processing {json_file.name}: {e}")

if __name__ == "__main__":
    main()
