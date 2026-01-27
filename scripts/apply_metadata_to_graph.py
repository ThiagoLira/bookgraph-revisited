
import json
import sys
from pathlib import Path

def apply_metadata(library_dir):
    lib_path = Path(library_dir)
    if not lib_path.exists():
        print(f"Directory {lib_path} not found.")
        return

    metadata_path = lib_path / "authors_metadata.json"
    graph_path = lib_path / "graph.json" # Try graph.json first
    
    if not graph_path.exists():
        # Fallback to checking all json files if graph.json doesn't exist (e.g. DFW case)
        target_files = list(lib_path.glob("*.json"))
        target_files = [f for f in target_files if f.name not in ["authors_metadata.json", "manifest.json", "datasets.json"]]
    else:
        target_files = [graph_path]

    if not metadata_path.exists():
        print(f"Metadata file {metadata_path} not found.")
        return
        
    print(f"Loading metadata from {metadata_path}")
    metadata = json.loads(metadata_path.read_text())
    
    # Normalize keys in metadata for easier lookup if needed, but assuming exact match for now
    
    total_updates = 0
    
    for json_file in target_files:
        print(f"Processing {json_file.name}...")
        try:
            data = json.loads(json_file.read_text())
            changed = False
            
            citations = data.get("citations", [])
            for citation in citations:
                gm = citation.get("goodreads_match")
                if not gm: continue
                
                # Check based on name
                name = gm.get("name")
                
                # Fallback to key in raw author or canonical_author
                if not name:
                    name = citation.get("raw", {}).get("author")
                
                # Check aliases or direct match
                # Some entries in manual_run have "Stalin", but metadata has "Stalin"
                # Some might have "Stalin" in raw, but "Joseph Stalin" in goodreads_match
                
                # We try multiple candidates
                candidates = [name]
                if gm.get("name"): candidates.append(gm.get("name"))
                if citation.get("raw", {}).get("canonical_author"): candidates.append(citation.get("raw", {}).get("canonical_author"))
                
                matched = False
                for candidate in candidates:
                    if not candidate: continue
                    if candidate in metadata:
                        cached = metadata[candidate]
                        current = gm.get("author_meta", {})
                        
                        # Apply update
                        current.update(cached)
                        gm["author_meta"] = current
                        
                        # Force name update if we have a "better" name in metadata context (e.g. overrides)
                        # We use the key as the source of truth if it differs from the current name
                        if candidate in ["Struve", "Stalin", "I. V. Stalin", "Joseph Stalin"]:
                             if candidate == "Struve":
                                 gm["name"] = "Friedrich Georg Wilhelm von Struve"
                             elif "Stalin" in candidate:
                                 gm["name"] = "Joseph Stalin"
                        
                        # Synthesize wikipedia_match if missing or if we want to force dates into it
                        # The frontend likely relies on wikipedia_match for dates/timeline
                        if not gm.get("wikipedia_match") or candidate in ["Struve", "Stalin"]:
                             wm = gm.get("wikipedia_match", {})
                             if not wm: wm = {}
                             
                             wm["birth_year"] = cached.get("birth_year")
                             wm["death_year"] = cached.get("death_year")
                             
                             if candidate == "Struve":
                                 wm["title"] = "Friedrich Georg Wilhelm von Struve"
                             elif "Stalin" in candidate:
                                 wm["title"] = "Joseph Stalin"
                                 
                             gm["wikipedia_match"] = wm

                        changed = True
                        matched = True
                        total_updates += 1
                        # print(f"  Updated {candidate}")
                        break
                
                if not matched and "Stalin" in str(candidates):
                     # Force fallback for Stalin if explicit match failed but string is there
                     if "Stalin" in metadata:
                         gm["author_meta"] = metadata["Stalin"]
                         changed = True
                         total_updates += 1
                
                # Also handle the variants like "I. V. Stalin" -> "Stalin" entry in metadata?
                # The metadata file seems to have entries for variants too, e.g. "I. V. Stalin"
                
                # What if the name in goodreads_match is "Joseph Stalin" but metadata has "Stalin"?
                # I fixed "Joseph Stalin" in metadata too in previous step.
                           
            if changed:
                json_file.write_text(json.dumps(data, indent=2))
                print(f"  Saved {json_file.name} with updates.")
            else:
                print(f"  No changes for {json_file.name}")
                
        except Exception as e:
            print(f"Error processing {json_file}: {e}")

    print(f"Total updates applied: {total_updates}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        apply_metadata(sys.argv[1])
    else:
        print("Usage: python apply_metadata_to_graph.py <library_dir>")
