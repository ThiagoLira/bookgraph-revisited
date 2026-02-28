"""
Unified LLM client configuration and construction.

Provides a single LLMConfig dataclass and factory functions for both
AsyncOpenAI (extraction, validation) and LlamaIndex LLM (workflow, enrichment).
All LLM calls go through OpenRouter.
"""

from dataclasses import dataclass

from openai import AsyncOpenAI
from llama_index.core.llms import LLM


@dataclass
class LLMConfig:
    """Configuration for a single LLM endpoint (OpenRouter)."""
    base_url: str = "https://openrouter.ai/api/v1"
    api_key: str = ""
    model: str = "deepseek/deepseek-v3.2"
    timeout: float = 150.0


def build_async_openai(config: LLMConfig) -> AsyncOpenAI:
    """Build an AsyncOpenAI client for direct API calls (extraction, validation)."""
    return AsyncOpenAI(api_key=config.api_key, base_url=config.base_url)


def build_llama_llm(config: LLMConfig) -> LLM:
    """Build a LlamaIndex LLM wrapper for structured prediction (workflow, enrichment)."""
    try:
        from llama_index.llms.openai_like import OpenAILike

        return OpenAILike(
            model=config.model,
            api_key=config.api_key,
            api_base=config.base_url,
            is_chat_model=True,
            is_function_calling_model=True,
            timeout=config.timeout,
        )
    except ModuleNotFoundError:
        from llama_index.llms.openai import OpenAI

        return OpenAI(
            model=config.model,
            api_key=config.api_key,
            base_url=config.base_url,
            timeout=config.timeout,
        )
