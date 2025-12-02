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

def dump_metadata():
    # Load Overrides
    try:
        with open('frontend/data/original_publication_dates.json', 'r') as f:
            overrides = json.load(f)
    except:
        overrides = {}

    all_books = {} # GID -> {year, title, author}

    files = glob.glob('frontend/data/*.json')
    for file_path in files:
        if 'manifest.json' in file_path or 'authors_metadata.json' in file_path or 'original_publication_dates.json' in file_path:
            continue
            
        try:
            with open(file_path, 'r') as f:
                data = json.load(f)
        except:
            continue

        def process(gid, title, authors, year_val):
            if not gid:
                return
            gid_str = str(gid)
            
            # Determine Year
            year = None
            if gid_str in overrides:
                year = parse_year(overrides[gid_str])
            else:
                year = parse_year(year_val)
            
            # Format Author
            auth_str = "Unknown"
            if authors:
                if isinstance(authors, list):
                    auth_str = ", ".join(authors)
                else:
                    auth_str = str(authors)
            
            # Store (overwrite if exists, assuming later scans might be same)
            # Actually, we just want one entry per GID.
            if gid_str not in all_books:
                all_books[gid_str] = {
                    'year': year,
                    'title': title,
                    'author': auth_str
                }
            else:
                # If we have a year now and didn't before, update
                if year is not None and all_books[gid_str]['year'] is None:
                    all_books[gid_str]['year'] = year

        # Source
        src = data.get('source', {})
        process(src.get('goodreads_id'), src.get('title'), src.get('authors'), src.get('publication_year') or src.get('goodreads', {}).get('publication_year'))

        # Citations
        citations = data.get('citations', [])
        for cit in citations:
            match = cit.get('goodreads_match')
            if match:
                process(match.get('book_id'), match.get('title'), match.get('authors'), match.get('publication_year'))

    # Sort
    # Handle None years by putting them at the end
    sorted_books = sorted(all_books.items(), key=lambda x: (x[1]['year'] if x[1]['year'] is not None else 9999))

    # Output
    with open('all_metadata_dump.txt', 'w') as f:
        for gid, info in sorted_books:
            y = info['year']
            if y is None:
                y_str = "Unknown"
            else:
                y_str = str(y)
            
            line = f"{gid} | {y_str} | {info['author']} | {info['title']}"
            f.write(line + "\n")

    print(f"Dumped {len(sorted_books)} books to all_metadata_dump.txt")

if __name__ == "__main__":
    dump_metadata()
