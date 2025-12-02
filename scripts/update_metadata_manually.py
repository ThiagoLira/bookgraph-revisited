import json
import os

def update_metadata():
    # 1. Update Publication Dates
    pub_dates_path = "frontend/data/original_publication_dates.json"
    with open(pub_dates_path, "r") as f:
        pub_dates = json.load(f)

    updates_pub = {
        "388564": "1968-01-01T00:00:00", # The Lessons of History
        "202643": "1867-01-01T00:00:00", # Das Kapital
        "840220": "1915-01-01T00:00:00", # Metamorphosis
        "5459222": "1915-01-01T00:00:00", # Metamorphosis
        "15778990": "1740-01-01T00:00:00", # Pamela
        "28281931": "1925-07-18T00:00:00", # Mein Kampf
        "54270": "1925-07-18T00:00:00", # Mein Kampf
        "21258721": "1860-01-01T00:00:00", # Max Havelaar
        "34448816": "1962-01-01T00:00:00", # Heydrich
        "6075126": "27 BC", # History of Rome
        "12299973": "1599-01-01T00:00:00", # Julius Caesar
        "20385662": "2 AD", # Ars Amatoria
        "82086280": "1687-01-01T00:00:00", # Newton Principia
        "3732140": "1677-01-01T00:00:00", # Spinoza Ethics
        "13611921": "350 BC", # Plato Epistles
        "463876": "1500 BC", # The Vedas
        "33554089": "350 AD", # Sallust
        "21527649": "161 AD", # Menippus
        "334332": "400 AD", # Macrobius
        "782374": "1965-01-01T00:00:00" # The Careful Writer
    }

    count_pub = 0
    for gid, date in updates_pub.items():
        if gid in pub_dates: # Only update if key exists (even if null)
            pub_dates[gid] = date
            count_pub += 1
    
    with open(pub_dates_path, "w") as f:
        json.dump(pub_dates, f, indent=2)
    
    print(f"Updated {count_pub} publication dates.")

    # 2. Update Author Metadata
    auth_meta_path = "frontend/data/authors_metadata.json"
    with open(auth_meta_path, "r") as f:
        auth_meta = json.load(f)

    updates_auth = {
        "Archimedes": {"birth_year": -287, "death_year": -212}, # Approx death
        "Pausanias (geographer)": {"birth_year": 110, "death_year": 180},
        "Zhuang Zhou": {"birth_year": -369, "death_year": -286},
        "Agathon": {"birth_year": -445, "death_year": -400},
        "Robert Cawdrey": {"birth_year": 1538, "death_year": 1604}
    }

    count_auth = 0
    for name, meta in updates_auth.items():
        if name in auth_meta:
            # Update existing record, don't overwrite entire object if possible, but here we just set fields
            if not auth_meta[name]: auth_meta[name] = {}
            auth_meta[name]["birth_year"] = meta["birth_year"]
            auth_meta[name]["death_year"] = meta["death_year"]
            count_auth += 1
    
    with open(auth_meta_path, "w") as f:
        json.dump(auth_meta, f, indent=2)

    print(f"Updated {count_auth} author records.")

if __name__ == "__main__":
    update_metadata()
