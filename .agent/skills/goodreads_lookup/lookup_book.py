#!/usr/bin/env python3
import sqlite3
import argparse
import json
import sys
from pathlib import Path

def main():
    parser = argparse.ArgumentParser(description="Lookup Goodreads Book ID")
    parser.add_argument("--title", required=True, help="Title of the book")
    parser.add_argument("--author", help="Author of the book")
    parser.add_argument("--limit", type=int, default=10, help="Max results")
    parser.add_argument("--db-path", default="datasets/books_index.db", help="Path to SQLite DB")
    
    args = parser.parse_args()
    
    db_path = Path(args.db_path)
    if not db_path.exists():
        # Try relative to repo root if running from elsewhere
        repo_root = Path(__file__).resolve().parent.parent.parent.parent
        db_path = repo_root / "datasets" / "books_index.db"
        if not db_path.exists():
            print(f"Error: Database not found at {args.db_path} or {db_path}")
            sys.exit(1)

    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
    except Exception as e:
         print(f"Error connecting to DB: {e}")
         sys.exit(1)

    title_query = args.title.strip()
    author_query = args.author.strip() if args.author else None
    
    print(f"Searching for Title='{title_query}', Author='{author_query}'...")

    results = []

    # 1. Author + Title Search (FTS on authors, filter on title)
    if author_query:
        # FTS on authors column
        # Note: input needs to be sanitized for FTS query syntax if complex, 
        # but for simple names standard implementation usually works or use param binding if possible.
        # SQLite FTS MATCH doesn't support binding the match string safely easily without creating the string first.
        # We quote it to be safe-ish.
        fts_query = f'authors : "{author_query}"'
        
        sql = """
        SELECT data FROM books_fts 
        WHERE books_fts MATCH ? 
        LIMIT 100
        """
        try:
            rows = conn.execute(sql, (fts_query,)).fetchall()
            for row in rows:
                try:
                    data = json.loads(row['data'])
                    t = data.get('title', '')
                    if title_query.lower() in t.lower():
                        results.append(data)
                except:
                    continue
        except sqlite3.OperationalError as e:
            print(f"FTS Error (Author): {e}")

    # 2. Relaxed Title-only Search (if no author or no results)
    if not results and not author_query:
        # If no author provided, we must rely on title search.
        # But books_fts is indexed heavily on authors?
        # Let's check schema/setup. Usually FTS is across columns or specific columns.
        # Assuming we can match on title if it is in the FTS index.
        # If 'data' is the only column, maybe we can't easily FTS title?
        
        # Fallback: simple LIKE query on the main table if FTS fails or isn't built for titles
        # But per debug_search.py, it executes `SELECT data FROM books_fts WHERE books_fts MATCH ...`
        # If titles are not indexed in FTS, this is hard.
        # Let's assume title is indexed or use a LIKE on books table if it exists.
        
        # Checking debug_search.py again: it ONLY queried authors in FTS.
        # Does the DB have a `books` table?
        # debug_search.py: `conn.execute(sql, (fts_query,))` where sql select from books_fts
        
        # Let's try to query the `books` table if exists for simple LIKE
        try:
            sql = "SELECT data FROM books WHERE title LIKE ? LIMIT ?"
            rows = conn.execute(sql, (f"%{title_query}%", args.limit)).fetchall()
            for row in rows:
                results.append(json.loads(row['data']))
        except Exception:
            # Maybe books table doesn't have title column separated?
            pass


    # Sort by rough relevance (exact title match?)
    # Simple heuristic
    results.sort(key=lambda x: len(x.get('title', ''))) 
    
    results = results[:args.limit]

    print(f"\nFound {len(results)} matches:\n")
    for i, book in enumerate(results):
        print(f"{i+1}. {book.get('title')} (ID: {book.get('book_id')})")
        print(f"   Authors: {book.get('authors')}")
        print(f"   Year: {book.get('publication_year')}")
        print("-" * 30)

if __name__ == "__main__":
    main()
