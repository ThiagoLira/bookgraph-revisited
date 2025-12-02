import json
import glob
import re

def get_year(date_val):
    if not date_val:
        return None
    
    # Handle override strings
    if isinstance(date_val, str):
        if "BC" in date_val:
            try:
                y = int(re.sub(r'\D', '', date_val))
                return -y
            except:
                return None
        # Handle "1880-01-01" or "1999"
        match = re.match(r'^-?(\d{4})', date_val)
        if match:
            return int(match.group(1))
        # Handle "-386"
        match = re.match(r'^(-?\d+)', date_val)
        if match:
            return int(match.group(1))
            
    # Handle integers
    if isinstance(date_val, (int, float)):
        return int(date_val)
        
    return None

def scan_suspicious():
    # Load overrides
    try:
        with open('frontend/data/original_publication_dates.json', 'r') as f:
            overrides = json.load(f)
    except:
        overrides = {}

    # Heuristics
    ancient_keywords = [
        "Bible", "Holy Bible", "Torah", "Quran", "Koran", "Talmud", 
        "Gilgamesh", "Beowulf", "Iliad", "Odyssey", "Aeneid", 
        "Republic", "Symposium", "Apology", "Phaedo", "Crito", "Meno",
        "Nicomachean Ethics", "Politics", "Poetics", "Metaphysics",
        "Confessions", "City of God", "Meditations"
    ]
    
    ancient_authors = [
        "Homer", "Plato", "Aristotle", "Socrates", "Virgil", "Vergil", 
        "Ovid", "Horace", "Sophocles", "Euripides", "Aeschylus", 
        "Herodotus", "Thucydides", "Hesiod", "Pindar", "Sappho", 
        "Cicero", "Caesar", "Augustine", "Confucius", "Laozi", "Sun Tzu",
        "Marcus Aurelius", "Seneca", "Epictetus", "Plotinus", "Lucretius"
    ]

    suspicious = []
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

        # Helper to check a book
        def check_book(gid, title, authors, context_source):
            if not gid:
                return
            
            gid_str = str(gid)
            if gid_str in seen_gids:
                return
            seen_gids.add(gid_str)

            # Determine effective year
            year = None
            if gid_str in overrides:
                year = get_year(overrides[gid_str])
            else:
                # Try to find year in source or citations? 
                # The 'check_book' is called with data, but we need the year from the specific object
                # For source, it's in data['source']
                # For citation, it's in match
                pass 
                # Wait, I need to pass the year in or extract it here.
                # Let's just pass the whole object or extract before calling.
            
            # Refactor: extract year before calling
            return

    # Re-loop with better structure
    seen_gids = set()
    
    for file_path in files:
        if 'manifest.json' in file_path or 'authors_metadata.json' in file_path or 'original_publication_dates.json' in file_path:
            continue
            
        try:
            with open(file_path, 'r') as f:
                data = json.load(f)
        except:
            continue
            
        # 1. Check Source
        src = data.get('source', {})
        gid = src.get('goodreads_id')
        title = src.get('title', '')
        authors = src.get('authors', []) # Might be list of strings
        
        # Get year
        year = None
        if gid and str(gid) in overrides:
            year = get_year(overrides[str(gid)])
        else:
            year = src.get('publication_year')
            if not year:
                year = src.get('goodreads', {}).get('publication_year')
        
        # Check
        if year and year > 1500: # "Modern" cutoff
            is_ancient = False
            # Check Title
            for kw in ancient_keywords:
                if kw.lower() in title.lower():
                    is_ancient = True
                    break
            
            # Check Authors
            if not is_ancient:
                for auth in authors:
                    for ancient_auth in ancient_authors:
                        if ancient_auth.lower() in auth.lower():
                            is_ancient = True
                            break
            
            if is_ancient:
                suspicious.append({
                    'gid': gid,
                    'title': title,
                    'authors': authors,
                    'year': year,
                    'reason': 'Ancient text with modern year'
                })

        # 2. Check Citations
        citations = data.get('citations', [])
        for cit in citations:
            match = cit.get('goodreads_match')
            if not match:
                continue
                
            gid = match.get('book_id')
            title = match.get('title', '')
            authors = match.get('authors', [])
            
            if not gid:
                continue
                
            if str(gid) in seen_gids:
                continue
            seen_gids.add(str(gid))
            
            # Get year
            year = None
            if str(gid) in overrides:
                year = get_year(overrides[str(gid)])
            else:
                year = match.get('publication_year')
            
            # Check
            if year and year > 1500:
                is_ancient = False
                for kw in ancient_keywords:
                    if kw.lower() in title.lower():
                        is_ancient = True
                        break
                
                if not is_ancient:
                    for auth in authors:
                        for ancient_auth in ancient_authors:
                            if ancient_auth.lower() in auth.lower():
                                is_ancient = True
                                break
                
                if is_ancient:
                    suspicious.append({
                        'gid': gid,
                        'title': title,
                        'authors': authors,
                        'year': year,
                        'reason': 'Ancient text with modern year'
                    })

    print(f"Found {len(suspicious)} suspicious items:")
    for item in suspicious:
        print(f"GID: {item['gid']} | Title: {item['title']} | Authors: {item['authors']} | Year: {item['year']}")

if __name__ == "__main__":
    scan_suspicious()
