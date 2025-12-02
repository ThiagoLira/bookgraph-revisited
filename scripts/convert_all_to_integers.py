import json
import re

def parse_to_integer(date_val):
    if date_val is None:
        return None
    if isinstance(date_val, int):
        return date_val
    
    s = str(date_val).strip()
    
    # Handle BC
    if "BC" in s:
        try:
            # Extract number
            num = int(re.sub(r'\D', '', s))
            return -num
        except:
            pass
            
    # Handle AD (e.g. "400 AD")
    if "AD" in s:
        try:
            num = int(re.sub(r'\D', '', s))
            return num
        except:
            pass

    # Handle ISO Date "YYYY-MM-DD" -> Year Integer
    match = re.match(r'^(\d{4})-\d{2}-\d{2}$', s)
    if match:
        return int(match.group(1))
        
    # Handle "YYYY-MM-DD" with negative year? "-0399-01-01"
    match = re.match(r'^(-?\d+)-\d{2}-\d{2}$', s)
    if match:
        return int(match.group(1))

    # Handle simple string year "1999" or "-399" or "0350"
    match = re.match(r'^(-?\d+)$', s)
    if match:
        return int(match.group(1))

    # Fallback: try to find any 4 digit year?
    # No, let's be strict to avoid garbage.
    
    return date_val # Return original if we can't convert safely

def convert_all():
    input_file = 'frontend/data/original_publication_dates.json'
    
    try:
        with open(input_file, 'r') as f:
            data = json.load(f)
    except:
        print("Could not load file")
        return

    converted_count = 0
    new_data = {}

    for gid, val in data.items():
        new_val = parse_to_integer(val)
        if new_val != val:
            converted_count += 1
        new_data[gid] = new_val

    with open(input_file, 'w') as f:
        json.dump(new_data, f, indent=2, sort_keys=True)

    print(f"Converted {converted_count} dates to integers.")

if __name__ == "__main__":
    convert_all()
