import asyncio
import json
import re
from typing import Any, Dict, List, Optional, Set, Union
from difflib import SequenceMatcher

from llama_index.core.workflow import (
    Context,
    StartEvent,
    StopEvent,
    Workflow,
    step,
    Event,
)
from llama_index.core import PromptTemplate
from llama_index.core.llms import LLM
from llama_index.llms.openai import OpenAI
from pydantic import BaseModel, Field

from lib.bibliography_agent.bibliography_tool import (
    SQLiteGoodreadsCatalog,
    GoodreadsAuthorCatalog,
    SQLiteWikiPeopleIndex,
)

# --- Helpers ---

def fuzzy_token_sort_ratio(s1: str, s2: str) -> int:
    """
    Mimics fuzzywuzzy.token_sort_ratio using difflib.
    1. Tokenize and lower case.
    2. Sort tokens.
    3. Rejoin.
    4. Calculate ratio.
    """
    if not s1 or not s2:
        return 0
    
    tokens1 = sorted(re.findall(r'\w+', s1.lower()))
    tokens2 = sorted(re.findall(r'\w+', s2.lower()))
    
    sorted_s1 = " ".join(tokens1)
    sorted_s2 = " ".join(tokens2)
    
    matcher = SequenceMatcher(None, sorted_s1, sorted_s2)
    return int(matcher.ratio() * 100)

from lib.bibliography_agent.events import (
    QueriesGeneratedEvent,
    SearchResultsEvent,
    ValidationEvent,
    RetryEvent,
    SearchQuery,
)

# --- Helpers ---

# --- LLM Schemas ---


class QueryList(BaseModel):
    queries: List[SearchQuery] = Field(..., description="List of search queries.")

class ValidationResult(BaseModel):
    reasoning: str = Field(..., description="Reasoning for the selection.")
    index: int = Field(..., description="Index of the selected match in the provided list, or -1 if none are good.")

# --- Workflow ---

class CitationWorkflow(Workflow):
    def __init__(
        self,
        books_db_path: str,
        authors_path: str,
        wiki_people_path: str,
        llm: Optional[LLM] = None,
        timeout: Optional[float] = None,
        verbose: bool = False,
    ):
        super().__init__(timeout=timeout, verbose=verbose)
        self.verbose = verbose
        self.book_catalog = SQLiteGoodreadsCatalog(db_path=books_db_path, trace=verbose)
        self.author_catalog = GoodreadsAuthorCatalog(authors_path=authors_path)
        self.wiki_catalog = SQLiteWikiPeopleIndex(db_path=wiki_people_path, trace=verbose)
        self.llm = llm or OpenAI(model="gpt-4o-mini")


    @step
    async def generate_queries(
        self, ctx: Context, ev: Union[StartEvent, RetryEvent]
    ) -> QueriesGeneratedEvent | StopEvent:
        citation = None
        retry_count = 0
        
        if isinstance(ev, StartEvent):
            citation = ev.get("citation")
            await ctx.store.set("retry_count", 0)
            if citation:
                await ctx.store.set("citation", citation)
        elif isinstance(ev, RetryEvent):
            citation = ev.citation
            retry_count = ev.retry_count
            
        if not citation:
            return StopEvent(result=None)

        title = citation.get("title")
        author = citation.get("author")
        
        mode = "book" if (title and title.strip()) else "author_only"
        
        prompt = (
            f"You are a bibliography expert. Generate search queries for this citation.\n"
            f"Citation: {json.dumps(citation, ensure_ascii=False)}\n"
            f"Retry Attempt: {retry_count}\n\n"
        )
        
        if retry_count > 0:
            prompt += "Previous searches failed. Generate BROADER, FUZZIER, or ALTERNATIVE queries.\n"
        
        if mode == "book":
            prompt += (
                "The citation has a title. Generate a list of structured queries to find this BOOK in Goodreads.\n"
                "For each query, provide:\n"
                "- 'title': The book title to search for (try exact, no subtitle, spelling corrections).\n"
                "- 'author': The author name to filter by (try exact, last name only, variations). \n"
                "  IMPORTANT: Always include the author if known, to filter out same-titled books by others.\n"
            )
        else:
            prompt += (
                "The citation is AUTHOR ONLY. Generate a list of queries to find this AUTHOR.\n"
                "For each query, provide:\n"
                "- 'author': The author name to search for (variations, removing initials).\n"
                "- 'title': Leave empty.\n"
            )

        try:
            # Try standard structured predict first
            response = await self.llm.astructured_predict(QueryList, PromptTemplate(prompt))
            
            # If we got a string, it failed to parse internally but didn't raise.
            if isinstance(response, str):
                 raise ValueError(f"astructured_predict returned string: {response[:100]}")

        except Exception as e:
            if self.verbose:
                print(f"[Workflow] astructured_predict failed: {e}. Falling back to apredict.")
            
            # Fallback: Manual JSON prompt
            json_prompt = prompt + f"\nRespond strictly with a JSON object matching this schema:\n{QueryList.model_json_schema()}"
            raw_response = await self.llm.apredict(PromptTemplate(json_prompt))
            
            if self.verbose:
                print(f"[Workflow] Fallback Raw Response: {raw_response}")

            # Parse
            match = re.search(r"\{.*\}", raw_response, re.DOTALL)
            if match:
                clean_response = match.group(0)
                data = json.loads(clean_response)
                response = QueryList(**data)
            else:
                raise ValueError(f"Could not parse JSON from fallback response: {raw_response[:200]}")

        if self.verbose:
            print(f"[Workflow] Generated Queries ({mode}): {response.queries}")
        
        return QueriesGeneratedEvent(citation=citation, queries=response.queries, mode=mode)

    @step
    async def search_goodreads(
        self, ctx: Context, ev: QueriesGeneratedEvent
    ) -> SearchResultsEvent:
        # Runs for both "book" and "author_only" modes
        queries = ev.queries
        mode = ev.mode
        citation = ev.citation
        
        all_results = []
        seen_ids = set()

        for q in queries:
            if mode == "book":
                # Search books with title and author
                matches = self.book_catalog.find_books(title=q.title, author=q.author, limit=5)
            else:
                # Search authors
                # Use author field if present, else title (fallback)
                name = q.author or q.title
                matches = self.author_catalog.find_authors(query=name, limit=5)
            
            for m in matches:
                # Deduplicate
                mid = m.get("book_id") if mode == "book" else m.get("author_id")
                if mid and mid not in seen_ids:
                    all_results.append(m)
                    seen_ids.add(mid)

        # Filter top 5 by fuzzy score
        if len(all_results) > 5:
            scored = []
            for res in all_results:
                target = ""
                if mode == "book":
                    target = res.get("title", "")
                else:
                    target = res.get("name", "")
                
                # Score against the best matching query (or the original citation field)
                # Let's score against the original citation field for stability
                source_text = citation.get("title") if mode == "book" else citation.get("author")
                if not source_text:
                    # Fallback to query text
                    source_text = queries[0].title if mode == "book" else queries[0].author
                
                score = fuzzy_token_sort_ratio(source_text, target)
                scored.append((score, res))
            
            scored.sort(key=lambda x: x[0], reverse=True)
            all_results = [x[1] for x in scored[:5]]

        if self.verbose:
            print(f"[Workflow] Goodreads Search Found {len(all_results)} candidates.")
            print(f"[Workflow] Returning SearchResultsEvent for {mode}")

        return SearchResultsEvent(citation=citation, results=all_results, source="goodreads", mode=mode)

    @step
    async def search_wikipedia(
        self, ctx: Context, ev: QueriesGeneratedEvent
    ) -> SearchResultsEvent | StopEvent | None:
        # Only runs for "author_only" mode
        if ev.mode != "author_only":
            return None # Do not stop the workflow, just produce no event

        queries = ev.queries
        citation = ev.citation
        
        all_results = []
        seen_ids = set()

        for q in queries:
            name = q.author or q.title
            matches = self.wiki_catalog.find_people(name=name, limit=5)
            for m in matches:
                mid = m.get("page_id")
                if mid and mid not in seen_ids:
                    all_results.append(m)
                    seen_ids.add(mid)
        
        # Filter top 5
        if len(all_results) > 5:
            scored = []
            for res in all_results:
                target = res.get("title", "")
                source_text = citation.get("author") or queries[0].author
                score = fuzzy_token_sort_ratio(source_text, target)
                scored.append((score, res))
            
            scored.sort(key=lambda x: x[0], reverse=True)
            all_results = [x[1] for x in scored[:5]]

        if self.verbose:
            print(f"[Workflow] Wikipedia Search Found {len(all_results)} candidates.")

        return SearchResultsEvent(citation=citation, results=all_results, source="wikipedia", mode=ev.mode)

    @step
    async def validate_matches(
        self, ctx: Context, ev: SearchResultsEvent
    ) -> ValidationEvent:
        if self.verbose:
            print(f"[Workflow] Entering validate_matches for {ev.source}")
        citation = ev.citation
        candidates = ev.results
        source = ev.source
        mode = ev.mode

        if not candidates:
            if self.verbose:
                print("[Workflow] No candidates to validate.")
            return ValidationEvent(citation=citation, selected_result=None, source=source, mode=mode, reasoning="No candidates found.")

        prompt = (
            f"You are a bibliography expert. Validate these candidates against the citation.\n"
            f"Citation: {json.dumps(citation, ensure_ascii=False)}\n"
            f"Candidates ({source}):\n"
        )
        for i, c in enumerate(candidates):
            prompt += f"[{i}] {json.dumps(c, ensure_ascii=False)}\n"
        
        prompt += (
            "\nAnalyze the candidates. Which one is the correct match?\n"
            "Return the index of the best match, or -1 if none are good.\n"
            "Provide reasoning."
        )

        try:
            if self.verbose:
                print("[Workflow] Calling LLM for validation...")
            
            response = await self.llm.astructured_predict(ValidationResult, PromptTemplate(prompt))
             # If we got a string, it failed to parse internally but didn't raise.
            if isinstance(response, str):
                 raise ValueError(f"astructured_predict returned string: {response[:100]}")

        except Exception as e:
            if self.verbose:
                print(f"[Workflow] astructured_predict validation failed: {e}. Falling back to apredict.")
            
            json_prompt = prompt + f"\nRespond strictly with a JSON object matching this schema:\n{ValidationResult.model_json_schema()}"
            raw_response = await self.llm.apredict(PromptTemplate(json_prompt))
            
            if self.verbose:
                print(f"[Workflow] Fallback Validation Response: {raw_response}")

            match = re.search(r"\{.*\}", raw_response, re.DOTALL)
            if match:
                clean_response = match.group(0)
                data = json.loads(clean_response)
                response = ValidationResult(**data)
            else:
                raise ValueError(f"Could not parse JSON from fallback response: {raw_response[:200]}")

        idx = response.index
        selected = None
        if 0 <= idx < len(candidates):
            selected = candidates[idx]
            
            if self.verbose:
                print(f"[Workflow] Validation ({source}): Selected index {idx}. Reason: {response.reasoning}")

            return ValidationEvent(
                citation=citation, 
                selected_result=selected, 
                source=source, 
                mode=mode, 
                reasoning=response.reasoning
            )

    @step
    async def aggregate_results(
        self, ctx: Context, ev: ValidationEvent
    ) -> StopEvent | RetryEvent | None:
        if self.verbose:
            print(f"[Workflow] Entering aggregate_results for {ev.source}")
        mode = ev.mode
        
        # Store result in context
        results_key = "results"
        current_results = await ctx.store.get(results_key, default={})
        current_results[ev.source] = ev.selected_result
        await ctx.store.set(results_key, current_results)

        # Check if we are done
        if mode == "book":
            # Book mode only waits for Goodreads
            # (We don't search Wikipedia for books in this design, only authors)
            final_result = {
                "match_type": "book" if ev.selected_result else "not_found",
                "metadata": ev.selected_result or {},
                "reasoning": ev.reasoning
            }
            
            # Retry logic
            if not ev.selected_result:
                return await self._handle_retry(ctx, ev.citation)
            
            return StopEvent(result=final_result)
        
        elif mode == "author_only":
            # Wait for both Goodreads and Wikipedia
            # We need to know if we have received both.
            # Since events come in one by one, we check if we have both keys.
            # BUT, if one fails/stops early (e.g. no queries), we might hang.
            # However, search steps always emit SearchResultsEvent (even empty), 
            # and validate always emits ValidationEvent.
            # So we should eventually get both.
            
            if "goodreads" in current_results and "wikipedia" in current_results:
                gr_res = current_results["goodreads"]
                wiki_res = current_results["wikipedia"]
                
                final_metadata = {}
                match_type = "not_found"
                
                if gr_res:
                    final_metadata.update(gr_res)
                    match_type = "author"
                
                if wiki_res:
                    final_metadata["wikipedia_match"] = wiki_res
                    if match_type == "not_found":
                        match_type = "person" # Found in wiki but not goodreads
                
                # Retry logic if NOTHING found
                if not gr_res and not wiki_res:
                    return await self._handle_retry(ctx, ev.citation)

                return StopEvent(result={
                    "match_type": match_type,
                    "metadata": final_metadata,
                    "reasoning": "Aggregated results."
                })
            
            return None # Wait for other event

    async def _handle_retry(self, ctx: Context, citation: Dict[str, Any]) -> StopEvent | RetryEvent:
        retry_count = await ctx.store.get("retry_count", default=0)
        if retry_count < 3:
            new_count = retry_count + 1
            await ctx.store.set("retry_count", new_count)
            if self.verbose:
                print(f"[Workflow] Retrying... ({new_count}/3)")
            
            # Re-trigger query generation
            # We might want to modify the prompt to be broader, but for now just re-running
            # (The LLM is stateless here unless we pass history, but maybe randomness helps, 
            # or we could pass 'retry_count' to generate_queries to ask for broader queries).
            # To do that properly, we'd need to emit an event that generate_queries listens to,
            # or call it directly. 
            # Since generate_queries listens to StartEvent, we can't easily loop back to it 
            # without a custom event or recursively calling.
            # LlamaIndex Workflows allow steps to listen to multiple events.
            # Let's make generate_queries listen to a RetryEvent too.
            return RetryEvent(citation=citation, retry_count=new_count)
        else:
            return StopEvent(result={"match_type": "not_found", "metadata": {}, "reasoning": "Max retries exceeded."})

