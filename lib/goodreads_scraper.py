import requests
import re
import json
import datetime
from typing import Optional

def get_original_publication_date(goodreads_id: str) -> Optional[datetime.datetime]:
    """
    Fetches the original publication date for a book from Goodreads.
    
    Args:
        goodreads_id: The Goodreads Book ID (e.g., "74921815").
        
    Returns:
        datetime.datetime object representing the original publication date, or None if not found.
    """
    url = f"https://www.goodreads.com/book/show/{goodreads_id}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Safari/537.36"
    }
    
    # Skip synthetic IDs from fallback resolution
    if str(goodreads_id).startswith("web_"):
        return None
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        html = response.text
        
        # Extract __NEXT_DATA__ JSON blob
        match = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html, re.DOTALL)
        if not match:
            print(f"Error: Could not find __NEXT_DATA__ in {url}")
            return None
            
        data = json.loads(match.group(1))
        
        # Traverse to Apollo State
        apollo_state = data.get("props", {}).get("pageProps", {}).get("apolloState", {})
        if not apollo_state:
            print(f"Error: Could not find apolloState in JSON for {url}")
            return None
            
        # Find the Work entity
        work_node = None
        for key, value in apollo_state.items():
            if key.startswith("Work:"):
                work_node = value
                break
        
        if not work_node:
            print(f"Error: Could not find Work entity in apolloState for {url}")
            return None
            
        # Extract publication time
        # The structure is usually details -> publicationTime (epoch ms)
        details = work_node.get("details", {})
        pub_time_ms = details.get("publicationTime")
        
        if not pub_time_ms:
            print(f"Warning: No publicationTime found in Work details for {url}")
            return None
            
        # Convert ms to seconds
        pub_time_sec = int(pub_time_ms) / 1000
        
        try:
            return datetime.datetime.fromtimestamp(pub_time_sec)
        except (ValueError, OSError, OverflowError):
            # Handle dates before year 1 (BC) or out of range
            # Approximate year calculation
            # 1 year approx 31556926 seconds
            year = 1970 + int(pub_time_sec / 31556926)
            if year <= 0:
                # Return a dummy datetime for year 1 but with a special flag? 
                # Or just return None and print the BC year?
                # The user just wants to know if it works.
                # Let's return a string representation for now if the return type allows, 
                # or change the return type.
                # For this specific tool, let's return a datetime at year 1 but log the actual year.
                # Actually, let's change the return type hint to Union[datetime.datetime, str]
                return f"{abs(year)} BC"
            return None

    except Exception as e:
        print(f"Exception fetching data for {goodreads_id}: {e}")
        return None

import os
import time

def generate_pub_dates_map(ids_file: str, output_file: str = "goodreads_data/original_publication_dates.json"):
    """
    Reads a list of Goodreads IDs from a file, fetches their original publication dates,
    and updates a JSON mapping file.
    
    Args:
        ids_file: Path to the text file containing Goodreads IDs (one per line).
        output_file: Path to the output JSON file.
    """
    # Load existing data
    if os.path.exists(output_file):
        try:
            with open(output_file, 'r') as f:
                pub_dates = json.load(f)
        except json.JSONDecodeError:
            pub_dates = {}
    else:
        pub_dates = {}
        
    # Load IDs to process
    with open(ids_file, 'r') as f:
        ids_to_process = [line.strip() for line in f if line.strip()]
        
    print(f"Loaded {len(ids_to_process)} IDs to process.")
    
    # Filter out already processed IDs
    ids_to_fetch = [gid for gid in ids_to_process if gid not in pub_dates]
    print(f"Fetching dates for {len(ids_to_fetch)} new IDs...")
    
    try:
        for i, gid in enumerate(ids_to_fetch):
            print(f"[{i+1}/{len(ids_to_fetch)}] Fetching date for ID: {gid}")
            date = get_original_publication_date(gid)
            
            if date:
                if isinstance(date, datetime.datetime):
                    pub_dates[gid] = date.isoformat()
                else:
                    pub_dates[gid] = str(date)
            else:
                pub_dates[gid] = None
                
            # Save periodically
            if (i + 1) % 10 == 0:
                with open(output_file, 'w') as f:
                    json.dump(pub_dates, f, indent=2)
                print(f"Saved progress to {output_file}")
            
            # Be polite to Goodreads
            time.sleep(1.0)
            
    except KeyboardInterrupt:
        print("\nInterrupted! Saving progress...")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        # Final save
        with open(output_file, 'w') as f:
            json.dump(pub_dates, f, indent=2)
        print(f"Final save to {output_file}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Fetch original publication dates from Goodreads.")
    parser.add_argument("ids_file", help="Path to file containing Goodreads IDs")
    parser.add_argument("--output", default="goodreads_data/original_publication_dates.json", help="Path to output JSON file")
    args = parser.parse_args()

    generate_pub_dates_map(args.ids_file, args.output)
