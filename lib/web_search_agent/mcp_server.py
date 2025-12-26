from mcp.server.fastmcp import FastMCP
import httpx
import json

# Initialize FastMCP server
mcp = FastMCP("searxng-search")

SEARXNG_URL = "http://localhost:8080"  # Local SearXNG instance

@mcp.tool()
async def searxng_web_search(query: str) -> str:
    """
    Search the web using SearXNG.
    Args:
        query: The search query string.
    Returns:
        JSON string containing search results.
    """
    print(f"Executing search for: {query}")
    async with httpx.AsyncClient() as client:
        try:
            # searxng expects q=...&format=json
            params = {
                "q": query,
                "format": "json"
            }
            response = await client.get(f"{SEARXNG_URL}/search", params=params, timeout=10.0)
            response.raise_for_status()
            data = response.json()
            
            # Extract relevant fields to keep context small
            results = []
            for res in data.get("results", [])[:5]:
                results.append({
                    "title": res.get("title"),
                    "url": res.get("url"),
                    "content": res.get("content", "")[:300] # Truncate content
                })
            
            return json.dumps(results)
        except Exception as e:
            return f"Error performing search: {str(e)}"

if __name__ == "__main__":
    # Run the server
    # FastMCP uses SSE by default on standard run or stdio.
    # We want SSE over HTTP for the agent to connect to.
    mcp.run(transport="sse") 
