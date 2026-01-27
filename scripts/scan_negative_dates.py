
import json
from pathlib import Path

base_dir = Path("outputs/folder_runs/dfw_20260126/final_citations_metadata_goodreads")

for json_file in base_dir.glob("*.json"):
    try:
        data = json.loads(json_file.read_text())
        for citation in data.get("citations", []):
            gm = citation.get("goodreads_match", {})
            if not gm: continue
            
            am = gm.get("author_meta", {})
            b_year = am.get("birth_year")
            
            if b_year and isinstance(b_year, int) and b_year < 0:
                name = gm.get("name", "Unknown")
                print(f"File: {json_file.name} | Author: {name} | Year: {b_year}")
                
    except Exception as e:
        print(f"Error {json_file}: {e}")
