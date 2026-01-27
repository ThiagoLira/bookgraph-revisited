
import json
from pathlib import Path

# Force these dates regardless of current value
FORCED_OVERRIDES = {
    "Struve": {"birth_year": 1793, "death_year": 1864, "nationality": "German-Russian", "main_genre": "Astronomy"},
    "Friedrich Georg Wilhelm von Struve": {"birth_year": 1793, "death_year": 1864},
    "Stalin": {"birth_year": 1878, "death_year": 1953},
    "I. V. Stalin": {"birth_year": 1878, "death_year": 1953},
    "Joseph Stalin": {"birth_year": 1878, "death_year": 1953},
    "J. Stalin": {"birth_year": 1878, "death_year": 1953},
    "Machiavelli": {"birth_year": 1469, "death_year": 1527},
    "Niccolo Machiavelli": {"birth_year": 1469, "death_year": 1527}
}

def main():
    target_file = Path("frontend/data/stalin_library/authors_metadata.json")
    if not target_file.exists():
        print("File not found")
        return

    print(f"Loading {target_file}...")
    data = json.loads(target_file.read_text())
    changed_count = 0

    # Apply forced overrides
    for author, correct_meta in FORCED_OVERRIDES.items():
        if author in data:
            current_meta = data[author]
            # Check if different
            diff = False
            for k, v in correct_meta.items():
                if current_meta.get(k) != v:
                    diff = True
                    break
            
            if diff:
                print(f"[FIX] Updating {author}: {current_meta} -> {correct_meta}")
                current_meta.update(correct_meta)
                changed_count += 1
    
    if changed_count > 0:
        target_file.write_text(json.dumps(data, indent=2, sort_keys=True))
        print(f"Saved {changed_count} changes to {target_file}")
    else:
        print("No changes needed.")

if __name__ == "__main__":
    main()
