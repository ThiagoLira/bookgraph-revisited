#!/usr/bin/env python3
import asyncio
import argparse
import json
import sys
import os
from pathlib import Path
from dotenv import load_dotenv

from llama_index.llms.openai_like import OpenAILike
from llama_index.llms.openai import OpenAI
from lib.web_search_agent.agent import WebSearchAgent

def parse_args():
    parser = argparse.ArgumentParser(description="Run Web Search Agent on a Book JSON")
    parser.add_argument("input_file", type=Path, help="Path to input JSON file")
    parser.add_argument("output_file", type=Path, help="Path to output JSON file")
    parser.add_argument("--base-url", default="http://localhost:8080/v1", help="LLM Base URL")
    parser.add_argument("--api-key", default="test", help="LLM API Key")
    parser.add_argument("--model", default="Qwen/Qwen3-30B-A3B", help="Model Name")
    parser.add_argument("--mcp-url", default="http://127.0.0.1:8000/sse", help="MCP Server URL")
    parser.add_argument("--use-openai", action="store_true", help="Use standard OpenAI instead of OpenAILike")
    parser.add_argument("--use-openrouter", action="store_true", help="Use OpenRouter")
    parser.add_argument("--openrouter-model", default="google/gemini-2.0-flash-exp:free", help="OpenRouter model")
    parser.add_argument("--api-base", default=None, help="Custom API base URL")
    return parser.parse_args()

async def main():
    load_dotenv()
    args = parse_args()
    
    # Setup LLM
    if args.use_openrouter:
        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            print("Error: OPENROUTER_API_KEY not found in .env")
            sys.exit(1)
        
        llm = OpenAILike(
            model=args.openrouter_model,
            api_base=args.api_base or "https://openrouter.ai/api/v1",
            api_key=api_key,
            is_chat_model=True,
            is_function_calling_model=True,
            context_window=32768,
            temperature=0.6,
            additional_kwargs={
                "response_format": {"type": "json_object"},
                "top_p": 0.95
            }
        )
        print(f"Using OpenAILike with model {args.openrouter_model} at {args.api_base or 'https://openrouter.ai/api/v1'}")
    elif args.use_openai or os.getenv("OPENAI_API_KEY"):
        llm = OpenAI(model=args.model)
        print("Using OpenAI LLM")
    else:
        llm = OpenAILike(
            model=args.model,
            api_base=args.base_url,
            api_key=args.api_key,
            is_chat_model=True
        )
        print(f"Using OpenAILike LLM at {args.base_url}")

    # Init Agent
    agent = WebSearchAgent(llm=llm, mcp_url=args.mcp_url, verbose=True)
    
    # Load Input
    with open(args.input_file, "r") as f:
        book_data = json.load(f)
        
    print(f"Processing {args.input_file}...")
    result = await agent.run(book_data=book_data)
    
    # Save Output
    with open(args.output_file, "w") as f:
        json.dump(result, f, indent=2)
        
    print(f"Done. Saved to {args.output_file}")

if __name__ == "__main__":
    asyncio.run(main())
