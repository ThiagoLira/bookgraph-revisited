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

def generate_pub_dates_map(input_file: str):
    """
    Reads a citation metadata JSON file, collects all Goodreads IDs,
    fetches their original publication dates, and saves the mapping to a new JSON file.
    
    Args:
        input_file: Path to the input JSON file (e.g., ".../61535.json").
    """
    try:
        with open(input_file, 'r') as f:
            data = json.load(f)
            
        source_id = data.get("source", {}).get("goodreads_id")
        if not source_id:
            print(f"Error: No source Goodreads ID found in {input_file}")
            return

        # Collect all unique IDs
        ids = set()
        if source_id:
            ids.add(source_id)
            
        for citation in data.get("citations", []):
            edge = citation.get("edge", {})
            target_id = edge.get("target_book_id")
            if target_id:
                ids.add(target_id)
        
        print(f"Found {len(ids)} unique Goodreads IDs in {input_file}")
        
        # Fetch dates
        pub_dates = {}
        for i, gid in enumerate(ids):
            print(f"[{i+1}/{len(ids)}] Fetching date for ID: {gid}")
            date = get_original_publication_date(gid)
            if date:
                # Store as ISO string or just year? User asked for "String".
                # Let's store the full ISO string if it's a datetime, or the string if it's a BC string.
                if isinstance(date, datetime.datetime):
                    pub_dates[gid] = date.isoformat()
                else:
                    pub_dates[gid] = str(date)
            else:
                pub_dates[gid] = None
            
            # Be polite to Goodreads
            time.sleep(1.0)
            
        # Save output
        output_filename = f"pub_dates_{source_id}.json"
        # Save in the same directory as the script or current dir? 
        # User said "create a file called pub_dates_ID.json", didn't specify path.
        # Let's save it in the current working directory.
        with open(output_filename, 'w') as f:
            json.dump(pub_dates, f, indent=2)
            
        print(f"Successfully saved publication dates to {output_filename}")

    except Exception as e:
        print(f"Error generating pub dates map: {e}")

if __name__ == "__main__":
    # Test with "The Republic" (ID: 30289) -> Orig: ~375 BC
    # test_id = "30289"
    # date = get_original_publication_date(test_id)
    # print(f"Original Publication Date for {test_id}: {date}")
    
    # Test bulk generation if a file argument is provided
    import sys
    if len(sys.argv) > 1:
        generate_pub_dates_map(sys.argv[1])
    else:
        print("Usage: python lib/goodreads_scraper.py <input_json_file>")
