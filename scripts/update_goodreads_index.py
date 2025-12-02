import json
import sqlite3
import shutil
import os
from datetime import datetime

def update_index():
    db_path = 'goodreads_data/books_index.db'
    dates_path = 'goodreads_data/original_publication_dates.json'

    # 1. Backup
    if os.path.exists(db_path):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = f"{db_path}.{timestamp}.bak"
        shutil.copy2(db_path, backup_path)
        print(f"Backed up DB to: {backup_path}")
    else:
        print(f"Database not found at {db_path}")
        return

    # 2. Load Dates
    try:
        with open(dates_path, 'r') as f:
            dates_map = json.load(f)
    except Exception as e:
        print(f"Error loading dates: {e}")
        return

    # 3. Connect and Update
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Check if column exists
        cursor.execute("PRAGMA table_info(books)")
        columns = [info[1] for info in cursor.fetchall()]
        
        if 'original_publication_year' not in columns:
            print("Adding column 'original_publication_year'...")
            cursor.execute("ALTER TABLE books ADD COLUMN original_publication_year INTEGER")
        else:
            print("Column 'original_publication_year' already exists.")

        # Update
        print(f"Updating {len(dates_map)} records...")
        count = 0
        
        # Prepare batch updates
        updates = []
        for gid, year in dates_map.items():
            # Ensure year is integer (it should be from our previous step, but safety first)
            if isinstance(year, int):
                updates.append((year, gid))
            else:
                # Try to parse if somehow still string (shouldn't happen)
                try:
                    y_int = int(year)
                    updates.append((y_int, gid))
                except:
                    print(f"Skipping non-integer year for {gid}: {year}")

        # Execute in batches
        batch_size = 100
        for i in range(0, len(updates), batch_size):
            batch = updates[i:i + batch_size]
            cursor.executemany("UPDATE books SET original_publication_year = ? WHERE book_id = ?", batch)
            conn.commit()
            print(f"Committed batch {i // batch_size + 1} ({len(batch)} records)")
        
        print(f"Successfully updated {len(updates)} rows.")

    except Exception as e:
        print(f"Error updating database: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    update_index()
