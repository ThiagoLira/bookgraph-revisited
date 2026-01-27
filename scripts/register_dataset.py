#!/usr/bin/env python3
"""
Registers a pipeline output directory as a dataset in the frontend.

Usage:
    python scripts/register_dataset.py <PIPELINE_OUTPUT_DIR> --name "Display Name" [--target-dir frontend/data/my_book]

Example:
    python scripts/register_dataset.py outputs/single_runs/calvino_classics --name "Calvino: Classics"
"""

import argparse
import json
import shutil
import sys
from pathlib import Path

def parse_args():
    parser = argparse.ArgumentParser(description="Register a dataset for the frontend.")
    parser.add_argument("input_dir", type=Path, help="Path to the pipeline output directory (containing final_citations...).")
    parser.add_argument("--name", required=True, help="Display name for the dataset in the UI.")
    parser.add_argument("--target-dir", type=Path, help="Where to store the frontend data (default: inside input_dir or frontend/data).")
    return parser.parse_args()

def main():
    args = parse_args()
    repo_root = Path(__file__).resolve().parent.parent

    if not args.input_dir.exists():
        print(f"Error: Input directory {args.input_dir} does not exist.")
        sys.exit(1)

    # 1. Locate the final JSON file
    # It might be in final_citations_metadata_goodreads/*.json
    final_dir = args.input_dir / "final_citations_metadata_goodreads"
    if not final_dir.exists():
         # Fallback: maybe the input dir IS the final dir? or flat structure?
         # Let's check for any json file looking like a graph
         final_dir = args.input_dir

    json_files = list(final_dir.glob("*.json"))
    # Filter out manifest.json or graph.json if they exist
    json_files = [f for f in json_files if f.name not in ["manifest.json", "graph.json", "datasets.json"]]
    
    if not json_files:
        print(f"Error: No suitable JSON files found in {final_dir}.")
        sys.exit(1)
        
    # 3. Copy files and generate manifest
    manifest_files = []
    
    print(f"Found {len(json_files)} JSON files to register.")
    
    # Determine target directory once
    if args.target_dir:
         dest_dir = args.target_dir
    else:
         # Better: derive from name
         sanitized_name = args.name.lower().replace(" ", "_").replace(":", "")
         dest_dir = repo_root / "frontend" / "data" / sanitized_name

    if not dest_dir.exists():
        dest_dir.mkdir(parents=True)

    for src in json_files:
        if len(json_files) == 1:
            # Single file case: rename to graph.json for convention (optional but clean)
            dst_name = "graph.json"
        else:
            # Multi file case: keep original names
            dst_name = src.name
            
        dst_path = dest_dir / dst_name
        print(f"Copying {src.name} -> {dst_name}")
        shutil.copy2(src, dst_path)
        manifest_files.append(dst_name)

    # 4. Create manifest.json
    manifest_path = dest_dir / "manifest.json"
    with open(manifest_path, "w") as f:
        json.dump(manifest_files, f, indent=4)
    print(f"Created {manifest_path} with {len(manifest_files)} entries.")

    # 5. Update frontend/datasets.json
    datasets_json_path = repo_root / "frontend" / "datasets.json"
    
    if not datasets_json_path.exists():
        print("Error: frontend/datasets.json not found.")
        sys.exit(1)
        
    with open(datasets_json_path, "r") as f:
        datasets = json.load(f)
        
    # Relative path for frontend
    # If target_dir is absolute, make it relative to frontend/
    try:
        frontend_root = repo_root / "frontend"
        rel_path = "./" + str(dest_dir.relative_to(frontend_root))
    except ValueError:
        # Fallback if not inside frontend
        print(f"Warning: Target dir {dest_dir} is not inside frontend/. UI might not load it.")
        rel_path = str(dest_dir)

    # Check if exists
    existing = next((d for d in datasets if d["path"] == rel_path), None)
    if existing:
        existing["name"] = args.name
        print(f"Updated existing entry for {rel_path}")
    else:
        datasets.append({
            "name": args.name,
            "path": rel_path
        })
        print(f"Added new entry for {rel_path}")
        
    with open(datasets_json_path, "w") as f:
        json.dump(datasets, f, indent=4)
        
    print("Done. Frontend updated.")

if __name__ == "__main__":
    main()
