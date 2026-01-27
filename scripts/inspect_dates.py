
import json
from pathlib import Path

base_dir = Path("outputs/folder_runs/dfw_20260126/final_citations_metadata_goodreads")
targets = ["Shakespeare", "Bismarck", "Pascal"]

for json_file in base_dir.glob("*.json"):
    print(f"Checking {json_file.name}...")
    try:
        data = json.loads(json_file.read_text())
        for citation in data.get("citations", []):
            # Check raw author
            raw_author = citation.get("raw", {}).get("author", "")
            
            # Check resolved person/author
            edge = citation.get("edge", {})
            person = edge.get("target_person")
            
            found = False
            for target in targets:
                if target.lower() in str(raw_author).lower():
                    found = True
                if person and target.lower() in person.get("title", "").lower():
                    found = True
            
            if found:
                print(f"  Found match: {raw_author}")
                if person:
                    print(f"    Resolved Person: {person.get('title')}")
                    print(f"    Birth: {person.get('birth_year')}")
                    print(f"    Death: {person.get('death_year')}")
                
                   
    except Exception as e:
        print(f"Error reading {json_file}: {e}")
