import asyncio
import unittest
from typing import Any
from unittest.mock import MagicMock, AsyncMock
from llama_index.core.llms import MockLLM
from llama_index.core.tools import FunctionTool
from lib.web_search_agent.agent import WebSearchAgent

class MyMockLLM(MockLLM):
    async def achat(self, messages, **kwargs: Any) -> Any:
        response_mock = MagicMock()
        response_mock.response = '{"birth_year": 1469, "death_year": 1527, "name": "Niccolo Machiavelli"}'
        response_mock.__str__ = lambda x: x.response
        return response_mock
        
    def chat(self, messages, **kwargs: Any) -> Any:
        response_mock = MagicMock()
        response_mock.response = '{"birth_year": 1469, "death_year": 1527, "name": "Niccolo Machiavelli"}'
        response_mock.__str__ = lambda x: x.response
        return response_mock

class TestWebSearchAgent(unittest.IsolatedAsyncioTestCase):
    async def test_agent_workflow(self):
        # Mock LLM
        mock_llm = MyMockLLM()
        
        # Mock MCP Client
        agent = WebSearchAgent(llm=mock_llm, verbose=True)
        agent.mcp_client = MagicMock()
        agent.mcp_client.list_tools = AsyncMock(return_value=[{"name": "search", "description": "Search web"}])
        agent.mcp_client.to_llama_index_tools = MagicMock(return_value=[
            FunctionTool.from_defaults(fn=lambda x: "Found info", name="search", description="Search web")
        ])
        
        # Test Data
        book_data = {
            "source": {"title": "The Prince"},
            "citations": [
                {
                    "raw": {"title": "The Prince"},
                    "edge": {
                        "target_person": {
                            "title": "Machiavelli", 
                            "birth_year": None 
                        }
                    }
                }
            ]
        }
        
        # Run
        result = await agent.run(book_data=book_data)
        
        # Verify
        target = result["citations"][0]["edge"]["target_person"]
        self.assertEqual(target["birth_year"], 1469)
        self.assertEqual(target["death_year"], 1527)
        self.assertEqual(target["title"], "Niccolo Machiavelli")
        print("Test passed: Metadata updated correctly.")

if __name__ == "__main__":
    unittest.main()
