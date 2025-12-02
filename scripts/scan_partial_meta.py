import json

def scan_partial_metadata():
    try:
        with open('frontend/data/authors_metadata.json', 'r') as f:
            data = json.load(f)
    except FileNotFoundError:
        print("File not found.")
        return

    partial_authors = []
    for name, meta in data.items():
        if meta.get('death_year') and not meta.get('birth_year'):
            partial_authors.append(name)

    print(f"Found {len(partial_authors)} authors with death year but missing birth year:")
    for name in partial_authors:
        print(f"{name}: Died {data[name]['death_year']}")

if __name__ == "__main__":
    scan_partial_metadata()
