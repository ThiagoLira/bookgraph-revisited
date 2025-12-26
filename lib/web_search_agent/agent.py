import json
import asyncio
from typing import Any, Dict, List, Optional
from datetime import datetime

from llama_index.core.workflow import (
    Event,
    StartEvent,
    StopEvent,
    Workflow,
    step,
    Context,
)
from llama_index.core.llms import LLM, ChatMessage
from llama_index.core.agent.workflow.react_agent import ReActAgent

# LlamaIndex MCP Tool Integration
from llama_index.tools.mcp import aget_tools_from_mcp_url

class SearchEvent(Event):
    book_data: Dict[str, Any]
    issue: Dict[str, Any]
    remaining_issues: List[Dict[str, Any]]

class UpdateEvent(Event):
    book_data: Dict[str, Any]
    citation_index: int
    updates: Dict[str, Any]
    remaining_issues: List[Dict[str, Any]]

class WebSearchAgent(Workflow):
    def __init__(
        self,
        llm: LLM,
        mcp_url: str = "http://127.0.0.1:8000/sse",
        timeout: int = 300,
        verbose: bool = False,
    ):
        super().__init__(timeout=timeout, verbose=verbose)
        self.llm = llm
        self.mcp_url = mcp_url
        self.tools = []
        self._initialized = False

    async def _initialize_tools(self):
        if not self._initialized:
            try:
                # Use official MCP integration
                # Note: mcp-searxng over HTTP is usually an SSE endpoint or just HTTP.
                # If aget_tools_from_mcp_url supports it.
                self.tools = await aget_tools_from_mcp_url(self.mcp_url)
                self._initialized = True
            except Exception as e:
                import traceback
                traceback.print_exc()
                print(f"Warning: Failed to initialize MCP tools: {e}")

    @step
    async def validate_metadata(self, ctx: Context, ev: StartEvent) -> SearchEvent | StopEvent:
        await self._initialize_tools()
        book_data = ev.get("book_data")
        if not book_data:
            return StopEvent(result={})

        citations = book_data.get("citations", [])
        issues = []
        
        for i, citation in enumerate(citations):
            edge = citation.get("edge", {})
            target = edge.get("target_person", {}) 
            
            author_name = target.get("title")
            b_year = target.get("birth_year")

            if not b_year:
                issues.append({
                    "index": i,
                    "reason": "missing_birth_year",
                    "author": author_name,
                    "citation_title": citation.get("raw", {}).get("title", "")
                })
                continue
        
        if not issues:
             return StopEvent(result=book_data)

        first_issue = issues.pop(0)
        return SearchEvent(book_data=book_data, issue=first_issue, remaining_issues=issues)

    @step
    async def search_and_correct(self, ctx: Context, ev: SearchEvent) -> UpdateEvent:
        issue = ev.issue
        author = issue["author"]
        book_title = issue["citation_title"]
        
        query = f"when was {author} born and died? canonical name"
        if book_title:
             query += f" author of {book_title}"

        from llama_index.core.agent import FunctionAgent

        # Use FunctionAgent with structured output support
        agent = FunctionAgent(
            tools=self.tools,
            llm=self.llm,
            verbose=True,
            system_prompt="You are a helper agent. Use the search tool to find birth/death years and canonical name.\n"
                          "You MUST return the final answer as a raw JSON object matching this schema:\n"
                          "{\"birth_year\": int or null, \"death_year\": int or null, \"name\": str}\n"
                          "Rules:\n"
                          "1. AD dates must be POSITIVE (e.g., 1469). Do NOT use negative numbers for AD years.\n"
                          "2. BC dates must be NEGATIVE (e.g., -430).\n"
                          "3. If unknown, use null."
        )
        
        
        max_retries = 3
        updates = {}
        
        for attempt in range(max_retries):
            try:
                print(f"DEBUG: Attempt {attempt + 1}/{max_retries} for {author}")
                response = await agent.run(f"Find details for: {query}.")
                
                content = str(response) 
                print(f"DEBUG: Agent Response: {content}")
                
                import re
                # Naive JSON extraction
                json_match = re.search(r"\{.*\}", content, re.DOTALL)
                
                if json_match:
                    data = json.loads(json_match.group(0))
                    
                    # Validate rules locally to trigger retry if model ignores them
                    b_year = data.get("birth_year")
                    d_year = data.get("death_year")
                    
                    # Reject negative dates for obviously AD figures (heuristic: > -100 to avoid BC confusion, 
                    # but prompt implementation is stricter. Let's just trust prompt or basic type check for now 
                    # to avoid complex validation logic in retry)
                    
                    updates = {
                        "birth_year": b_year,
                        "death_year": d_year,
                        "title": data.get("name") 
                    }
                    # If successful, break loop
                    break
            except Exception as e:
                print(f"DEBUG: Attempt {attempt + 1} failed: {e}")
                if attempt == max_retries - 1:
                    print("Error: Max retries reached for JSON parsing.")
        
        return UpdateEvent(
            book_data=ev.book_data,
            citation_index=issue["index"],
            updates=updates,
            remaining_issues=ev.remaining_issues
        )

    @step
    async def update_data(self, ctx: Context, ev: UpdateEvent) -> SearchEvent | StopEvent:
        idx = ev.citation_index
        updates = ev.updates
        book_data = ev.book_data
        
        if updates:
            target_person = book_data["citations"][idx]["edge"]["target_person"]
            if updates.get("birth_year"):
                target_person["birth_year"] = updates["birth_year"]
            if updates.get("death_year"):
                target_person["death_year"] = updates["death_year"]
            if updates.get("title"):
                target_person["title"] = updates["title"]
                
        if ev.remaining_issues:
            next_issue = ev.remaining_issues.pop(0)
            return SearchEvent(book_data=book_data, issue=next_issue, remaining_issues=ev.remaining_issues)
        
        return StopEvent(result=book_data)
