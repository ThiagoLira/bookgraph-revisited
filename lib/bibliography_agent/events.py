from typing import Any, Dict, List, Optional
from llama_index.core.workflow import Event
from pydantic import BaseModel, Field

class SearchQuery(BaseModel):
    title: Optional[str] = Field(None, description="Book title to search for.")
    author: Optional[str] = Field(None, description="Author name to search for.")

class QueriesGeneratedEvent(Event):
    citation: Dict[str, Any]
    queries: List[SearchQuery]
    mode: str  # "book" or "author_only"

class SearchResultsEvent(Event):
    citation: Dict[str, Any]
    results: List[Dict[str, Any]]
    source: str  # "goodreads" or "wikipedia"
    mode: str

class ValidationEvent(Event):
    citation: Dict[str, Any]
    selected_result: Optional[Dict[str, Any]]
    source: str
    mode: str
    reasoning: str

class RetryEvent(Event):
    citation: Dict[str, Any]
    retry_count: int
