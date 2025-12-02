import json
import glob
import os
import argparse

def extract_ids():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default="frontend/data", help="Source directory containing JSON files")
    args = parser.parse_args()
    
    source_dir = args.source
        
    print(f"Scanning files in {source_dir}...")
    
    json_files = glob.glob(os.path.join(source_dir, "*.json"))
    all_ids = set()
    
    for fpath in json_files:
        if fpath.endswith("manifest.json"):
            continue
            
        try:
            with open(fpath, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
                # 1. Source ID
                if "source" in data:
                    sid = data["source"].get("goodreads_id")
                    if sid:
                        all_ids.add(str(sid))
                    # Also check nested goodreads object just in case
                    if "goodreads" in data["source"]:
                        sid2 = data["source"]["goodreads"].get("book_id")
                        if sid2:
                            all_ids.add(str(sid2))
                            
                # 2. Citation IDs
                if "citations" in data:
                    for cit in data["citations"]:
                        # Check goodreads_match
                        if "goodreads_match" in cit and cit["goodreads_match"]:
                            bid = cit["goodreads_match"].get("book_id")
                            if bid:
                                all_ids.add(str(bid))
                                
                        # Check metadata (sometimes used in other formats)
                        if "metadata" in cit and cit["metadata"]:
                            bid = cit["metadata"].get("book_id")
                            if bid:
                                all_ids.add(str(bid))
                                
        except Exception as e:
            print(f"Error reading {fpath}: {e}")
            
    # Write to file
    output_file = "all_goodreads_ids.txt"
    sorted_ids = sorted(list(all_ids))
    
    with open(output_file, 'w', encoding='utf-8') as f:
        for bid in sorted_ids:
            f.write(f"{bid}\n")
            
    print(f"Extracted {len(sorted_ids)} unique IDs to {output_file}")

if __name__ == "__main__":
    extract_ids()
