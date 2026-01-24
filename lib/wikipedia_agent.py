
"""
Wikipedia Fact Lookup Agent for LlamaIndex

A specialized agent for extracting simple facts from Wikipedia:
- Publication dates of books
- Birth/death dates of people
- Release dates of albums/movies
- Founding dates of companies
- Basic biographical information

This is optimized for quick factual lookups rather than general browsing.

Requirements:
    pip install llama-index llama-index-llms-openai pyppeteer beautifulsoup4 lxml

Usage:
    from wikipedia_agent import WikipediaAgent, create_wikipedia_agent
    
    agent, tools = await create_wikipedia_agent(llm)
    response = await agent.achat("When was 1984 by George Orwell first published?")
"""

import asyncio
import re
from typing import Optional, List, Any, Dict
from bs4 import BeautifulSoup

from pyppeteer import launch
from pyppeteer.browser import Browser
from pyppeteer.page import Page

from llama_index.core.tools import FunctionTool
from llama_index.core.tools.tool_spec.base import BaseToolSpec


class WikipediaToolSpec(BaseToolSpec):
    """
    Specialized LlamaIndex ToolSpec for Wikipedia fact lookups.
    
    Optimized for answering simple factual questions like:
    - "When was [book] published?"
    - "When was [person] born/died?"
    - "When was [company] founded?"
    """
    
    spec_functions = [
        "search_wikipedia",
        "get_wikipedia_page",
        "get_infobox_data",
        "get_page_summary",
    ]
    
    def __init__(self, headless: bool = True, language: str = "en"):
        """
        Initialize Wikipedia tools.
        
        Args:
            headless: Run browser in headless mode
            language: Wikipedia language code (default: "en")
        """
        self.headless = headless
        self.language = language
        self.base_url = f"https://{language}.wikipedia.org"
        self.browser: Optional[Browser] = None
        self.page: Optional[Page] = None
        self._initialized = False
    
    async def initialize(self) -> None:
        """Initialize the browser."""
        if self._initialized:
            return
        
        self.browser = await launch(
            headless=self.headless,
            args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage']
        )
        self.page = await self.browser.newPage()
        await self.page.setUserAgent(
            'Mozilla/5.0 (compatible; WikipediaFactBot/1.0; +https://example.com/bot)'
        )
        self._initialized = True
    
    async def close(self) -> None:
        """Close the browser."""
        if self.browser:
            await self.browser.close()
            self.browser = None
            self.page = None
            self._initialized = False
    
    async def _ensure_initialized(self) -> None:
        if not self._initialized:
            await self.initialize()
    
    async def search_wikipedia(self, query: str) -> str:
        """
        Search Wikipedia for a topic and return matching article titles.
        
        Args:
            query: The search term (e.g., "1984 novel", "George Orwell", "Apple Inc")
        
        Returns:
            List of matching Wikipedia article titles with their URLs
        """
        await self._ensure_initialized()
        
        try:
            search_url = f"{self.base_url}/w/index.php?search={query.replace(' ', '+')}&title=Special:Search"
            await self.page.goto(search_url, {'waitUntil': 'networkidle2', 'timeout': 20000})
            
            # Check if we landed directly on an article (exact match)
            current_url = self.page.url
            if '/wiki/' in current_url and 'Special:Search' not in current_url:
                title = await self.page.title()
                title = title.replace(' - Wikipedia', '')
                return f"Direct match found: '{title}'\nURL: {current_url}\n\nUse get_wikipedia_page with this URL to get details."
            
            # Extract search results
            html = await self.page.content()
            soup = BeautifulSoup(html, 'lxml')
            
            results = []
            for item in soup.select('.mw-search-result-heading')[:8]:
                link = item.find('a')
                if link:
                    title = link.get_text(strip=True)
                    href = link.get('href', '')
                    full_url = f"{self.base_url}{href}" if href.startswith('/') else href
                    results.append({'title': title, 'url': full_url})
            
            if not results:
                return f"No Wikipedia articles found for: {query}"
            
            output = f"Wikipedia search results for '{query}':\n\n"
            for i, r in enumerate(results, 1):
                output += f"{i}. {r['title']}\n   {r['url']}\n"
            output += "\nUse get_wikipedia_page with a URL to get article details."
            
            return output
        except Exception as e:
            return f"Search failed: {str(e)}"
    
    async def get_wikipedia_page(self, url_or_title: str) -> str:
        """
        Navigate to a Wikipedia article and get its content.
        
        Args:
            url_or_title: Either a full Wikipedia URL or an article title
                         (e.g., "https://en.wikipedia.org/wiki/1984_(novel)" or "1984 (novel)")
        
        Returns:
            The article's infobox data (if present) and opening paragraphs
        """
        await self._ensure_initialized()
        
        try:
            # Handle both URLs and titles
            if url_or_title.startswith('http'):
                url = url_or_title
            else:
                # Convert title to URL format
                title_formatted = url_or_title.replace(' ', '_')
                url = f"{self.base_url}/wiki/{title_formatted}"
            
            await self.page.goto(url, {'waitUntil': 'networkidle2', 'timeout': 20000})
            
            html = await self.page.content()
            soup = BeautifulSoup(html, 'lxml')
            
            # Get article title
            title_el = soup.select_one('#firstHeading')
            title = title_el.get_text(strip=True) if title_el else "Unknown"
            
            output = f"Wikipedia Article: {title}\nURL: {self.page.url}\n\n"
            
            # Extract infobox data (the sidebar with key facts)
            infobox = soup.select_one('.infobox, .infobox_v2, .vcard')
            if infobox:
                output += "=== Key Facts (Infobox) ===\n"
                for row in infobox.select('tr'):
                    header = row.select_one('th')
                    data = row.select_one('td')
                    if header and data:
                        key = header.get_text(strip=True)
                        value = data.get_text(separator=' ', strip=True)
                        # Clean up common formatting issues
                        value = re.sub(r'\[[\d\w]+\]', '', value)  # Remove citation markers
                        value = re.sub(r'\s+', ' ', value).strip()
                        if key and value and len(value) < 500:
                            output += f"  {key}: {value}\n"
                output += "\n"
            
            # Get first few paragraphs
            content_div = soup.select_one('#mw-content-text .mw-parser-output')
            if content_div:
                paragraphs = []
                for p in content_div.find_all('p', recursive=False)[:4]:
                    text = p.get_text(strip=True)
                    # Clean up
                    text = re.sub(r'\[[\d\w]+\]', '', text)
                    text = re.sub(r'\s+', ' ', text).strip()
                    if text and len(text) > 50:
                        paragraphs.append(text)
                
                if paragraphs:
                    output += "=== Summary ===\n"
                    output += '\n\n'.join(paragraphs[:3])
            
            return output
        except Exception as e:
            return f"Failed to get page: {str(e)}"
    
    async def get_infobox_data(self, url_or_title: str) -> str:
        """
        Get just the infobox/sidebar data from a Wikipedia article.
        This contains structured facts like dates, places, etc.
        
        Args:
            url_or_title: Wikipedia URL or article title
        
        Returns:
            Structured key-value pairs from the article's infobox
        """
        await self._ensure_initialized()
        
        try:
            if url_or_title.startswith('http'):
                url = url_or_title
            else:
                title_formatted = url_or_title.replace(' ', '_')
                url = f"{self.base_url}/wiki/{title_formatted}"
            
            await self.page.goto(url, {'waitUntil': 'networkidle2', 'timeout': 20000})
            
            html = await self.page.content()
            soup = BeautifulSoup(html, 'lxml')
            
            # Get article title
            title_el = soup.select_one('#firstHeading')
            title = title_el.get_text(strip=True) if title_el else "Unknown"
            
            # Find infobox
            infobox = soup.select_one('.infobox, .infobox_v2, .vcard, .infobox-book, .infobox-person')
            
            if not infobox:
                return f"No infobox found for '{title}'. Try get_wikipedia_page for full content."
            
            output = f"Infobox data for: {title}\n\n"
            
            data = {}
            for row in infobox.select('tr'):
                header = row.select_one('th')
                cell = row.select_one('td')
                if header and cell:
                    key = header.get_text(strip=True)
                    value = cell.get_text(separator=' ', strip=True)
                    value = re.sub(r'\[[\d\w]+\]', '', value)
                    value = re.sub(r'\s+', ' ', value).strip()
                    if key and value:
                        data[key] = value
                        output += f"{key}: {value}\n"
            
            if not data:
                return f"Infobox found but no data extracted for '{title}'"
            
            return output
        except Exception as e:
            return f"Failed to get infobox: {str(e)}"
    
    async def get_page_summary(self, url_or_title: str) -> str:
        """
        Get a brief summary (first 2-3 paragraphs) from a Wikipedia article.
        
        Args:
            url_or_title: Wikipedia URL or article title
        
        Returns:
            The opening paragraphs of the article
        """
        await self._ensure_initialized()
        
        try:
            if url_or_title.startswith('http'):
                url = url_or_title
            else:
                title_formatted = url_or_title.replace(' ', '_')
                url = f"{self.base_url}/wiki/{title_formatted}"
            
            await self.page.goto(url, {'waitUntil': 'networkidle2', 'timeout': 20000})
            
            html = await self.page.content()
            soup = BeautifulSoup(html, 'lxml')
            
            title_el = soup.select_one('#firstHeading')
            title = title_el.get_text(strip=True) if title_el else "Unknown"
            
            content_div = soup.select_one('#mw-content-text .mw-parser-output')
            if not content_div:
                return f"Could not extract content from '{title}'"
            
            paragraphs = []
            for p in content_div.find_all('p', recursive=False)[:5]:
                text = p.get_text(strip=True)
                text = re.sub(r'\[[\d\w]+\]', '', text)
                text = re.sub(r'\s+', ' ', text).strip()
                if text and len(text) > 30:
                    paragraphs.append(text)
            
            if not paragraphs:
                return f"No content found for '{title}'"
            
            output = f"Summary of '{title}':\n\n"
            output += '\n\n'.join(paragraphs[:3])
            
            return output
        except Exception as e:
            return f"Failed to get summary: {str(e)}"
    
    def to_tool_list(self) -> List[FunctionTool]:
        """Convert to list of FunctionTools for LlamaIndex agents."""
        tools = []
        for func_name in self.spec_functions:
            func = getattr(self, func_name)
            tool = FunctionTool.from_defaults(
                async_fn=func,
                name=func_name,
                description=func.__doc__ or f"Execute {func_name}"
            )
            tools.append(tool)
        return tools


async def create_wikipedia_agent(
    llm: Any,
    headless: bool = True,
    verbose: bool = True,
    language: str = "en"
) -> tuple:
    """
    Create a LlamaIndex agent specialized for Wikipedia fact lookups.
    
    Args:
        llm: The LLM to use
        headless: Run browser in headless mode
        verbose: Print agent reasoning
        language: Wikipedia language code
    
    Returns:
        Tuple of (agent, tool_spec)
    """
    from llama_index.core.agent import ReActAgent
    
    tool_spec = WikipediaToolSpec(headless=headless, language=language)
    await tool_spec.initialize()
    
    # Custom system prompt for Wikipedia lookups
    system_prompt = """You are a research assistant specialized in finding facts on Wikipedia.

When asked a factual question:
1. First search Wikipedia for the relevant article
2. Then get the infobox data (contains dates, places, key facts) or page content
3. Extract and report the specific fact requested

For dates (birth, death, publication, founding, etc.), always check the infobox first as it has structured data.

Be concise - just provide the requested fact with its source."""

    agent = ReActAgent.from_tools(
        tools=tool_spec.to_tool_list(),
        llm=llm,
        verbose=verbose,
        max_iterations=6,
        system_prompt=system_prompt
    )
    
    return agent, tool_spec


# Simpler alternative: Direct lookup functions without an agent
class WikipediaLookup:
    """
    Simple Wikipedia lookup without using an LLM agent.
    Good for programmatic fact extraction.
    
    Example:
        wiki = WikipediaLookup()
        await wiki.initialize()
        
        info = await wiki.get_book_info("1984 (novel)")
        print(info)
        
        await wiki.close()
    """
    
    def __init__(self, language: str = "en"):
        self.tools = WikipediaToolSpec(headless=True, language=language)
    
    async def initialize(self):
        await self.tools.initialize()
    
    async def close(self):
        await self.tools.close()
    
    async def get_person_dates(self, name: str) -> dict:
        """Get birth and death dates for a person."""
        result = await self.tools.search_wikipedia(f"{name}")
        
        # If direct match, extract from infobox
        if "Direct match" in result:
            url = result.split("URL: ")[1].split("\n")[0]
            infobox = await self.tools.get_infobox_data(url)
        else:
            # Try first result
            lines = result.split('\n')
            url = None
            for line in lines:
                if line.strip().startswith('http'):
                    url = line.strip()
                    break
            if url:
                infobox = await self.tools.get_infobox_data(url)
            else:
                return {"error": "No Wikipedia article found", "raw": result}
        
        # Parse dates from infobox
        dates = {}
        # Parse output of get_infobox_data which is key: value
        for line in infobox.split('\n'):
            line_lower = line.lower()
            if 'born' in line_lower:
                dates['born'] = line.split(':', 1)[1].strip() if ':' in line else line
            elif 'died' in line_lower:
                dates['died'] = line.split(':', 1)[1].strip() if ':' in line else line
            elif 'birth_date' in line_lower:
                 dates['born'] = line.split(':', 1)[1].strip() if ':' in line else line
            elif 'death_date' in line_lower:
                 dates['died'] = line.split(':', 1)[1].strip() if ':' in line else line
        
        return dates if dates else {"raw": infobox}
    
    async def get_book_info(self, title: str) -> dict:
        """Get publication info for a book."""
        result = await self.tools.search_wikipedia(f"{title} novel book")
        
        if "Direct match" in result:
            url = result.split("URL: ")[1].split("\n")[0]
        else:
            lines = result.split('\n')
            url = None
            for line in lines:
                if line.strip().startswith('http'):
                    url = line.strip()
                    break
        
        if not url:
            return {"error": "No Wikipedia article found"}
        
        infobox = await self.tools.get_infobox_data(url)
        
        info = {}
        for line in infobox.split('\n'):
            line_lower = line.lower()
            if any(k in line_lower for k in ['published', 'publication date', 'release date', 'first published']):
                info['published'] = line.split(':', 1)[1].strip() if ':' in line else line
            elif 'author' in line_lower:
                info['author'] = line.split(':', 1)[1].strip() if ':' in line else line
            elif 'publisher' in line_lower:
                info['publisher'] = line.split(':', 1)[1].strip() if ':' in line else line
        
        return info if info else {"raw": infobox}
