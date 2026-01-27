
import json
import glob

def check_file(path):
    with open(path) as f:
        data = json.load(f)
    
    src_authors = data.get("source", {}).get("authors", [])
    if src_authors:
        print(f"File: {path}")
        print(f"  Source Authors: {src_authors!r}")
        for a in src_authors:
            print(f"    '{a}' chars: {[ord(c) for c in a]}")

    citations = data.get("citations", [])
    for i, cit in enumerate(citations):
        match = cit.get("goodreads_match") or {}
        c_authors = match.get("authors", [])
        for a in c_authors:
            if "Eco" in a:
                print(f"  Citation {i} Author: {a!r}")
                print(f"    '{a}' chars: {[ord(c) for c in a]}")

for f in glob.glob("frontend/data/umberto_eco_collection/*.json"):
    check_file(f)
