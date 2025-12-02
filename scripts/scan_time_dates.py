import json
import re

def scan_time_dates():
    try:
        with open('frontend/data/original_publication_dates.json', 'r') as f:
            data = json.load(f)
    except FileNotFoundError:
        print("File not found.")
        return

    time_dates = []
    
    for gid, date_str in data.items():
        if isinstance(date_str, str) and 'T' in date_str:
            time_dates.append((gid, date_str))

    print(f"Found {len(time_dates)} dates with time components:")
    for gid, date in time_dates:
        print(f"GID: {gid}, Date: {date}")

if __name__ == "__main__":
    scan_time_dates()
