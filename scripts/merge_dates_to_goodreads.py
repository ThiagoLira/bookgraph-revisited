import json
import os
import shutil
from datetime import datetime

def merge_dates():
    source_path = 'frontend/data/original_publication_dates.json'
    target_path = 'goodreads_data/original_publication_dates.json'

    print(f"Loading source: {source_path}")
    try:
        with open(source_path, 'r') as f:
            source_data = json.load(f)
    except Exception as e:
        print(f"Error loading source: {e}")
        return

    print(f"Loading target: {target_path}")
    target_data = {}
    if os.path.exists(target_path):
        try:
            with open(target_path, 'r') as f:
                target_data = json.load(f)
        except Exception as e:
            print(f"Error loading target (will create new): {e}")

    # Backup target
    if os.path.exists(target_path):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = f"{target_path}.{timestamp}.bak"
        shutil.copy2(target_path, backup_path)
        print(f"Backed up target to: {backup_path}")

    # Merge
    # We want source_data to overwrite target_data for any conflicts,
    # because source_data contains our manually cleaned fixes.
    initial_len = len(target_data)
    
    # Update target with source
    target_data.update(source_data)
    
    final_len = len(target_data)
    updated_count = len(source_data)
    
    print(f"Initial target size: {initial_len}")
    print(f"Source size: {len(source_data)}")
    print(f"Final target size: {final_len}")

    # Write back
    with open(target_path, 'w') as f:
        json.dump(target_data, f, indent=2, sort_keys=True)
    
    print(f"Successfully merged dates into {target_path}")

if __name__ == "__main__":
    merge_dates()
