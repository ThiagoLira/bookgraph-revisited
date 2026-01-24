
import sys
import json
from pathlib import Path

# Add repo root to path to import lib
repo_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repo_root))

from lib.bibliography_agent.bibliography_tool import SQLiteGoodreadsCatalog, GoodreadsAuthorCatalog

def main():
    books_db = SQLiteGoodreadsCatalog(db_path="datasets/books_index.db", trace=True)
    # authors_db = GoodreadsAuthorCatalog("datasets/goodreads_book_authors.json") 
    
    # List of (Title, Author) tuples to search for.
    # If Author is None, will search title only (risky for common titles).
    # If Title is None, will search Author only.
    target_citations = [
        ("The End of the Road", "John Barth"),
        ("The Sot-Weed Factor", "John Barth"),
        ("The Recognitions", "William Gaddis"),
        ("The Crying of Lot 49", "Thomas Pynchon"),
        ("The Whole Truth", "James Cummin"),
        ("The Public Burning", "Robert Coover"), # Text says "A Public Burning"
        ("A Political Fable", "Robert Coover"),
        ("The Propheteers", "Max Apple"),
        ("And Other Travels", "Bill Knott"),
        ("Arrested Saturday Night", "Stephen Dobyns"),
        ("Crash Course", "Bill Knott"), # Poem? might be in a book
        ("White Noise", "Don DeLillo"),
        ("Great Jones Street", "Don DeLillo"),
        ("The Oranging of America", "Max Apple"),
        ("Krazy Kat", "Jay Cantor"),
        ("You Bright and Risen Angels", "William T. Vollmann"),
        ("Movies", "Stephen Dixon"), # "Movies: Seventeen Stories"
        ("Libra", "Don DeLillo"),
        ("The Safety of Objects", "A. M. Homes"),
        ("The Rainbow Stories", "William T. Vollmann"),
        ("Fort Wayne Is Seventh on Hitler's List", "Michael Martone"),
        ("My Cousin, My Gastroenterologist", "Mark Leyner"),
        ("The Dharma Bums", "Jack Kerouac"),
        ("Candide", "Voltaire"),
        ("Bright Lights, Big City", "Jay McInerney"), # Referred to as "Bright Lights"
        ("A Night at the Movies", "Robert Coover"),
        ("You Must Remember This", "Robert Coover"),
        ("Life after Television", "George Gilder"),
    ]

    # Additional Authors mentioned by last name or full name in text
    target_authors = [
        "Norman Mailer",
        "Jay McInerney",
        "Tama Janowitz",
        "Louise Erdrich",
        "Ralph Waldo Emerson",
        "Octavio Paz",
        "James Joyce",
        "Vladimir Nabokov",
        "Honore de Balzac",
        "Samuel Huntington",
        "Barbara Tuchman",
        "Alexis de Tocqueville", # de Tocqueville
        "Stanley Cavell",
        "Lewis Hyde",
        "Janet Maslin", # Critic, maybe has books indexed?
        "David Leavitt",
    ]

    results = []

    print("Searching for Books...")
    authors_db = GoodreadsAuthorCatalog("datasets/goodreads_book_authors.json") 
    
    for title, author in target_citations:
        print(f"Searching: {title} by {author}")
        matches = books_db.find_books(title=title, author=author, limit=1)
        if matches:
            best = matches[0]
            print(f"  FOUND BOOK: {best['title']} (ID: {best['book_id']})")
            results.append({
                "citation": {
                    "title": title,
                    "author": author,
                    "citation_excerpt": f"Expected citation matching {title}" 
                },
                "expected_match": {
                    "book_id": best['book_id'],
                    "title": best['title'],
                    "author_ids": best.get('author_ids', []),
                    "match_type": "book"
                }
            })
        else:
            print(f"  BOOK NOT FOUND: {title}. Checking Author...")
            # Fallback to author lookup
            if author:
                # Reuse authors_db which we will initialize earlier
                auth_matches = authors_db.find_authors(query=author, limit=1)
                if auth_matches:
                    best_auth = auth_matches[0]
                    print(f"    FOUND AUTHOR: {best_auth['name']} (ID: {best_auth['author_id']})")
                    results.append({
                        "citation": {
                            "title": title,
                            "author": author,
                            "citation_excerpt": f"Expected citation matching {title}"
                        },
                        "expected_match": {
                            "author_id": best_auth['author_id'],
                            "name": best_auth['name'],
                            "match_type": "author"
                        }
                    })
                    continue
            
            print(f"    NOT FOUND ANY MATCH for {title} / {author}")
            results.append({
                "citation": {
                    "title": title,
                    "author": author,
                    "citation_excerpt": f"Expected citation matching {title}"
                },
                "expected_match": None
            })

    print("\nSearching for Authors (Author-only citations)...")
    # For authors, we just want to verify they exist in our DB and get their ID?
    # But the format of ground truth JSON expects a "citation" (from text) and "expected_match".
    # For author-only citations, the expected match is an Author object (no book_id usually, or we match an author).
    # But our pipeline output for author-only has "match_type": "author" and metadata.
    
    # We need to instantiate the author catalog too if we want to confirm them.
    # But since we are mocking the 'expected_match', let's just assume if we find them in book search (as author) 
    # or just create a placeholder if we assume they are valid.
    # However, to be accurate, let's use the Author Catalog if possible. 
    # But the script commented out `authors_db`. Let's uncomment it.
    
    authors_db = GoodreadsAuthorCatalog("datasets/goodreads_book_authors.json") 
    
    for author_name in target_authors:
        print(f"Searching Author: {author_name}")
        matches = authors_db.find_authors(query=author_name, limit=1)
        if matches:
            best = matches[0]
            print(f"  FOUND: {best['name']} (ID: {best['author_id']})")
            results.append({
                "citation": {
                    "title": None,
                    "author": author_name,
                    "citation_excerpt": f"Expected citation for {author_name}"
                },
                "expected_match": {
                    "author_id": best['author_id'],
                    "name": best['name'],
                    "match_type": "author"
                }
            })
        else:
            print(f"  NOT FOUND: {author_name}")
            results.append({
                "citation": {
                    "title": None,
                    "author": author_name,
                    "citation_excerpt": f"Expected citation for {author_name}"
                },
                "expected_match": None
            })

    output_path = Path(__file__).parent / "ground_truth.json"
    output_path.write_text(json.dumps(results, indent=2))
    print(f"\nWrote {len(results)} entries to {output_path}")

if __name__ == "__main__":
    main()
