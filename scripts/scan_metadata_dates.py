
import json
import sys
from pathlib import Path

def scan_metadata(path):
    p = Path(path)
    if not p.exists():
        print(f"File not found: {p}")
        return

    print(f"Scanning {p}...")
    try:
        data = json.loads(p.read_text())
        for author, meta in data.items():
            b_year = meta.get("birth_year")
            if b_year and isinstance(b_year, int) and b_year < 0:
                print(f"Author: {author} | Year: {b_year}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        scan_metadata(sys.argv[1])
    else:
        print("Usage: python scan_metadata_dates.py <path_to_json>")
