#!/usr/bin/env python3
import sqlite3
import argparse
import shutil
import re
import sys
from pathlib import Path
from datetime import datetime

DEFAULT_LIBRARY_PATH = "/home/thiago/Onedrive/Ebooks Vault"

def main():
    parser = argparse.ArgumentParser(description="Retrieve books from Calibre library.")
    parser.add_argument("--library-path", default=DEFAULT_LIBRARY_PATH, help="Path to Calibre library root.")
    parser.add_argument("--author", help="Filter by Author name (partial match).")
    parser.add_argument("--title", help="Filter by Title (partial match).")
    parser.add_argument("--tag", help="Filter by Tag (partial match, e.g. 'non-fiction').")
    parser.add_argument("--lang", help="Filter by Language code (e.g. 'eng', 'ita').")
    parser.add_argument("--limit", type=int, default=50, help="Max books to retrieve.")
    
    args = parser.parse_args()
    
    lib_path = Path(args.library_path)
    db_path = lib_path / "metadata.db"
    
    if not db_path.exists():
        print(f"Error: Calibre DB not found at {db_path}")
        sys.exit(1)

    # Prepare Destination
    # Generate slug from query
    parts = []
    if args.author: parts.append(args.author)
    if args.title: parts.append(args.title)
    if args.tag: parts.append(args.tag)
    if args.lang: parts.append(args.lang)
    
    slug = "_".join(parts) if parts else "all_books"
    slug = re.sub(r'[^a-zA-Z0-9]', '_', slug).lower()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    folder_name = f"{slug}_{timestamp}"
    
    repo_root = Path(__file__).resolve().parent.parent.parent.parent
    dest_dir = repo_root / "input_books" / "libraries" / folder_name
    dest_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"Destination: {dest_dir}")

    # Connect DB
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    
    # Build Query
    # We SELECT distinct book details. 
    # We join identifiers to get goodreads id.
    query_parts = ["SELECT b.id, b.title, b.path, i.val as goodreads_id FROM books b"]
    query_parts.append("LEFT JOIN identifiers i ON b.id = i.book AND i.type='goodreads'")
    
    where_clauses = []
    params = []
    
    joins = set()
    
    if args.author:
        # Check authors table? Or easier: query books.author_sort or link to authors
        # For better matching, let's use books_authors_link + authors
        joins.add("JOIN books_authors_link bal ON b.id = bal.book")
        joins.add("JOIN authors a ON bal.author = a.id")
        where_clauses.append("a.name LIKE ?")
        params.append(f"%{args.author}%")

    if args.title:
        where_clauses.append("b.title LIKE ?")
        params.append(f"%{args.title}%")
        
    if args.tag:
        joins.add("JOIN books_tags_link btl ON b.id = btl.book")
        joins.add("JOIN tags t ON btl.tag = t.id")
        where_clauses.append("t.name LIKE ?")
        params.append(f"%{args.tag}%")
        
    if args.lang:
        joins.add("JOIN books_languages_link bll ON b.id = bll.book")
        joins.add("JOIN languages l ON bll.lang_code = l.id")
        where_clauses.append("l.lang_code LIKE ?")
        params.append(f"%{args.lang}%")

    # Construct complete query
    full_sql = " ".join(query_parts)
    for j in joins:
        full_sql += f" {j}"
        
    if where_clauses:
        full_sql += " WHERE " + " AND ".join(where_clauses)
        
    full_sql += " GROUP BY b.id" # Deduplicate if multiple matches
    
    print(f"Querying DB...")
    
    # ... (execution) ...

    try:
        cursor = conn.execute(full_sql, params)
        rows = cursor.fetchall()
    except sqlite3.OperationalError as e:
        print(f"SQL Error: {e}")
        sys.exit(1)
        
    print(f"Found {len(rows)} potential matches.")
    
    copied_count = 0
    missing_txt_count = 0
    
    for row in rows:
        if copied_count >= args.limit:
            break
            
        book_id = row['id']
        title = row['title']
        rel_path = row['path']
        goodreads_id = row['goodreads_id']
        
        book_dir = lib_path / rel_path
        
        # Check for TXT format
        data_rows = conn.execute("SELECT name, format FROM data WHERE book=?", (book_id,)).fetchall()
        
        txt_file = None
        for dr in data_rows:
            if dr['format'] == 'TXT':
                fname = f"{dr['name']}.txt"
                fpath = book_dir / fname
                if fpath.exists():
                    txt_file = fpath
                    break
        
        if txt_file:
            # Determine Output Filename
            # Sanitize title
            safe_title = re.sub(r'[^a-zA-Z0-9]', '_', title)
            
            if goodreads_id:
                # Format: Title_12345.txt
                out_name = f"{safe_title}_{goodreads_id}.txt"
            else:
                # Format: Title.txt (Warning: this might miss the ID in pipeline)
                print(f"  [WARN] Book '{title}' has no Goodreads ID in Calibre.")
                out_name = f"{safe_title}.txt"
                
            dest_path = dest_dir / out_name
            
            print(f"  [COPY] {title} -> {out_name}")
            shutil.copy2(txt_file, dest_path)
            copied_count += 1
        else:
            print(f"  [SKIP] {title} (No TXT)")
            print(f"         Debug: Formats found: {[r['format'] for r in data_rows]}")
            missing_txt_count += 1
            
    print("-" * 40)
    print(f"Copied: {copied_count}")
    print(f"Skipped (No TXT): {missing_txt_count}")
    print(f"Output Directory: {dest_dir}")

if __name__ == "__main__":
    main()
