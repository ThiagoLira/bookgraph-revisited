import json
import asyncio
import re
from pathlib import Path
from typing import Dict, Any, Optional
import logging

from llama_index.core.llms import LLM
from lib.bibliography_agent.llm_utils import build_llm
from lib.goodreads_scraper import get_original_publication_date
from lib.wikipedia_agent import WikipediaLookup

logger = logging.getLogger(__name__)

class MetadataEnricher:
    def __init__(
        self,
        dates_path: str,
        authors_path: str,
        legacy_dates_path: Optional[str] = None, 
        llm: Optional[LLM] = None,
        auto_update: bool = True
    ):
        self.dates_path = Path(dates_path)
        self.authors_path = Path(authors_path)
        self.auto_update = auto_update 
        self.llm = llm or build_llm()
        
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
        
        # Wiki Lookup
        self.wiki = WikipediaLookup()

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
            self.dates_updates = {}
            
        if self.authors_updates and self.auto_update:
            self.authors_cache.update(self.authors_updates)
            self.authors_path.parent.mkdir(parents=True, exist_ok=True)
            self.authors_path.write_text(json.dumps(self.authors_cache, indent=2, sort_keys=True))
            self.authors_updates = {}

    async def enrich_book(self, book_id: str, title: str, author: str) -> int | None:
        """
        Get original publication year.
        1. Cache
        2. Goodreads Scraper (if ID)
        3. Wikipedia Lookup
        4. LLM Fallback (if Wiki structured data fails)
        """
        if not book_id and not title:
            return None
            
        # 1. Cache
        if book_id and book_id in self.dates_cache:
            return self.dates_cache[book_id]
        if book_id and book_id in self.dates_updates:
            return self.dates_updates[book_id]

        year = None
        
        # 2. Scrape Goodreads (if we have an ID)
        if book_id and book_id != "manual_run":
            logger.debug(f"Scraping Goodreads for ID: {book_id}")
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
                        logger.info(f"Scraper found year: {year}")
            except Exception as e:
                logger.warning(f"Scraper error: {e}")

        # 3. Wikipedia Lookup
        if not year and title:
             logger.info(f"Goodreads failed. Trying Wikipedia for: {title}")
             try:
                 await self.wiki.initialize()
                 info = await self.wiki.get_book_info(title)
                 date_str = info.get("published", "") or info.get("first_published", "")
                 if date_str:
                     # Parse year from "25 January 1949" or "1949 (UK)"
                     match = re.search(r'\d{4}', date_str)
                     if match:
                         year = int(match.group(0))
                         logger.info(f"Wikipedia found year: {year}")
             except Exception as e:
                 logger.warning(f"Wiki lookup failed: {e}")

        # 4. LLM Lookup (Absolute Fallback)
        if not year:
             logger.info(f"Fallback to LLM for: {title}")
             year = await self._lookup_book_year(title, author)

        # Cache result
        if year and book_id:
            self.dates_updates[book_id] = year
            self.dates_cache[book_id] = year
            
        return year

    async def enrich_author(self, author_name: str) -> Dict[str, Any]:
        """
        Get author metadata (birth, death, etc.).
        1. Cache
        2. Wikipedia Lookup
        3. LLM Fallback
        """
        if not author_name:
            return {}
            
        if author_name in self.authors_cache:
            return self.authors_cache[author_name]
            
        if author_name in self.authors_updates:
            return self.authors_updates[author_name]
            
        logger.debug(f"Looking up bio for: {author_name}")
        meta = {}
        
        # 2. Wikipedia Lookup
        try:
            await self.wiki.initialize()
            dates = await self.wiki.get_person_dates(author_name)
            if 'born' in dates:
                # Extract year
                y = re.search(r'\d{4}', dates['born'])
                if y: meta['birth_year'] = int(y.group(0))
            if 'died' in dates:
                y = re.search(r'\d{4}', dates['died'])
                if y: meta['death_year'] = int(y.group(0))
                
            if meta:
                logger.info(f"Wikipedia bio found: {meta}")
        except Exception as e:
            logger.warning(f"Wiki bio lookup failed: {e}")

        # 3. LLM Fallback (if Wiki returned nothing useful)
        if not meta:
            logger.info(f"Wikipedia failed. Fallback to LLM for {author_name}")
            meta = await self._lookup_author_bio(author_name)
            
        if meta:
            self.authors_updates[author_name] = meta
            self.authors_cache[author_name] = meta
        else:
            logger.warning(f"Failed to find bio for {author_name}")
            
        return meta or {}

    async def _lookup_book_year(self, title: str, author: str) -> int | None:
        # Simple LLM prompt for now. Ideally tool-use Search.
        # But user asked for "quick lookup". 
        prompt = (
            f"What is the ORIGINAL publication year of the book '{title}' by {author}?\n"
            "Return ONLY the year as an integer (e.g. 1953). If unknown or ancient/BC, return closest estimate or negative integer.\n"
            "If you are unsure, return 'null'."
        )
        try:
            resp = await self.llm.acomplete(prompt)
            # print(f"[enricher] Book Year Response: {resp.text}")
            text = resp.text.strip()
            # extract number
            import re
            match = re.search(r'-?\d{3,4}', text)
            if match:
                return int(match.group(0))
        except Exception as e:
            logger.error(f"Error enriching book {title}: {e}")
        return None

    async def _lookup_author_bio(self, name: str) -> Dict[str, Any] | None:
        prompt = (
            f"Provide biographical data for author '{name}'.\n"
            "Return JSON with keys: 'birth_year' (int), 'death_year' (int or null), 'main_genre' (str), 'nationality' (str).\n"
            "Use negative numbers for BC years.\n"
            "Return ONLY JSON."
        )
        try:
            # print(f"[enricher] Calling LLM for {name}...")
            resp = await self.llm.acomplete(prompt)
            text = resp.text.strip()
            # print(f"[enricher] Author Bio Response for {name}: {text}")
            # cleaning markdown code blocks
            if text.startswith("```"):
                text = text.split("\n", 1)[1]
                if text.endswith("```"):
                    text = text.rsplit("\n", 1)[0]
            data = json.loads(text)
            return data
        except Exception as e:
            logger.error(f"Error enriching author {name}: {e}")
        return None
