
import json
import sys
import subprocess
from pathlib import Path

# Add repo root to path
repo_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repo_root))

from preprocess_citations import preprocess

def main():
    library_name = "manual_test"
    output_dir = repo_root / "calibre_outputs" / library_name
    
    raw_dir = output_dir / "raw_extracted_citations"
    pre_dir = output_dir / "preprocessed_extracted_citations"
    final_dir = output_dir / "final_citations_metadata_goodreads"
    
    raw_dir.mkdir(parents=True, exist_ok=True)
    pre_dir.mkdir(parents=True, exist_ok=True)
    final_dir.mkdir(parents=True, exist_ok=True)

    # 1. Create Raw Extraction (Simulated)
    # Based on manual reading of DFW-PLURIBUS.txt
    
    # We pretend the book ID is "DFW-PLURIBUS" (or a fake Goodreads ID if we had one, but using filename as key for now)
    # The pipeline usually uses Goodreads ID as filename. Let's use '1000' as a dummy ID.
    book_id = "1000" 
    
    raw_citations = [
        # Page 1/Start
        {"author": "Mailer", "citation_excerpt": "The exceptions to this rule - Mailer, McInerney, Janowitz - create..."},
        {"author": "McInerney", "citation_excerpt": "The exceptions to this rule - Mailer, McInerney, Janowitz - create..."},
        {"author": "Janowitz", "citation_excerpt": "The exceptions to this rule - Mailer, McInerney, Janowitz - create..."},
        {"author": "Louise Erdrich", "citation_excerpt": "I suspect Louise Erdrich might."},
        
        # Middle - "Brat Pack" authors mentions?
        {"author": "Stendhal", "citation_excerpt": "Not the Stendhalian mirror reflecting..."},
        {"title": "Candide", "author": "Voltaire", "citation_excerpt": "The Voltaire of Candide, for instance, uses a bisensuous irony"},
        {"author": "Darwin", "citation_excerpt": "Darwinianly naturalistic"}, # Maybe skipped? Let's include as Author
        {"author": "Emerson", "citation_excerpt": "what Emerson, years before TV, called"},
        
        # Literary references section
        {"title": "The End of the Road", "author": "Barth", "citation_excerpt": "Barth of The End of the Road and The Sot-Weed Factor"},
        {"title": "The Sot-Weed Factor", "author": "Barth", "citation_excerpt": "Barth of The End of the Road and The Sot-Weed Factor"},
        {"title": "The Recognitions", "author": "Gaddis", "citation_excerpt": "Gaddis of The Recognitions"},
        {"title": "The Crying of Lot 49", "author": "Pynchon", "citation_excerpt": "Pynchon of The Crying of Lot 49"},
        {"title": "The Whole Truth", "author": "James Cummin", "citation_excerpt": "James Cummin's 1986 The Whole Truth"},
        {"title": "A Public Burning", "author": "Robert Coover", "citation_excerpt": "Robert Coover's 1977 A Public Burning"},
        {"title": "A Political Fable", "author": "Robert Coover", "citation_excerpt": "his 1980 A Political Fable"},
        {"title": "The Propheteers", "author": "Max Apple", "citation_excerpt": "Max Apple's 1986 The Propheteers"},
        {"title": "And Other Travels", "author": "Bill Knott", "citation_excerpt": "Bill Knott's 1974 \"And Other Travels\""},
        
        # Image-fiction section
        {"title": "Arrested Saturday Night", "author": "Stephen Dobyns", "citation_excerpt": "Stephen Dobyns's 1980 \"Arrested Saturday Night\""},
        {"title": "Crash Course", "author": "Knott", "citation_excerpt": "Knott's 1983 \"Crash Course\""},
        {"title": "White Noise", "author": "DeLillo", "citation_excerpt": "DeLillo's 1985 White Noise"},
        {"title": "Great Jones Street", "author": "DeLillo", "citation_excerpt": "The DeLillo of Great Jones Street"},
        {"title": "Burning", "author": "Coover", "citation_excerpt": "the Coover of Burning"},
        {"title": "The Oranging of America", "author": "Max Apple", "citation_excerpt": "Max Apple, whose seventies short story \"The Oranging of America\""},
        {"title": "Krazy Kat", "author": "Jay Cantor", "citation_excerpt": "Jay Cantor's Krazy Kat"},
        {"title": "You Bright and Risen Angels", "author": "William T. Vollmann", "citation_excerpt": "William T. Vollmann's You Bright and Risen Angels"},
        {"title": "Movies: Seventeen Stories", "author": "Stephen Dixon", "citation_excerpt": "Stephen Dixon's Movies: Seventeen Stories"},
        {"title": "Libra", "author": "DeLillo", "citation_excerpt": "DeLillo's own fictional hologram of Oswald in Libra"},
        {"title": "The Safety of Objects", "author": "A. M. Homes", "citation_excerpt": "A. M. Homes's 1990 The Safety of Objects"},
        {"title": "The Rainbow Stories", "author": "Vollmann", "citation_excerpt": "Vollmann's 1989 The Rainbow Stories"},
        {"title": "Fort Wayne Is Seventh on Hitler's List", "author": "Michael Martone", "citation_excerpt": "Michael Martone's 1990 Fort Wayne Is Seventh on Hitler's List"},
        {"title": "My Cousin, My Gastroenterologist", "author": "Mark Leyner", "citation_excerpt": "Mark Leyner's 1990 campus smash My Cousin, My Gastroenterologist"},
        {"title": "The Dharma Bums", "author": "Kerouac", "citation_excerpt": "since The Dharma Bums"}, 
        {"title": "Bright Lights, Big City", "author": "Jay McInerney", "citation_excerpt": "COMA BABY feature in Bright Lights"},
        {"title": "A Night at the Movies", "author": "Coover", "citation_excerpt": "Coover's A Night at the Movies"},
        {"title": "You Must Remember This", "author": "Coover", "citation_excerpt": "You Must Remember This"},
        {"title": "Life after Television", "author": "George Gilder", "citation_excerpt": "author of 1990's Life after Television"},
        {"author": "Samuel Huntington", "citation_excerpt": "conservative critics like Samuel Huntington"},
        {"author": "Barbara Tuchman", "citation_excerpt": "conservative critics like Samuel Huntington and Barbara Tuchman"},
        {"author": "Tocqueville", "citation_excerpt": "by 1830 de Tocqueville had already diagnosed"},
        {"author": "Stanley Cavell", "citation_excerpt": "what Stanley Cavell calls the reader's \"willingness to be pleased\""},
        {"author": "Lewis Hyde", "citation_excerpt": "as essayist Lewis Hyde points out"},
        {"author": "Janet Maslin", "citation_excerpt": "Janet Maslin locates her true anti-reality culprit"},
        {"author": "David Leavitt", "citation_excerpt": "David Leavitt's sole descriptions"},
        {"author": "Honore de Balzac", "citation_excerpt": "let's not even talk about Balzac"},
    ]

    raw_payload = {
        "source_path": str(repo_root / "DFW-PLURIBUS.txt"),
        "model": "Simulated-Human",
        "chunk_size": 50,
        "total_sentences": 100,
        "chunks": [
            {
                "chunk_index": 0,
                "start_sentence": 0,
                "end_sentence": 100,
                "citations": raw_citations
            }
        ],
        "failures": []
    }

    raw_path = raw_dir / f"{book_id}.json"
    raw_path.write_text(json.dumps(raw_payload, indent=2))
    print(f"Created Raw: {raw_path}")

    # 2. Run Preprocessing (Real)
    # We import the function directly to avoid subprocess overhead/path issues, 
    # but could run via subprocess.
    pre_payload = preprocess(raw_path, source_title="E Unibus Pluram", source_authors=["David Foster Wallace"])
    pre_path = pre_dir / f"{book_id}.json"
    pre_path.write_text(json.dumps(pre_payload, indent=2, ensure_ascii=False))
    print(f"Created Preprocessed: {pre_path}")

    # 3. Process Workflow (Simulated using Generate Ground Truth Results)
    # Load the matches found by generate_ground_truth.py
    gt_path = Path(__file__).parent / "ground_truth.json"
    if not gt_path.exists():
        print("Error: ground_truth.json not found. Run generate_ground_truth.py first.")
        return

    gt_data = json.loads(gt_path.read_text())
    
    # Map (Title, Author) -> Metadata
    lookup_map = {}
    for entry in gt_data:
        c = entry["citation"]
        m = entry["expected_match"]
        if m:
            # We key by the 'citation' title/author used in GT script
            # We need to match the preprocessed citation to this.
            # Normalization might be needed.
            key = (c["title"], c["author"])
            lookup_map[key] = m

            # Also add loose keys
            if c["title"]:
                lookup_map[(c["title"].lower(), c["author"].lower())] = m
    
    final_output = {
        "source": {
            "title": "E Unibus Pluram",
            "authors": ["David Foster Wallace"],
            "goodreads_id": book_id,
        },
        "citations": []
    }

    # Iterate through preprocessed citations and resolve
    for cit in pre_payload["citations"]:
        title = cit.get("title")
        author = cit.get("author")
        
        # Try to find in lookup map
        match_meta = None
        match_type = "not_found"

        # 1. Exact Key Lookup
        key = (title, author)
        if key in lookup_map:
            match_meta = lookup_map[key]
        
        # 2. Loose Lookup if no exact match
        if not match_meta:
             for (gt_title, gt_author), meta in lookup_map.items():
                if not meta: continue
                
                # Check Author
                author_match = False
                if author and gt_author and gt_author.lower() in author.lower():
                    author_match = True
                elif not author and not gt_author:
                    author_match = True # Both None? Unlikely
                
                if not author_match:
                    continue

                # Check Title
                title_match = False
                if title and gt_title and gt_title.lower() in title.lower():
                    title_match = True
                elif not title and not gt_title:
                    title_match = True
                
                # Special case: "Burning" -> "The Public Burning"
                if title == "Burning" and gt_title == "The Public Burning":
                    title_match = True
                
                if author_match and title_match:
                    match_meta = meta
                    break
        
        # 3. Fallback: Check for Author-only match in GT if we failed book match
        # (e.g. if we have citation for "Life after Television" (Book) but GT says match_type="author" for that citation)
        # The previous loop handles this if (Title, Author) maps to an Author Match in GT.
        # But what if citation has Title, but GT only has Author citation? (Unlikely with current script structure).
        # However, checking if match_meta is found.

        if match_meta:
             m_type = match_meta.get("match_type", "book") # Default to book if not specified
             if m_type == "book":
                 final_output["citations"].append({
                     "raw": cit,
                     "goodreads_match": match_meta,
                     "edge": {
                         "target_type": "book",
                         "target_book_id": match_meta["book_id"]
                     }
                 })
             elif m_type == "author":
                 final_output["citations"].append({
                     "raw": cit,
                     "goodreads_match": match_meta,
                     "edge": {
                         "target_type": "author",
                         "target_author_id": match_meta["author_id"]
                     }
                 })
        else:
            # Unresolved
             final_output["citations"].append({
                 "raw": cit,
                 "goodreads_match": {},
                 "edge": {
                     "target_type": "not_found"
                 }
             })

    final_path = final_dir / f"{book_id}.json"
    final_path.write_text(json.dumps(final_output, indent=2, ensure_ascii=False))
    print(f"Created Final: {final_path}")

if __name__ == "__main__":
    main()
