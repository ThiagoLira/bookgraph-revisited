import json
import re

def scan_bad_dates():
    try:
        with open('frontend/data/original_publication_dates.json', 'r') as f:
            data = json.load(f)
    except FileNotFoundError:
        print("File not found.")
        return

    bad_dates = []
    
    for gid, date_str in data.items():
        if date_str is None:
            continue
            
        # Simulate Frontend Logic
        is_valid = False
        
        # 1. Number
        if isinstance(date_str, (int, float)):
            is_valid = True
            
        # 2. String
        elif isinstance(date_str, str):
            # 2a. Contains "BC"
            if "BC" in date_str:
                # Check if it has digits
                if re.search(r'\d', date_str):
                    is_valid = True
            # 2b. Try to parse as standard date (YYYY, YYYY-MM-DD, ISO)
            else:
                # Simple regex for YYYY or YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS
                # Also allow negative years if padded? -YYYY
                if re.match(r'^-?\d{4}$', date_str): # YYYY or -YYYY
                    is_valid = True
                elif re.match(r'^\d{4}-\d{2}-\d{2}', date_str): # YYYY-MM-DD...
                    is_valid = True
                elif re.match(r'^-?\d+$', date_str): # Just digits (maybe unpadded year like "75")
                    # JS new Date("75") gives 1975 or 2075 usually, or Invalid. 
                    # Actually new Date("75") is Invalid. new Date(75) is 1970 + 75ms.
                    # But the frontend does:
                    # if (!isNaN(date.getFullYear()))
                    
                    # If it's a string "75", new Date("75") -> Invalid Date.
                    # If it's a string "-386", new Date("-386") -> Invalid Date.
                    
                    # So simple integers as strings might be FAILING if they are not 4 digits?
                    # Let's flag anything that isn't 4 digits or standard format.
                    is_valid = False 
                    
                    # Exception: if it's just a number string, we might want to convert it to int in the JSON
                    # But the JSON has it as string.
                    pass
        
        if not is_valid:
            bad_dates.append((gid, date_str))

    print(f"Found {len(bad_dates)} potentially malformed dates:")
    for gid, date in bad_dates:
        print(f"GID: {gid}, Date: {date}")

if __name__ == "__main__":
    scan_bad_dates()
