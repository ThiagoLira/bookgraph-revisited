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

def lint_metadata():
    # Load Data
    try:
        with open('frontend/data/authors_metadata.json', 'r') as f:
            author_meta = json.load(f)
    except:
        author_meta = {}

    try:
        with open('frontend/data/original_publication_dates.json', 'r') as f:
            date_overrides = json.load(f)
    except:
        date_overrides = {}

    issues = []

    # 1. Check Date Formats
    for gid, d in date_overrides.items():
        if isinstance(d, int):
            continue
        if isinstance(d, str):
            # Allowed: "YYYY-MM-DD", "YYYY", "-YYYY", "N BC"
            if re.match(r'^\d{4}-\d{2}-\d{2}$', d): continue
            if re.match(r'^-?\d{1,4}$', d): continue
            if "BC" in d: continue
            
            issues.append(f"Date Format: GID {gid} has suspicious format '{d}'")

    # 2. Scan Graph for Missing Authors & Anachronisms
    files = glob.glob('frontend/data/*.json')
    for file_path in files:
        if 'manifest.json' in file_path or 'authors_metadata.json' in file_path or 'original_publication_dates.json' in file_path:
            continue
            
        try:
            with open(file_path, 'r') as f:
                data = json.load(f)
        except:
            continue

        def check_item(gid, title, authors, year_val):
            # Check Year
            year = None
            if gid and str(gid) in date_overrides:
                year = parse_year(date_overrides[str(gid)])
            else:
                year = parse_year(year_val)
            
            if not authors:
                return

            if isinstance(authors, str):
                authors = [authors]

            for auth in authors:
                # Check if author exists
                if auth not in author_meta:
                    # Only flag if it's a "real" author (not Anonymous/Unknown)
                    if "Anonymous" not in auth and "Unknown" not in auth:
                        # issues.append(f"Missing Author: '{auth}' (from {title}) not in authors_metadata.json")
                        pass # Too noisy? Let's focus on dates first.
                
                # Check Anachronism
                if auth in author_meta and year:
                    meta = author_meta[auth]
                    birth = meta.get('birth_year')
                    death = meta.get('death_year')
                    
                    if birth and year < birth:
                        issues.append(f"Anachronism (Before Birth): {title} ({year}) by {auth} (b. {birth})")
                    
                    if death and year > (death + 50): # 50 year buffer
                        issues.append(f"Anachronism (After Death): {title} ({year}) by {auth} (d. {death})")

        # Source
        src = data.get('source', {})
        check_item(src.get('goodreads_id'), src.get('title'), src.get('authors'), src.get('publication_year') or src.get('goodreads', {}).get('publication_year'))

        # Citations
        citations = data.get('citations', [])
        for cit in citations:
            match = cit.get('goodreads_match')
            if match:
                check_item(match.get('book_id'), match.get('title'), match.get('authors'), match.get('publication_year'))

    # Deduplicate and Print
    unique_issues = sorted(list(set(issues)))
    print(f"Found {len(unique_issues)} issues:")
    for i in unique_issues[:100]:
        print(i)

if __name__ == "__main__":
    lint_metadata()
