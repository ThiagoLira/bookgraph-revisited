import json
import glob

def scan_anonymous():
    files = glob.glob('frontend/data/*.json')
    
    for file_path in files:
        if 'manifest.json' in file_path or 'authors_metadata.json' in file_path or 'original_publication_dates.json' in file_path:
            continue
            
        try:
            with open(file_path, 'r') as f:
                data = json.load(f)
        except:
            continue

        # Helper
        def check(gid, title, authors, year):
            if not authors:
                return
            if isinstance(authors, str):
                authors = [authors]
            
            is_anon = False
            for auth in authors:
                if "Anonymous" in auth or "Unknown" in auth:
                    is_anon = True
                    break
            
            if is_anon:
                print(f"GID: {gid} | Title: {title} | Authors: {authors} | Year: {year}")

        # Source
        src = data.get('source', {})
        check(src.get('goodreads_id'), src.get('title'), src.get('authors'), src.get('publication_year'))

        # Citations
        citations = data.get('citations', [])
        for cit in citations:
            match = cit.get('goodreads_match')
            if match:
                check(match.get('book_id'), match.get('title'), match.get('authors'), match.get('publication_year'))

if __name__ == "__main__":
    scan_anonymous()
