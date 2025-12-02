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

def scan_aggressive():
    # Load Author Metadata
    try:
        with open('frontend/data/authors_metadata.json', 'r') as f:
            author_meta = json.load(f)
    except:
        author_meta = {}

    # Load Overrides
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

        def check(gid, title, authors, year_val):
            if not gid or not authors:
                return
            
            gid_str = str(gid)
            if gid_str in seen_gids:
                return
            seen_gids.add(gid_str)

            # Determine Year
            year = None
            if gid_str in overrides:
                year = parse_year(overrides[gid_str])
            else:
                year = parse_year(year_val)
            
            if not year:
                return

            # Check Criteria: Book > 1900
            if year < 1900:
                return

            if isinstance(authors, str):
                authors = [authors]

            for auth in authors:
                meta = author_meta.get(auth)
                if meta:
                    birth = meta.get('birth_year')
                    if birth and birth < 1850:
                        # Found one!
                        reprints.append({
                            'gid': gid,
                            'title': title,
                            'author': auth,
                            'auth_birth': birth,
                            'book_year': year
                        })
                        return

        # Source
        src = data.get('source', {})
        check(src.get('goodreads_id'), src.get('title'), src.get('authors'), src.get('publication_year') or src.get('goodreads', {}).get('publication_year'))

        # Citations
        citations = data.get('citations', [])
        for cit in citations:
            match = cit.get('goodreads_match')
            if match:
                check(match.get('book_id'), match.get('title'), match.get('authors'), match.get('publication_year'))

    # Sort by Author Birth Year (Oldest first)
    reprints.sort(key=lambda x: x['auth_birth'])

    print(f"Found {len(reprints)} aggressive reprints:")
    for item in reprints:
        print(f"GID: {item['gid']} | {item['title']} ({item['book_year']}) | Author: {item['author']} (b. {item['auth_birth']})")

if __name__ == "__main__":
    scan_aggressive()
