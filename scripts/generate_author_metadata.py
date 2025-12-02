import json
import sqlite3
import glob
import os
import re

def normalize_name(name):
    """
    Convert 'Last, First' to 'First Last'.
    """
    if "," in name:
        parts = name.split(",", 1)
        if len(parts) == 2:
            return f"{parts[1].strip()} {parts[0].strip()}"
    return name

def main():
    base_dir = "/Users/thlira/Documents/bookgraph-revisited"
    data_dir = os.path.join(base_dir, "frontend/data")
    db_path = os.path.join(base_dir, "goodreads_data/wiki_people_index.db")
    output_path = os.path.join(data_dir, "authors_metadata.json")

    if not os.path.exists(db_path):
        print(f"Database not found at {db_path}")
        return

    # 1. Collect Author Names
    author_names = set()
    
    files = glob.glob(os.path.join(data_dir, "*.json"))
    print(f"Found {len(files)} JSON files in {data_dir}")

    for fpath in files:
        if "authors_metadata.json" in fpath or "manifest.json" in fpath or "original_publication_dates.json" in fpath:
            continue
            
        try:
            with open(fpath, "r") as f:
                data = json.load(f)
        except Exception as e:
            print(f"Error reading {fpath}: {e}")
            continue

        # Source Authors
        source = data.get("source", {})
        authors = source.get("authors", [])
        if isinstance(authors, str):
            authors = [authors]
        
        for a in authors:
            author_names.add(a)
            author_names.add(normalize_name(a))

        # Cited Authors
        citations = data.get("citations", [])
        for cit in citations:
            # Wikipedia Match
            wiki = cit.get("wikipedia_match")
            if wiki and wiki.get("title"):
                author_names.add(wiki["title"])
            
            # Goodreads Match
            gr = cit.get("goodreads_match")
            if gr:
                gr_authors = gr.get("authors", [])
                if isinstance(gr_authors, str):
                    gr_authors = [gr_authors]
                for a in gr_authors:
                    author_names.add(a)
                    author_names.add(normalize_name(a))

    print(f"Collected {len(author_names)} unique author names.")

    # 2. Query Database
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    metadata = {}
    
    # Batch processing could be faster, but simple loop is safer for FTS syntax
    found_count = 0
    
    for name in author_names:
        # Escape quotes for FTS
        escaped_name = name.replace('"', '""')
        
        # Try exact match on title
        # We use MATCH with phrase query
        query = 'SELECT data FROM people_fts WHERE title MATCH ? LIMIT 1'
        try:
            cursor.execute(query, (f'"{escaped_name}"',))
            row = cursor.fetchone()
            
            if row:
                data_json = row[0]
                try:
                    record = json.loads(data_json)
                    metadata[name] = {
                        "birth_year": record.get("birth_year"),
                        "death_year": record.get("death_year"),
                        "title": record.get("title"),
                        "description": record.get("description") # Might not be in JSON, but let's see
                    }
                    found_count += 1
                except json.JSONDecodeError:
                    pass
        except sqlite3.Error as e:
            print(f"SQLite error for name '{name}': {e}")

    conn.close()
    
    print(f"Found metadata for {found_count} authors.")

    # 3. Write Output
    with open(output_path, "w") as f:
        json.dump(metadata, f, indent=2)
    print(f"Wrote metadata to {output_path}")

if __name__ == "__main__":
    main()
