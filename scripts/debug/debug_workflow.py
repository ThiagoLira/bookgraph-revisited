import sys
from pathlib import Path
import asyncio
from unittest.mock import MagicMock
from llama_index.core.llms import LLM
from pydantic import BaseModel

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from lib.bibliography_agent.citation_workflow import CitationWorkflow, SearchResultsEvent, QueryList, ValidationResult, SearchQuery

class MockLLM(LLM):
    def __init__(self):
        super().__init__()
    
    async def acomplete(self, prompt, **kwargs):
        return MagicMock(text="Mock response")
        
    async def astructured_predict(self, output_cls, prompt, **kwargs):
        print(f"MockLLM called for {output_cls.__name__}")
        if output_cls.__name__ == "QueryList":
            return output_cls(queries=[SearchQuery(title="Test Query", author="Test Author")])
        elif output_cls.__name__ == "ValidationResult":
            return output_cls(index=0, reasoning="Mock reasoning")
        return None

    def chat(self, messages, **kwargs): return MagicMock()
    def stream_chat(self, messages, **kwargs): return MagicMock()
    async def achat(self, messages, **kwargs): return MagicMock()
    async def astream_chat(self, messages, **kwargs): return MagicMock()
    def complete(self, prompt, **kwargs): return MagicMock()
    def stream_complete(self, prompt, **kwargs): return MagicMock()
    async def astream_complete(self, prompt, **kwargs): return MagicMock()
    
    @property
    def metadata(self):
        return MagicMock()

from llama_index.core.workflow import Workflow, step, Context, StartEvent, StopEvent

class TestWorkflow(Workflow):
    @step
    async def start(self, ctx: Context, ev: StartEvent) -> SearchResultsEvent:
        print("TestWorkflow: Start step")
        return SearchResultsEvent(citation={}, results=[], source="test", mode="book")

    @step
    async def validate(self, ctx: Context, ev: SearchResultsEvent) -> StopEvent:
        print("TestWorkflow: Validate step")
        return StopEvent(result="Success")

async def main():
    print("--- Running TestWorkflow ---")
    tw = TestWorkflow(timeout=10, verbose=True)
    try:
        res = await tw.run()
        print(f"TestWorkflow Result: {res}")
    except Exception as e:
        print(f"TestWorkflow Failed: {e}")

    print("\n--- Running CitationWorkflow ---")
    # ... existing code ...
    mock_llm = MockLLM()
    w = CitationWorkflow(
        books_db_path="goodreads_data/books_index.db",
        authors_path="goodreads_data/goodreads_book_authors.json",
        wiki_people_path="goodreads_data/wiki_people_index.db",
        llm=mock_llm,
        verbose=True
    )
    
    print("\nRunning Workflow...")
    try:
        result = await w.run(citation={"title": "Test Book", "author": "Test Author"})
        print(f"Result: {result}")
    except Exception as e:
        print(f"Workflow failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
