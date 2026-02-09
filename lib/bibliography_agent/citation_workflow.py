import asyncio
import json
import re
import logging
from typing import Any, Dict, List, Optional, Set, Union
from difflib import SequenceMatcher
from pathlib import Path

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

logger = logging.getLogger(__name__)

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

        # Make Wiki optional
        self.wiki_catalog = None
        if wiki_people_path and Path(wiki_people_path).exists():
            self.wiki_catalog = SQLiteWikiPeopleIndex(db_path=wiki_people_path, trace=verbose)
        else:
            logger.warning(f"[workflow] Wiki DB not found at {wiki_people_path}, skipping Wiki lookups.")

        self.llm = llm or OpenAI(model="gpt-4o-mini")

        # Load author aliases
        self.author_aliases = {}
        aliases_path = Path("datasets/author_aliases.json")
        if aliases_path.exists():
            raw = json.loads(aliases_path.read_text())
            # Build reverse mapping: variant -> canonical
            for canonical, variants in raw.items():
                self.author_aliases[canonical.lower()] = canonical
                for v in variants:
                    self.author_aliases[v.lower()] = canonical
            logger.info(f"[workflow] Loaded {len(self.author_aliases)} author aliases")

        logger.info(f"[workflow] Initialized. Books DB: {books_db_path}, Wiki DB: {'yes' if self.wiki_catalog else 'no'}")


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
            logger.warning("[workflow] No citation provided, stopping.")
            return StopEvent(result=None)

        title = citation.get("title")
        author = citation.get("author")

        # Expand author with aliases
        author_variants = [author] if author else []
        if author:
            # Check for known aliases - get canonical name
            canonical = self.author_aliases.get(author.lower())
            if canonical and canonical != author:
                author_variants.append(canonical)
                logger.debug(f"[workflow] Expanded '{author}' -> canonical '{canonical}'")

            # Also check if this IS the canonical, get variants
            for variant, canon in self.author_aliases.items():
                if canon.lower() == author.lower() and variant != author.lower():
                    author_variants.append(variant.title())

        mode = "book" if (title and title.strip()) else "author_only"

        logger.debug(f"[workflow] Generating queries for: title='{title}', author='{author}', variants={author_variants}, mode={mode}, retry={retry_count}")

        # Build context with author variants if available
        citation_context = dict(citation)
        if len(author_variants) > 1:
            citation_context["_author_variants"] = author_variants

        prompt = (
            f"You are a bibliography expert. Generate search queries for this citation.\n"
            f"Citation: {json.dumps(citation_context, ensure_ascii=False)}\n"
            f"Retry Attempt: {retry_count}\n\n"
        )

        if retry_count > 0:
            prompt += "Previous searches failed. Generate BROADER, FUZZIER, or ALTERNATIVE queries.\n"

        if len(author_variants) > 1:
            prompt += f"Note: The author may also be known as: {', '.join(author_variants[1:])}\n\n"

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

        max_attempts = 2
        for attempt in range(max_attempts):
            try:
                response = await self.llm.astructured_predict(QueryList, PromptTemplate(prompt))

                if self.verbose:
                    print(f"[Workflow] Generated Queries ({mode}): {response.queries}")

                logger.info(f"[workflow] Generated {len(response.queries)} queries for '{author or title}' (mode={mode})")
                return QueriesGeneratedEvent(citation=citation, queries=response.queries, mode=mode)

            except Exception as e:
                error_msg = str(e)
                logger.warning(f"[workflow] Query generation attempt {attempt+1}/{max_attempts} failed: {error_msg}")

                if attempt < max_attempts - 1:
                    # Retry with simplified prompt
                    prompt = (
                        f"Generate search queries for: author='{author}', title='{title}'.\n"
                        "Return a JSON object with a 'queries' field containing a list of objects.\n"
                        "Each object should have 'title' (string or null) and 'author' (string or null) fields.\n"
                        "Example: {{\"queries\": [{{\"title\": \"The Republic\", \"author\": \"Plato\"}}]}}"
                    )
                    await asyncio.sleep(0.5)  # Brief delay before retry
                else:
                    # Final fallback: generate a basic query ourselves
                    logger.warning(f"[workflow] All LLM attempts failed, using basic fallback query for '{author}'")
                    basic_queries = []
                    if author:
                        basic_queries.append(SearchQuery(title=title or "", author=author))
                        # Try last name only
                        parts = author.split()
                        if len(parts) > 1:
                            basic_queries.append(SearchQuery(title=title or "", author=parts[-1]))

                    if basic_queries:
                        return QueriesGeneratedEvent(citation=citation, queries=basic_queries, mode=mode)
                    else:
                        return StopEvent(result={"citation": citation, "error": error_msg, "match_type": "error"})

        return StopEvent(result={"citation": citation, "error": "Query generation failed", "match_type": "error"})

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

        logger.debug(f"[workflow] Goodreads search: {len(all_results)} candidates for '{citation.get('author')}'")
        return SearchResultsEvent(citation=citation, results=all_results, source="goodreads", mode=mode)

    @step
    async def search_wikipedia(
        self, ctx: Context, ev: QueriesGeneratedEvent
    ) -> SearchResultsEvent | StopEvent | None:
        # Runs for both "book" and "author_only"

        if self.wiki_catalog is None:
             if self.verbose:
                 print("[Workflow] Skipping Wikipedia search (DB missing).")
             return None

        queries = ev.queries
        citation = ev.citation

        all_results = []
        seen_ids = set()

        for q in queries:
            name = q.author
            if not name and ev.mode == "author_only":
                 name = q.title # Fallback if author field is misused

            if not name:
                continue

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
                if not source_text:
                     continue
                score = fuzzy_token_sort_ratio(source_text, target)
                scored.append((score, res))

            scored.sort(key=lambda x: x[0], reverse=True)
            all_results = [x[1] for x in scored[:5]]

        if self.verbose:
            print(f"[Workflow] Wikipedia Search Found {len(all_results)} candidates.")

        logger.debug(f"[workflow] Wikipedia search: {len(all_results)} candidates for '{citation.get('author')}'")
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
            logger.debug(f"[workflow] No {source} candidates to validate for '{citation.get('author')}'")
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

        selected_index = -1
        reasoning = ""

        try:
            if self.verbose:
                print("[Workflow] Calling LLM for validation...")
            response = await self.llm.astructured_predict(ValidationResult, PromptTemplate(prompt))
            if self.verbose:
                 print(f"[Workflow] Validation Raw Response type: {type(response)}")

            selected_index = response.index
            reasoning = response.reasoning
            logger.debug(f"[workflow] Validation idx: {selected_index} (type: {type(selected_index)})")

        except Exception as e:
            logger.warning(f"[workflow] Structured predict failed: {e}")
            # Fallback: Try direct completion with JSON parsing
            try:
                raw_response = await self.llm.acomplete(
                    prompt + "\n\nRespond with JSON only: {\"reasoning\": \"...\", \"index\": N}"
                )
                text = raw_response.text.strip()
                if text.startswith("```"):
                    text = text.split("\n", 1)[1].rsplit("```", 1)[0]
                data = json.loads(text)
                selected_index = int(data.get("index", -1))
                reasoning = data.get("reasoning", "JSON fallback")
                logger.info(f"[workflow] JSON fallback succeeded: index={selected_index}")
            except Exception as e2:
                logger.warning(f"[workflow] JSON fallback also failed: {e2}")
                # Final fallback: pick highest fuzzy score
                if candidates:
                    source_text = citation.get("title") if mode == "book" else citation.get("author")
                    if source_text:
                        best_score = 0
                        best_idx = -1
                        for i, c in enumerate(candidates):
                            target = c.get("title", "") if mode == "book" else c.get("title", c.get("name", ""))
                            score = fuzzy_token_sort_ratio(source_text, target)
                            if score > best_score and score > 70:  # Minimum threshold
                                best_score = score
                                best_idx = i

                        if best_idx >= 0:
                            selected_index = best_idx
                            reasoning = f"Score fallback: picked index {selected_index} with score {best_score}"
                            logger.info(f"[workflow] {reasoning}")

        selected = None
        if isinstance(selected_index, int) and 0 <= selected_index < len(candidates):
            selected = candidates[selected_index]

        logger.info(f"[workflow] Validation ({source}): index={selected_index}, selected={'yes' if selected else 'no'}")

        return ValidationEvent(
            citation=citation,
            selected_result=selected,
            source=source,
            mode=mode,
            reasoning=reasoning
        )

    @step
    async def aggregate_results(
        self, ctx: Context, ev: ValidationEvent
    ) -> StopEvent | RetryEvent | None:
        logger.debug(f"[workflow] Aggregating results for {ev.source}")
        mode = ev.mode

        # Store result in context
        results_key = "results"
        current_results = await ctx.store.get(results_key, default={})
        current_results[ev.source] = ev.selected_result
        await ctx.store.set(results_key, current_results)

        # Wait for both events if possible, OR proceed if one is sufficient but we prefer enrichment
        # We generally expect 'goodreads' and 'wikipedia' events if valid.

        # Check if we have received both expected events?
        # A robust way is to check if we have results for 'goodreads' and 'wikipedia' keys.
        # But if wikipedia search was skipped (e.g. no author name), we might never get it?
        # Actually search_wikipedia emits SearchResultsEvent even if empty, so validate_matches emits ValidationEvent.
        # UNLESS search_wikipedia returns None early.
        # I updated search_wikipedia to run for book mode.

        has_gr = "goodreads" in current_results
        has_wiki = "wikipedia" in current_results

        if has_gr and has_wiki:
            gr_res = current_results["goodreads"]
            wiki_res = current_results["wikipedia"]

            final_metadata = {}
            match_type = "not_found"

            if mode == "book":
                if gr_res:
                    final_metadata.update(gr_res)
                    match_type = "book"
                    # Add enrichment
                    if wiki_res:
                        final_metadata["wikipedia_match"] = wiki_res
                else:
                     # Failed to find book.
                     # Should we fall back to author match?
                     # For now, let's stick to "not_found" or retry.
                     # But if we found the author in Wiki, maybe we should report "person" only?
                     # The requirement is to fix missing metadata for BOOKS.
                     # So if book is missing, we probably want to retry looking for the book.
                     pass

            elif mode == "author_only":
                if gr_res:
                    final_metadata.update(gr_res)
                    match_type = "author"

                if wiki_res:
                    final_metadata["wikipedia_match"] = wiki_res
                    if match_type == "not_found":
                        match_type = "person"

            citation = ev.citation
            logger.info(f"[workflow] Result for '{citation.get('author')}': match_type={match_type}, gr={'yes' if gr_res else 'no'}, wiki={'yes' if wiki_res else 'no'}")

            # Retry logic if NOTHING found (for book mode, if GR is missing)
            if mode == "book" and not gr_res:
                 return await self._handle_retry(ctx, ev.citation)
            if mode == "author_only" and match_type == "not_found":
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
            logger.info(f"[workflow] Retrying '{citation.get('author')}' ({new_count}/3)")

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
            logger.warning(f"[workflow] Max retries exceeded for '{citation.get('author')}'")
            return StopEvent(result={"match_type": "not_found", "metadata": {}, "reasoning": "Max retries exceeded."})
