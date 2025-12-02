import json
import glob
import os

def normalize(name):
    if not name:
        return "Unknown"
    if "," in name:
        parts = name.split(",", 1)
        if len(parts) == 2:
            return f"{parts[1].strip()} {parts[0].strip()}"
    return name

def scan_unknown_years():
    # Load authors metadata
    try:
        with open('frontend/data/authors_metadata.json', 'r') as f:
            author_meta = json.load(f)
    except FileNotFoundError:
        print("frontend/data/authors_metadata.json not found.")
        return

    missing_year_counts = {}

    # Iterate through all book JSON files
    files = glob.glob('frontend/data/*.json')
    for file_path in files:
        if 'manifest.json' in file_path or 'authors_metadata.json' in file_path or 'original_publication_dates.json' in file_path:
            continue
            
        try:
            with open(file_path, 'r') as f:
                data = json.load(f)
        except json.JSONDecodeError:
            continue

        # Process source authors
        src_authors = data.get('source', {}).get('authors', [])
        if isinstance(src_authors, str):
            src_authors = [src_authors]
        
        for src_name in src_authors:
            norm_name = normalize(src_name)
            meta = author_meta.get(norm_name, {})
            if not meta.get('birth_year'):
                missing_year_counts[norm_name] = missing_year_counts.get(norm_name, 0) + 1

        # Process citations
        citations = data.get('citations', [])
        for cit in citations:
            target_names = []
            
            # 1. Wikipedia Match
            if cit.get('wikipedia_match') and cit['wikipedia_match'].get('title'):
                target_names.append(cit['wikipedia_match']['title'])
            # 2. Goodreads Match
            elif cit.get('goodreads_match') and cit['goodreads_match'].get('authors'):
                gr_authors = cit['goodreads_match']['authors']
                if isinstance(gr_authors, str):
                    gr_authors = [gr_authors]
                for n in gr_authors:
                    target_names.append(normalize(n))
            
            for target_name in target_names:
                # Note: Frontend doesn't normalize wikipedia titles, but it DOES normalize goodreads authors.
                # However, the `getAuthorNode` function calls `authorMeta[name]`.
                # If the name came from wikipedia title, it is NOT normalized by the `normalize` function in the loop,
                # BUT `getAuthorNode` is called with `targetName`.
                # Wait, looking at frontend code:
                # srcNames = ... .map(normalize) -> getAuthorNode(srcName)
                # targetNames.push(cit.wikipedia_match.title) (NOT NORMALIZED)
                # targetNames.push(normalize(n)) (NORMALIZED)
                # getAuthorNode(targetName)
                
                # So if it's from Wikipedia, it's used as is.
                # If it's from Goodreads, it's normalized.
                
                # Let's replicate that logic exactly.
                
                # Actually, looking at my previous `normalize` function in python, it handles "Last, First".
                # Wikipedia titles are usually "First Last".
                
                meta = author_meta.get(target_name, {})
                if not meta.get('birth_year'):
                    missing_year_counts[target_name] = missing_year_counts.get(target_name, 0) + 1

    # Sort and print top missing
    sorted_missing = sorted(missing_year_counts.items(), key=lambda x: x[1], reverse=True)
    
    print("Top authors missing birth year (causing default to 2025):")
    for name, count in sorted_missing[:50]:
        print(f"{name}: {count}")

if __name__ == "__main__":
    scan_unknown_years()
