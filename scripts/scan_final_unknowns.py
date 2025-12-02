import json
import glob
import re

def parse_year(date_str):
    if date_str is None:
        return None
    if isinstance(date_str, (int, float)):
        return int(date_str)
    
    s = str(date_str)
    if "BC" in s:
        try:
            return -int(re.sub(r'\D', '', s))
        except:
            return None
            
    # Try parsing year
    # YYYY
    match = re.match(r'^-?(\d{4})', s)
    if match:
        return int(match.group(1))
    
    # Negative year unpadded? "-386"
    match = re.match(r'^(-?\d+)', s)
    if match:
        return int(match.group(1))
        
    return None

def scan_final_unknowns():
    try:
        with open('frontend/data/original_publication_dates.json', 'r') as f:
            pub_dates = json.load(f)
    except:
        pub_dates = {}

    unknowns = []
    seen_gids = set()

    files = glob.glob('frontend/data/*.json')
    for file_path in files:
        if 'manifest.json' in file_path or 'authors_metadata.json' in file_path or 'original_publication_dates.json' in file_path:
            continue
            
        try:
            with open(file_path, 'r') as f:
                data = json.load(f)
        except:
            continue

        def check(gid, title, meta_year):
            if not gid:
                return
            gid_str = str(gid)
            if gid_str in seen_gids:
                return
            seen_gids.add(gid_str)

            year = None
            # 1. Check override
            if gid_str in pub_dates:
                year = parse_year(pub_dates[gid_str])
            
            # 2. Check metadata
            if year is None:
                year = parse_year(meta_year)
            
            if year is None:
                unknowns.append({'gid': gid, 'title': title})

        # Source
        src = data.get('source', {})
        check(src.get('goodreads_id'), src.get('title'), src.get('publication_year') or src.get('goodreads', {}).get('publication_year'))

        # Citations
        citations = data.get('citations', [])
        for cit in citations:
            match = cit.get('goodreads_match')
            if match:
                check(match.get('book_id'), match.get('title'), match.get('publication_year'))

    print(f"Found {len(unknowns)} remaining unknown dates:")
    for item in unknowns[:20]:
        print(f"GID: {item['gid']} | Title: {item['title']}")

if __name__ == "__main__":
    scan_final_unknowns()
