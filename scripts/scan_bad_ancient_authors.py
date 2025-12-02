import json

def scan_bad_authors():
    try:
        with open('frontend/data/authors_metadata.json', 'r') as f:
            data = json.load(f)
    except:
        return

    ancient_names = [
        "Homer", "Plato", "Aristotle", "Socrates", "Virgil", "Vergil", 
        "Ovid", "Horace", "Sophocles", "Euripides", "Aeschylus", 
        "Herodotus", "Thucydides", "Hesiod", "Pindar", "Sappho", 
        "Cicero", "Caesar", "Augustine", "Confucius", "Laozi", "Sun Tzu",
        "Marcus Aurelius", "Seneca", "Epictetus", "Plotinus", "Lucretius",
        "Enoch", "Josephus", "Eusebius", "Proclus", "Plotinus", "Porphyry",
        "Iamblichus", "Boethius", "Aquinas", "Dante", "Chaucer",
        "Flavius Josephus", "Saint Augustine", "St. Augustine"
    ]

    bad_authors = []
    
    for name, meta in data.items():
        birth = meta.get('birth_year')
        if not birth:
            continue
            
        # Check if name contains ancient keyword
        is_ancient_name = False
        for ancient in ancient_names:
            if ancient.lower() == name.lower() or ancient.lower() in name.lower().split():
                 is_ancient_name = True
                 break
        
        if is_ancient_name and birth > 1500:
            bad_authors.append((name, birth))

    print(f"Found {len(bad_authors)} potentially incorrect ancient authors:")
    for name, birth in bad_authors:
        print(f"Author: {name} | Birth Year: {birth}")

if __name__ == "__main__":
    scan_bad_authors()
