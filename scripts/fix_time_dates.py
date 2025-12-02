import json
import re

def fix_time_dates():
    file_path = 'frontend/data/original_publication_dates.json'
    try:
        with open(file_path, 'r') as f:
            data = json.load(f)
    except FileNotFoundError:
        print("File not found.")
        return

    count = 0
    for gid, date_str in data.items():
        if isinstance(date_str, str) and 'T' in date_str:
            # Split by T and take first part
            new_date = date_str.split('T')[0]
            data[gid] = new_date
            count += 1

    with open(file_path, 'w') as f:
        json.dump(data, f, indent=2)

    print(f"Fixed {count} dates by removing time component.")

if __name__ == "__main__":
    fix_time_dates()
