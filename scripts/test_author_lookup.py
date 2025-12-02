import sys
import os

# Add project root to path
sys.path.append(os.getcwd())

from lib.bibliography_agent.bibliography_tool import SQLiteWikiPeopleIndex

def test_overrides():
    print("Initializing SQLiteWikiPeopleIndex with trace=True...")
    index = SQLiteWikiPeopleIndex(trace=True)
    
    tests = [
        ("Plato", -428),      # Should be overridden
        ("Sallust", -86),     # Should be overridden (Sallust the historian, 86 BC)
        ("Herodotus", -484),  # Should be overridden
        ("Plato (comic)", None) # Should NOT be overridden (no match in overrides)
    ]
    
    print("\n--- Running Tests ---")
    for name, expected_birth in tests:
        print(f"\nQuerying: {name}")
        results = index.find_people(name, limit=1)
        
        if not results:
            print(f"  No results found for {name}")
            continue
            
        match = results[0]
        birth = match.get("birth_year")
        title = match.get("title")
        
        print(f"  Result: {title} (Born: {birth})")
        
        if expected_birth is not None:
            if birth == expected_birth:
                print(f"  ✅ SUCCESS: Matches expected override {expected_birth}")
            else:
                print(f"  ❌ FAILURE: Expected {expected_birth}, got {birth}")
        else:
            print(f"  ℹ️  Info: No override expected (DB value used)")

if __name__ == "__main__":
    test_overrides()
