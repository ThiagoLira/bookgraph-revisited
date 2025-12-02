import json
import glob

def scan_aeneid():
    files = glob.glob('frontend/data/*.json')
    
    for file_path in files:
        if 'manifest.json' in file_path or 'authors_metadata.json' in file_path or 'original_publication_dates.json' in file_path:
            continue
            
        try:
            with open(file_path, 'r') as f:
                data = json.load(f)
        except:
            continue

        citations = data.get('citations', [])
        for cit in citations:
            match = cit.get('goodreads_match')
            if match:
                title = match.get('title', '')
                if 'Decline and Fall' in title:
                    print(f"File: {file_path}")
                    print(f"Title: {title}")
                    print(f"GID: {match.get('book_id')}")
                    print("-" * 20)

if __name__ == "__main__":
    scan_aeneid()
