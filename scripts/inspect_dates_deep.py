
import json
from pathlib import Path

base_dir = Path("outputs/folder_runs/dfw_20260126/final_citations_metadata_goodreads")
targets = ["Shakespeare", "Bismarck", "Pascal"]

for json_file in base_dir.glob("*.json"):
    print(f"Checking {json_file.name}...")
    try:
        data = json.loads(json_file.read_text())
        for citation in data.get("citations", []):
            raw_author = citation.get("raw", {}).get("author", "")
            edge = citation.get("edge", {})
            person = edge.get("target_person")
            
            found = False
            for target in targets:
                if target.lower() in str(raw_author).lower():
                    found = True
                if person and target.lower() in person.get("title", "").lower():
                    found = True
            
            if found:
                print(f"Found match: {raw_author}")
                print(json.dumps(citation, indent=2))
                   
    except Exception as e:
        print(f"Error reading {json_file}: {e}")
