import json
import glob
import re

def get_year(date_val):
    if not date_val:
        return None
    if isinstance(date_val, str):
        if "BC" in date_val:
            try:
                y = int(re.sub(r'\D', '', date_val))
                return -y
            except:
                return None
        match = re.match(r'^-?(\d{4})', date_val)
        if match:
            return int(match.group(1))
        match = re.match(r'^(-?\d+)', date_val)
        if match:
            return int(match.group(1))
    if isinstance(date_val, (int, float)):
        return int(date_val)
    return None

def scan_reprints():
    # Load author metadata
    try:
        with open('frontend/data/authors_metadata.json', 'r') as f:
            author_meta = json.load(f)
    except:
        author_meta = {}

    # Load date overrides
    try:
        with open('frontend/data/original_publication_dates.json', 'r') as f:
            overrides = json.load(f)
    except:
        overrides = {}

    reprints = []
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

        # Helper to check item
        def check_item(gid, title, authors, item_year):
            if not gid or not authors:
                return
            
            gid_str = str(gid)
            if gid_str in seen_gids:
                return
            seen_gids.add(gid_str)

            # Determine effective year
            year = item_year
            if gid_str in overrides:
                year = get_year(overrides[gid_str])
            
            if not year:
                return

            # Check against authors
            if isinstance(authors, str):
                authors = [authors]
                
            for auth_name in authors:
                # Normalize name? The metadata keys are usually the name.
                # But sometimes "Plato" vs "Plato, ..."
                
                # Try exact match first
                meta = author_meta.get(auth_name)
                if not meta:
                    # Try partial match?
                    pass
                
                if meta:
                    death = meta.get('death_year')
                    if death and year > (death + 20): # 20 year buffer for posthumous/uncertainty
                        reprints.append({
                            'gid': gid,
                            'title': title,
                            'author': auth_name,
                            'pub_year': year,
                            'death_year': death,
                            'diff': year - death
                        })
                        return # Found one author match, that's enough to flag

        # 1. Check Source
        src = data.get('source', {})
        check_item(
            src.get('goodreads_id'),
            src.get('title'),
            src.get('authors'),
            src.get('publication_year') or src.get('goodreads', {}).get('publication_year')
        )

        # 2. Check Citations
        citations = data.get('citations', [])
        for cit in citations:
            match = cit.get('goodreads_match')
            if match:
                check_item(
                    match.get('book_id'),
                    match.get('title'),
                    match.get('authors'),
                    match.get('publication_year')
                )

    # Sort by difference (worst offenders first)
    reprints.sort(key=lambda x: x['diff'], reverse=True)

    print(f"Found {len(reprints)} potential reprints:")
    for item in reprints[:50]: # Show top 50
        print(f"GID: {item['gid']} | {item['title']} ({item['pub_year']}) | Author: {item['author']} (d. {item['death_year']}) | Diff: {item['diff']} years")

if __name__ == "__main__":
    scan_reprints()
