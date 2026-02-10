import json
import asyncio
import re
from pathlib import Path
from typing import Dict, Any, Optional, TYPE_CHECKING
import logging

from llama_index.core.llms import LLM
from lib.bibliography_agent.llm_utils import build_llm
from lib.goodreads_scraper import get_original_publication_date
from lib.wikipedia_agent import WikipediaLookup

if TYPE_CHECKING:
    from lib.bibliography_agent.bibliography_tool import SQLiteWikiPeopleIndex

logger = logging.getLogger(__name__)

MAX_LIFESPAN = 120


def validate_dates(birth, death):
    """Sanitize a birth/death pair. Returns (birth, death) with fixes applied."""
    if birth is None or death is None:
        return birth, death

    # Sign error on death: birth>0, death<0, plausible lifespan
    if birth > 0 and death < 0 and 0 < (abs(death) - birth) < MAX_LIFESPAN:
        return birth, abs(death)

    # Sign error on birth: birth<0, death>0, plausible lifespan
    if birth < 0 and death > 0 and 0 < (death - abs(birth)) < MAX_LIFESPAN:
        return abs(birth), death

    # Both negative but death < birth numerically (both signs wrong)
    if birth < 0 and death < 0 and death < birth:
        if 0 < (abs(death) - abs(birth)) < MAX_LIFESPAN:
            return abs(birth), abs(death)
        return None, None

    # Implausible: birth>0, death<0, NOT plausible → null death
    if birth > 0 and death < 0:
        return birth, None

    # Legitimate BC-to-AD boundary: birth<0, death>0, plausible BC lifespan
    if birth < 0 and death > 0:
        if 0 < (abs(birth) + death) < MAX_LIFESPAN:
            return birth, death  # legitimate (e.g., Ovid: -43, 17)
        return None, death  # implausible span

    # birth > death, both positive → wrong person
    if birth > 0 and death > 0 and birth > death:
        return None, None

    # Lifespan > 200 years → wrong person
    if birth > 0 and death > 0 and (death - birth) > 200:
        return None, None

    return birth, death


class MetadataEnricher:
    def __init__(
        self,
        dates_path: str,
        authors_path: str,
        legacy_dates_path: Optional[str] = None,
        llm: Optional[LLM] = None,
        auto_update: bool = True,
        wiki_catalog: Optional["SQLiteWikiPeopleIndex"] = None,
    ):
        self.dates_path = Path(dates_path)
        self.authors_path = Path(authors_path)
        self.auto_update = auto_update
        self.llm = llm or build_llm()

        # Local wiki people index (fast, offline)
        self.wiki_catalog = wiki_catalog

        # Load legacy cache first (Read-Only layer)
        self.dates_cache = {}
        if legacy_dates_path:
             self.dates_cache = self._load_json(Path(legacy_dates_path))

        # Load local cache (overrides legacy if collision)
        local_dates = self._load_json(self.dates_path)
        self.dates_cache.update(local_dates)

        self.authors_cache = self._load_json(self.authors_path)

        # In-memory updates
        self.dates_updates: Dict[str, Any] = {}
        self.authors_updates: Dict[str, Any] = {}

        # Wiki Lookup (web scraper - slow, online)
        self.wiki = WikipediaLookup()

        logger.info(f"[enricher] Initialized. Cache sizes: dates={len(self.dates_cache)}, authors={len(self.authors_cache)}, local_wiki={'yes' if wiki_catalog else 'no'}")

    def _load_json(self, path: Path) -> Dict[str, Any]:
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text())
        except Exception:
            return {}

    def save(self):
        """Flush updates to disk."""
        if self.dates_updates and self.auto_update:
            self.dates_cache.update(self.dates_updates)
            self.dates_path.parent.mkdir(parents=True, exist_ok=True)
            self.dates_path.write_text(json.dumps(self.dates_cache, indent=2, sort_keys=True))
            logger.info(f"[enricher] Saved {len(self.dates_updates)} date updates to {self.dates_path}")
            self.dates_updates = {}

        if self.authors_updates and self.auto_update:
            self.authors_cache.update(self.authors_updates)
            self.authors_path.parent.mkdir(parents=True, exist_ok=True)
            self.authors_path.write_text(json.dumps(self.authors_cache, indent=2, sort_keys=True))
            logger.info(f"[enricher] Saved {len(self.authors_updates)} author updates to {self.authors_path}")
            self.authors_updates = {}

    async def enrich_book(self, book_id: str, title: str, author: str) -> int | None:
        """
        Get original publication year.
        1. Cache
        2. Goodreads Scraper (if ID)
        3. Wikipedia Lookup (web)
        4. LLM Fallback (if Wiki structured data fails)
        """
        if not book_id and not title:
            return None

        # 1. Cache
        if book_id and book_id in self.dates_cache:
            logger.debug(f"[enricher] Book year cache hit: {book_id} -> {self.dates_cache[book_id]}")
            return self.dates_cache[book_id]
        if book_id and book_id in self.dates_updates:
            return self.dates_updates[book_id]

        year = None

        # 2. Scrape Goodreads (if we have an ID and it's not synthetic)
        if book_id and book_id != "manual_run" and not str(book_id).startswith("web_"):
            logger.debug(f"[enricher] Scraping Goodreads for book ID: {book_id}")
            try:
                date_obj = await asyncio.to_thread(get_original_publication_date, book_id)
                if date_obj:
                    if isinstance(date_obj, str):
                        if "BC" in date_obj:
                            year = -int(re.sub(r'\D', '', date_obj))
                        else:
                            year = int(re.sub(r'\D', '', date_obj))
                    else:
                        year = date_obj.year

                    if year:
                        logger.info(f"[enricher] Goodreads scraper found year for '{title}': {year}")
            except Exception as e:
                logger.warning(f"[enricher] Goodreads scraper error for {book_id}: {e}")

        # 3. Wikipedia Lookup (web)
        if not year and title:
             logger.debug(f"[enricher] Trying Wikipedia web lookup for book: {title}")
             try:
                 await self.wiki.initialize()
                 info = await self.wiki.get_book_info(title)
                 date_str = info.get("published", "") or info.get("first_published", "")
                 if date_str:
                     # Parse year from "25 January 1949" or "1949 (UK)"
                     match = re.search(r'\d{4}', date_str)
                     if match:
                         year = int(match.group(0))
                         logger.info(f"[enricher] Wikipedia web found year for '{title}': {year}")
             except Exception as e:
                 logger.warning(f"[enricher] Wikipedia web lookup failed for '{title}': {e}")

        # 4. LLM Lookup (Absolute Fallback)
        if not year:
             logger.debug(f"[enricher] Fallback to LLM for book year: {title}")
             year = await self._lookup_book_year(title, author)
             if year:
                 logger.info(f"[enricher] LLM found year for '{title}': {year}")

        # Cache result
        if year and book_id:
            self.dates_updates[book_id] = year
            self.dates_cache[book_id] = year

        return year

    async def enrich_author(self, author_name: str) -> Dict[str, Any]:
        """
        Get author metadata (birth, death, etc.).
        1. Cache
        2. Local Wiki DB (fast)
        3. Wikipedia Web Lookup (slow)
        4. LLM Fallback
        """
        if not author_name:
            return {}

        # 1. Cache
        if author_name in self.authors_cache:
            logger.debug(f"[enricher] Author cache hit: {author_name}")
            return self.authors_cache[author_name]

        if author_name in self.authors_updates:
            return self.authors_updates[author_name]

        logger.debug(f"[enricher] Looking up author: {author_name}")
        meta = {}

        # 2. Local Wiki DB (fast, offline) - NEW!
        if self.wiki_catalog and not meta:
            try:
                local_results = self.wiki_catalog.find_people(name=author_name, limit=1)
                if local_results:
                    result = local_results[0]
                    if result.get("birth_year"):
                        meta["birth_year"] = result["birth_year"]
                    if result.get("death_year"):
                        meta["death_year"] = result["death_year"]
                    if result.get("title"):
                        meta["canonical_name"] = result["title"]

                    if meta:
                        logger.info(f"[enricher] Local wiki DB found: {author_name} -> birth={meta.get('birth_year')}, death={meta.get('death_year')}")
            except Exception as e:
                logger.warning(f"[enricher] Local wiki DB error for '{author_name}': {e}")

        # 3. Wikipedia Web Lookup (slow, online)
        if not meta:
            logger.debug(f"[enricher] Local DB miss, trying Wikipedia web for: {author_name}")
            try:
                await self.wiki.initialize()
                dates = await self.wiki.get_person_dates(author_name)

                # Skip if we got an error or raw HTML dump
                if 'error' in dates or ('raw' in dates and len(str(dates.get('raw', ''))) > 500):
                    logger.debug(f"[enricher] Wikipedia web returned no useful data for '{author_name}'")
                else:
                    if 'born' in dates:
                        # Extract year from formats like "April 15, 1452" or "c. 428 BC"
                        y = re.search(r'\d{3,4}', dates['born'])
                        if y:
                            birth_year = int(y.group(0))
                            if 'BC' in dates['born'] or 'BCE' in dates['born']:
                                birth_year = -birth_year
                            meta['birth_year'] = birth_year
                    if 'died' in dates:
                        y = re.search(r'\d{3,4}', dates['died'])
                        if y:
                            death_year = int(y.group(0))
                            if 'BC' in dates['died'] or 'BCE' in dates['died']:
                                death_year = -death_year
                            meta['death_year'] = death_year

                    if meta:
                        logger.info(f"[enricher] Wikipedia web found: {author_name} -> {meta}")
            except Exception as e:
                # Truncate error message to avoid HTML dumps in logs
                error_msg = str(e)[:200] if len(str(e)) > 200 else str(e)
                logger.warning(f"[enricher] Wikipedia web lookup failed for '{author_name}': {error_msg}")

        # 4. LLM Fallback (if Wiki returned nothing useful)
        if not meta:
            logger.debug(f"[enricher] Web lookup failed, falling back to LLM for: {author_name}")
            meta = await self._lookup_author_bio(author_name)
            if meta:
                logger.info(f"[enricher] LLM found bio for '{author_name}': birth={meta.get('birth_year')}, death={meta.get('death_year')}")

        # Validate dates before caching (catches errors from all 4 sources)
        if meta.get("birth_year") is not None or meta.get("death_year") is not None:
            b, d = validate_dates(meta.get("birth_year"), meta.get("death_year"))
            if b != meta.get("birth_year") or d != meta.get("death_year"):
                logger.warning(f"[enricher] Date validation corrected {author_name}: "
                              f"({meta.get('birth_year')},{meta.get('death_year')}) → ({b},{d})")
                meta["birth_year"] = b
                meta["death_year"] = d

        # Cache result
        if meta:
            self.authors_updates[author_name] = meta
            self.authors_cache[author_name] = meta
        else:
            logger.warning(f"[enricher] Failed to find bio for: {author_name}")
            # Cache negative result to avoid repeated lookups
            self.authors_updates[author_name] = {}
            self.authors_cache[author_name] = {}

        return meta or {}

    async def _lookup_book_year(self, title: str, author: str) -> int | None:
        """LLM fallback for book publication year."""
        prompt = (
            f"What is the ORIGINAL publication year of the book '{title}' by {author}?\n"
            "Return ONLY the year as an integer (e.g. 1953). For ancient/BC works, use negative numbers (e.g. -350 for 350 BC).\n"
            "If you are unsure, return 'null'."
        )
        try:
            resp = await self.llm.acomplete(prompt)
            text = resp.text.strip()
            match = re.search(r'-?\d{3,4}', text)
            if match:
                return int(match.group(0))
        except Exception as e:
            logger.error(f"[enricher] LLM book year lookup error for '{title}': {e}")
        return None

    async def _lookup_author_bio(self, name: str) -> Dict[str, Any] | None:
        """LLM fallback for author biographical data."""
        prompt = (
            f"Provide biographical data for author '{name}'.\n"
            "Return JSON with keys: 'birth_year' (int), 'death_year' (int or null), 'main_genre' (str), 'nationality' (str).\n"
            "Use negative numbers for BC years (e.g. -384 for 384 BC).\n"
            "Return ONLY valid JSON, no explanation."
        )
        try:
            resp = await self.llm.acomplete(prompt)
            text = resp.text.strip()
            # Clean markdown code blocks
            if text.startswith("```"):
                text = text.split("\n", 1)[1]
                if text.endswith("```"):
                    text = text.rsplit("\n", 1)[0]
            data = json.loads(text)
            # Validate dates from LLM
            if data.get("birth_year") is not None or data.get("death_year") is not None:
                b, d = validate_dates(data.get("birth_year"), data.get("death_year"))
                if b != data.get("birth_year") or d != data.get("death_year"):
                    logger.warning(f"[enricher] LLM bio date validation corrected {name}: "
                                  f"({data.get('birth_year')},{data.get('death_year')}) → ({b},{d})")
                    data["birth_year"] = b
                    data["death_year"] = d
            return data
        except Exception as e:
            logger.error(f"[enricher] LLM author bio lookup error for '{name}': {e}")
        return None

    async def resolve_citation_fallback(self, citation: Dict[str, Any], source_context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Fallback resolution using LLM knowledge when local DBs fail.
        """
        title = citation.get("title", "")
        author = citation.get("author", "")
        context = citation.get("contexts", [])

        source_title = source_context.get("title", "Unknown Source")
        source_year = source_context.get("publication_year") or 2025

        logger.info(f"[enricher] Fallback resolution for: title='{title}', author='{author}'")

        prompt = (
            f"You are an expert bibliographer. A citation was found in the book '{source_title}' (Published: {source_year}).\n"
            f"The citation text is: Title='{title}', Author='{author}'.\n"
            f"Context snippet: {context[:500] if context else 'N/A'}\n\n"
            f"Task: Identify the real-world book or person referenced.\n"
            f"CRITICAL CONSTRAINT: The identified work MUST have existed before {source_year}. Do not hallucinate future books.\n"
            f"If it is a Book, provide: title, author, original_year.\n"
            f"If it is a Person (no specific book cited), provide their birth/death years.\n"
            f"If you cannot identify it with high confidence, return match_type='not_found'.\n\n"
            f"Return JSON ONLY with this schema:\n"
            f"{{\n"
            f"  \"match_type\": \"book\" | \"person\" | \"not_found\",\n"
            f"  \"metadata\": {{\n"
            f"      \"title\": \"Title or Name\",\n"
            f"      \"authors\": [\"Author Name\"],\n"
            f"      \"original_year\": int,\n"
            f"      \"birth_year\": int,\n"
            f"      \"death_year\": int,\n"
            f"      \"nationality\": \"string\",\n"
            f"      \"description\": \"Brief description\"\n"
            f"  }}\n"
            f"}}"
        )

        try:
            resp = await self.llm.acomplete(prompt)
            text = resp.text.strip()

            # Clean markdown
            if text.startswith("```"):
                text = text.split("\n", 1)[1]
                if text.endswith("```"):
                    text = text.rsplit("\n", 1)[0]

            data = json.loads(text)

            match_type = data.get("match_type", "not_found")
            metadata = data.get("metadata", {})

            # Basic validation
            if match_type == "book":
                 # Ensure authors is a list
                 if isinstance(metadata.get("authors"), str):
                     metadata["authors"] = [metadata["authors"]]

            # Validate dates from LLM fallback
            if metadata.get("birth_year") is not None or metadata.get("death_year") is not None:
                b, d = validate_dates(metadata.get("birth_year"), metadata.get("death_year"))
                if b != metadata.get("birth_year") or d != metadata.get("death_year"):
                    logger.warning(f"[enricher] Fallback date validation corrected: "
                                  f"({metadata.get('birth_year')},{metadata.get('death_year')}) → ({b},{d})")
                    metadata["birth_year"] = b
                    metadata["death_year"] = d

            logger.info(f"[enricher] Fallback result: match_type={match_type}, title={metadata.get('title')}, birth={metadata.get('birth_year')}")
            return data

        except json.JSONDecodeError as e:
            logger.error(f"[enricher] Fallback JSON parse error: {e}")
            logger.debug(f"[enricher] Raw response: {resp.text[:500] if resp else 'N/A'}")
            return {"match_type": "not_found", "metadata": {}}
        except Exception as e:
            logger.error(f"[enricher] Fallback resolution error: {e}")
            return {"match_type": "not_found", "metadata": {}}
