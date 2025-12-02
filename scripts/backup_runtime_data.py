import os
import shutil
from pathlib import Path
import datetime

def backup_data():
    source_dir = Path("goodreads_data")
    target_base = Path(os.path.expanduser("~/OneDrive/BookGraphData"))
    
    # Create target directory if it doesn't exist
    if not target_base.exists():
        print(f"Creating target directory: {target_base}")
        target_base.mkdir(parents=True, exist_ok=True)
        
    # List of runtime files to backup
    files_to_backup = [
        "books_index.db",
        "wiki_people_index.db",
        "goodreads_book_authors.json",
        "original_publication_dates.json",
        "authors_metadata.json"
    ]
    
    print(f"Starting backup to {target_base}...")
    
    for filename in files_to_backup:
        source_file = source_dir / filename
        target_file = target_base / filename
        
        if not source_file.exists():
            print(f"⚠️  Warning: Source file not found: {source_file}")
            continue
            
        try:
            # Check if file needs update (size or mtime)
            should_copy = True
            if target_file.exists():
                src_stat = source_file.stat()
                dst_stat = target_file.stat()
                if src_stat.st_size == dst_stat.st_size and src_stat.st_mtime <= dst_stat.st_mtime:
                    should_copy = False
                    print(f"  Skipping {filename} (up to date)")
            
            if should_copy:
                print(f"  Copying {filename}...")
                shutil.copy2(source_file, target_file)
                print(f"  ✅ {filename} backed up successfully.")
                
        except Exception as e:
            print(f"❌ Error backing up {filename}: {e}")

    print("\nBackup complete.")

if __name__ == "__main__":
    backup_data()
