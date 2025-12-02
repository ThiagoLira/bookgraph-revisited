import json
import glob

def scan_authors():
    files = glob.glob('frontend/data/*.json')
    found_solon = False
    found_meno = False
    
    for file_path in files:
        if 'manifest.json' in file_path or 'authors_metadata.json' in file_path:
            continue
            
        try:
            with open(file_path, 'r') as f:
                data = json.load(f)
        except:
            continue

        citations = data.get('citations', [])
        for cit in citations:
            # Check Wikipedia Match
            wiki = cit.get('wikipedia_match')
            if wiki:
                title = wiki.get('title')
                if title == "Solon":
                    print(f"Found Solon as Wikipedia author in {file_path}")
                    found_solon = True
                if title == "Meno":
                    print(f"Found Meno as Wikipedia author in {file_path}")
                    found_meno = True
            
            # Check Goodreads Match
            gr = cit.get('goodreads_match')
            if gr:
                authors = gr.get('authors', [])
                if isinstance(authors, str):
                    authors = [authors]
                for auth in authors:
                    if auth == "Solon":
                        print(f"Found Solon as Goodreads author in {file_path}")
                        found_solon = True
                    if auth == "Meno":
                        print(f"Found Meno as Goodreads author in {file_path}")
                        found_meno = True
                        
    if not found_solon:
        print("Solon not found as author.")
    if not found_meno:
        print("Meno not found as author.")

if __name__ == "__main__":
    scan_authors()
