import json
import glob
import re

def parse_year(date_val):
    if date_val is None:
        return None
    if isinstance(date_val, int):
        return date_val
    s = str(date_val)
    if "BC" in s:
        try:
            return -int(re.sub(r'\D', '', s))
        except:
            return None
    match = re.match(r'^-?(\d{4})', s)
    if match:
        return int(match.group(1))
    match = re.match(r'^(-?\d+)', s)
    if match:
        return int(match.group(1))
    return None

def scan_future():
    # Load Overrides
    try:
        with open('frontend/data/original_publication_dates.json', 'r') as f:
            overrides = json.load(f)
    except:
        overrides = {}

    anachronisms = []
    unknowns = []

    files = glob.glob('frontend/data/*.json')
    
    # First pass: Build a map of GID -> Year for all books in the dataset
    # This is needed because sometimes the citation object itself doesn't have the year, 
    # but we might know it from another file or the overrides.
    gid_to_year = {}
    
    # Pre-fill with overrides
    for gid, date_str in overrides.items():
        gid_to_year[str(gid)] = parse_year(date_str)

    # Scan files to fill gaps
    for file_path in files:
        if 'manifest.json' in file_path or 'authors_metadata.json' in file_path or 'original_publication_dates.json' in file_path:
            continue
        try:
            with open(file_path, 'r') as f:
                data = json.load(f)
        except:
            continue
            
        src = data.get('source', {})
        gid = src.get('goodreads_id')
        if gid:
            y = parse_year(src.get('publication_year') or src.get('goodreads', {}).get('publication_year'))
            if y and str(gid) not in gid_to_year:
                gid_to_year[str(gid)] = y

        for cit in data.get('citations', []):
            match = cit.get('goodreads_match')
            if match:
                gid = match.get('book_id')
                if gid:
                    y = parse_year(match.get('publication_year'))
                    if y and str(gid) not in gid_to_year:
                        gid_to_year[str(gid)] = y

    # Second pass: Check citations
    for file_path in files:
        if 'manifest.json' in file_path or 'authors_metadata.json' in file_path or 'original_publication_dates.json' in file_path:
            continue
        try:
            with open(file_path, 'r') as f:
                data = json.load(f)
        except:
            continue

        src = data.get('source', {})
        src_gid = str(src.get('goodreads_id'))
        src_title = src.get('title')
        src_year = gid_to_year.get(src_gid)

        if not src_year:
            continue

        for cit in data.get('citations', []):
            match = cit.get('goodreads_match')
            if not match:
                continue
            
            tgt_gid = str(match.get('book_id'))
            tgt_title = match.get('title')
            tgt_year = gid_to_year.get(tgt_gid)

            if tgt_year is None:
                unknowns.append({
                    'src': src_title,
                    'src_year': src_year,
                    'tgt': tgt_title,
                    'tgt_gid': tgt_gid
                })
                continue

            # Check for Anachronism
            # Allow 5 year buffer for uncertainty/editions
            if tgt_year > (src_year + 5):
                # Filter out cases where Source is ancient but we used a reprint date?
                # No, we fixed source dates.
                # Filter out cases where Target is a modern commentary?
                # If Source cites Target, and Target is newer, it implies Source is a modern edition citing a modern book, 
                # OR it's a wrong match.
                
                anachronisms.append({
                    'src': src_title,
                    'src_year': src_year,
                    'tgt': tgt_title,
                    'tgt_year': tgt_year,
                    'diff': tgt_year - src_year
                })

    # Sort
    anachronisms.sort(key=lambda x: x['diff'], reverse=True)

    print(f"Found {len(unknowns)} citations to Unknown years.")
    print(f"Found {len(anachronisms)} citations to Future years:")
    
    for item in anachronisms[:50]:
        print(f"Source: {item['src']} ({item['src_year']}) -> Cites: {item['tgt']} ({item['tgt_year']}) | Diff: {item['diff']} years")

if __name__ == "__main__":
    scan_future()
