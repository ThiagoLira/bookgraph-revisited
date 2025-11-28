import asyncio
import sys
import os
from unittest.mock import MagicMock, patch, AsyncMock

# Add root to path
sys.path.append(os.getcwd())

from lib.bibliography_agent.citation_workflow import CitationWorkflow, QueryList, ValidationResult

async def run_tests():
    print("Running tests...")
    
    with patch("lib.bibliography_agent.citation_workflow.SQLiteGoodreadsCatalog") as mock_books, \
         patch("lib.bibliography_agent.citation_workflow.GoodreadsAuthorCatalog") as mock_authors, \
         patch("lib.bibliography_agent.citation_workflow.SQLiteWikiPeopleIndex") as mock_wiki:
        
        # Mock LLM
        mock_llm = MagicMock()
        mock_llm.astructured_predict = AsyncMock()

        # Helper to mock LLM responses based on expected return type
        def side_effect(output_cls, prompt, **kwargs):
            if output_cls == QueryList:
                # Return queries based on prompt content (simple heuristic)
                if "The Hobbit" in prompt:
                    return QueryList(queries=["The Hobbit", "Hobbit"])
                elif "Tolkien" in prompt:
                    return QueryList(queries=["Tolkien", "J.R.R. Tolkien"])
                return QueryList(queries=["Generic Query"])
            elif output_cls == ValidationResult:
                # Return validation result
                # We assume index 0 is always the best for this test
                return ValidationResult(reasoning="It matches perfectly.", index=0)
            return None
        
        mock_llm.astructured_predict.side_effect = side_effect

        # Test 1: Book Lookup Success
        # Setup DB mock
        mock_books.return_value.find_books.return_value = [{"title": "The Hobbit", "author": "Tolkien", "book_id": "123"}]
        
        workflow = CitationWorkflow("books.db", "authors.json", "wiki.db", llm=mock_llm, verbose=True)
        citation = {"title": "The Hobbit", "author": "Tolkien"}
        result = await workflow.run(citation=citation)
        
        assert result["match_type"] == "book"
        assert result["metadata"]["book_id"] == "123"
        print("Test 1 Passed: Book Lookup Success")
        
        # Test 2: Author Only (Parallel)
        # Setup DB mocks
        mock_authors.return_value.find_authors.return_value = [{"name": "J.R.R. Tolkien", "author_id": "999"}]
        mock_wiki.return_value.find_people.return_value = [{"title": "J.R.R. Tolkien", "page_id": "111"}]
        
        citation = {"title": "", "author": "Tolkien"}
        result = await workflow.run(citation=citation)
        
        assert result["match_type"] == "author" # or person if only wiki found, but here both
        assert result["metadata"]["author_id"] == "999"
        assert result["metadata"]["wikipedia_match"]["page_id"] == "111"
        print("Test 2 Passed: Author Only (Parallel)")

        # Test 3: Retry Logic (Simulated)
        # First query returns nothing, second attempt (retry) returns something
        # We need to simulate the DB returning nothing first time.
        # But the DB mock is static here.
        # We can use side_effect on find_books to return empty first, then result.
        mock_books.return_value.find_books.side_effect = [[], [{"title": "The Hobbit", "book_id": "123"}]]
        
        citation = {"title": "The Hobbit", "author": "Tolkien"}
        # We need to reset the LLM side effect to ensure it generates queries
        # The workflow will call generate_queries -> find_books (empty) -> validate (empty list -> index -1?)
        # Wait, if find_books returns empty, validate_matches returns "No candidates found" (index -1 effectively or None selected).
        # Then aggregate_results sees no selected result and triggers retry.
        # Then generate_queries called again (RetryEvent).
        # Then find_books called again (returns match).
        # Then validate_matches called again (returns index 0).
        # Then aggregate_results returns StopEvent.
        
        # We need to update side_effect for ValidationResult to handle empty candidates case if called?
        # In validate_matches: "if not candidates: return ... selected_result=None"
        # So LLM is NOT called if candidates are empty.
        
        result = await workflow.run(citation=citation)
        assert result["match_type"] == "book"
        assert result["metadata"]["book_id"] == "123"
        print("Test 3 Passed: Retry Logic")

if __name__ == "__main__":
    asyncio.run(run_tests())
