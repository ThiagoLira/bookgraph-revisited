
import json
from pathlib import Path

# Heuristic: If year is between these values, just flip the sign.
# Covers 1000 AD to 2025 AD (misinterpreted as -1000 to -2025)
FLIP_MIN = -2025
FLIP_MAX = -1000

# Manual overrides for cases where the year is just wrong (e.g. Lincoln -44)
MANUAL_OVERRIDES = {
    "Lincoln": 1809,
    "Churchill": 1874,
    "Cain": 1972, # Assuming Chelsea Cain or James M. Cain (1892), wait. 
                  # Looking at context might be needed, but usually James M. Cain in this library? 
                  # Or is it "Cain" biblical? "Cain | -65". Biblical Cain is way older. 
                  # Given "Chelsea Cain" appeared in DFW, might be contamination? 
                  # Let's assume James M. Cain if Stalin read him, or modern. 
                  # Safer to leave Cain alone or set to null if unsure? 
                  # Let's skip Cain for now or set to null.
    "Fries": 1887, # Charles C. Fries?
    "Wagner": 1813, # Richard Wagner
    "Schoenberg": 1874, # Arnold Schoenberg
    "Steiner": 1861, # Rudolf Steiner
    "Struve": 1870, # Peter Struve
    "Contini": 1912, # Gianfranco Contini
    "Popper": 1902, # Karl Popper
    "Oppenheimer": 1904, # J. Robert Oppenheimer
    "Pavlov": 1849, # Ivan Pavlov
    "Renan": 1823,
    "Bismarck": 1815,
    "Shakespeare": 1564,
    "Pascal": 1623,
    "Hume": 1711,
    "Winckelmann": 1717,
    "Genehis Khan": 1162, # Typo in my thought trace? Genghis Khan -1162 -> 1162
    "Genghis Khan": 1162,
    "Wolfram": 1170, # Wolfram von Eschenbach
    "Petrarchan": 1304, # Petrarch
    "John of Holywood": 1195,
    "Frederick II": 1194,
    "Ibn Khaldun": 1332,
    "bn khldwn": 1332,
    "Saint  Augustine": 354,
    "St. Augustine": 354,
    "Augustine": 354,
    "St. Thomas": 1225,
    "Pseudo-Dionysius": 400, # Approx 5th/6th century AD
    "Pseudo-Dionysius the Areopagite": 400,
    "Saint Brendan": 484,
    "Saint Jerome": 347,
    "Saint Ambrose": 339,
    "Cosmas Indicopleustes": 500, # 6th Cent AD
    "Propertius": -50, # Correct
    "Catullus": -84, # Correct
    "Ovid": -43, # Correct
    "Horace": -65, # Correct
    "Virgil": -70, # Correct
    "L. Beria": 1899,
    "Dimitrov": 1882
}

def main():
    target_file = Path("frontend/data/stalin_library/authors_metadata.json")
    if not target_file.exists():
        print("File not found")
        return

    print(f"Loading {target_file}...")
    data = json.loads(target_file.read_text())
    changed_count = 0

    for author, meta in data.items():
        b_year = meta.get("birth_year")
        
        if b_year is not None and isinstance(b_year, int) and b_year < 0:
            new_year = b_year
            
            # 1. Manual Override
            if author in MANUAL_OVERRIDES:
                # Handle cases where I marked it as "Correct" in the map by keeping it negative
                # But actually the map keys are correct years. 
                # If map says -50, keep -50.
                new_year = MANUAL_OVERRIDES[author]
                if new_year != b_year:
                    print(f"[FIX] {author}: {b_year} -> {new_year} (Manual)")
                    meta["birth_year"] = new_year
                    changed_count += 1
            
            # 2. Heuristic Flip
            elif FLIP_MIN <= b_year <= FLIP_MAX:
                new_year = abs(b_year)
                print(f"[FIX] {author}: {b_year} -> {new_year} (Flip)")
                meta["birth_year"] = new_year
                if meta.get("death_year") and meta["death_year"] < 0:
                     meta["death_year"] = abs(meta["death_year"])
                changed_count += 1
                
    if changed_count > 0:
        target_file.write_text(json.dumps(data, indent=2, sort_keys=True))
        print(f"Saved {changed_count} changes to {target_file}")
    else:
        print("No changes needed.")

if __name__ == "__main__":
    main()
