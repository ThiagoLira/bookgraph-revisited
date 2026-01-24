
import sqlite3
import sys
from pathlib import Path

def main():
    db_path = Path("datasets/books_index.db")
    if not db_path.exists():
        print("DB not found")
        return

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    
    queries = [
        ("George Gilder", ""), # Empty string to match all
    ]

    print("--- Loose Search ---")
    for author, title_frag in queries:
        print(f"\nAuthor: {author}, Title Frag: '{title_frag}'")
        fts_query = f'authors : "{author}"'
        sql = "SELECT data FROM books_fts WHERE books_fts MATCH ? LIMIT 50"
        
        rows = conn.execute(sql, (fts_query,)).fetchall()
        print(f"Found {len(rows)} books by {author}:")
        for row in rows:
            import json
            data = json.loads(row['data'])
            t = data.get('title', '')
            if title_frag and title_frag.lower() in t.lower():
                print(f"  MATCH: {t} (ID: {data['book_id']})")
            elif not title_frag:
                 print(f"  - {t}")

if __name__ == "__main__":
    main()
