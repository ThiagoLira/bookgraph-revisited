#!/bin/bash

# Start SearXNG and MCP-SearXNG
echo "Starting SearXNG and MCP Server..."
docker-compose up -d


echo "Starting Local Python MCP Server..."
# Kill existing instance if any
pkill -f mcp_server.py || true
# Start new instance in background
nohup uv run python lib/web_search_agent/mcp_server.py > mcp_server.log 2>&1 &
echo "MCP Server running on port 8000 (SSE)."

echo "Services started."
echo "SearXNG (Docker): http://localhost:8080"
echo "MCP Server (Local): http://127.0.0.1:8000/sse"
