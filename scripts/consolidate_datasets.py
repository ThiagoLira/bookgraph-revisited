
import json
import os
from pathlib import Path

def merge_json(source_path, target_path, backup=True):
    source = Path(source_path)
    target = Path(target_path)
    
    if not source.exists():
        print(f"Source {source} not found. Skipping.")
        return

    print(f"Loading source: {source}")
    try:
        source_data = json.loads(source.read_text())
    except Exception as e:
        print(f"Error loading source: {e}")
        return

    target_data = {}
    if target.exists():
        print(f"Loading target: {target}")
        try:
            target_data = json.loads(target.read_text())
        except Exception as e:
            print(f"Error loading target: {e}")
    else:
        print(f"Target {target} does not exist. Creating new.")

    # Merge
    print(f"Merging {len(source_data)} entries into {len(target_data)} existing entries...")
    target_data.update(source_data)
    
    # Save
    print(f"Saving {len(target_data)} entries to {target}...")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(target_data, indent=2, sort_keys=True))
    print("Done.")

def main():
    repo_root = Path(".").resolve()
    
    # Merge Dates
    merge_json(
        repo_root / "frontend/data/stalin_library/original_publication_dates.json",
        repo_root / "datasets/original_publication_dates.json"
    )
    
    # Merge Authors
    merge_json(
        repo_root / "frontend/data/stalin_library/authors_metadata.json",
        repo_root / "datasets/authors_metadata.json"
    )

if __name__ == "__main__":
    main()
