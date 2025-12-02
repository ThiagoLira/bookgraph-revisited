import json
import glob
import os

def scan_missing_dates():
    # Load existing dates
    try:
        with open('frontend/data/original_publication_dates.json', 'r') as f:
            pub_dates = json.load(f)
    except FileNotFoundError:
        pub_dates = {}

    missing_dates = {} # Use dict to avoid duplicates, key=gid

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

        # Check Source Book
        src = data.get('source', {})
        gid = src.get('goodreads_id')
        title = src.get('title')
        
        has_date = False
        if gid and gid in pub_dates and pub_dates[gid]:
            has_date = True
        elif src.get('publication_year'):
            has_date = True
        elif src.get('goodreads', {}).get('publication_year'):
             has_date = True
             
        if gid and not has_date:
            missing_dates[gid] = title

        # Check Citations
        citations = data.get('citations', [])
        for cit in citations:
            match = cit.get('goodreads_match')
            if not match:
                continue
            
            # Check if it's a book citation
            # The structure in frontend: 
            # const gid = meta.goodreads_id || (meta.goodreads_match ? meta.goodreads_match.book_id : null);
            
            c_gid = match.get('book_id')
            c_title = match.get('title')
            
            if not c_gid:
                continue
                
            c_has_date = False
            if str(c_gid) in pub_dates and pub_dates[str(c_gid)]:
                c_has_date = True
            elif match.get('publication_year'):
                c_has_date = True
            
            if not c_has_date:
                # Only add if we haven't found it yet or if we have a better title now
                if str(c_gid) not in missing_dates:
                    missing_dates[str(c_gid)] = c_title

    print(f"Found {len(missing_dates)} books (source or cited) with completely missing publication dates:")
    for gid, title in list(missing_dates.items())[:50]: # Limit output
        print(f"GID: {gid}, Title: {title}")

if __name__ == "__main__":
    scan_missing_dates()
