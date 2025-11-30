from typing import Optional
from llama_index.core.llms import LLM
from llama_index.llms.openai import OpenAI

def build_llm(model: str, api_key: str, base_url: Optional[str]) -> LLM:
    """
    Create an OpenAI-compatible LLM wrapper for LlamaIndex.

    Prefers `OpenAILike` so we can target OpenRouter or any self-hosted endpoint.
    Falls back to the builtin OpenAI wrapper if base_url is omitted.
    """
    if not base_url:
        return OpenAI(model=model, api_key=api_key, timeout=120.0)

    try:
        from llama_index.llms.openai_like import OpenAILike

        return OpenAILike(
            model=model,
            api_key=api_key,
            api_base=base_url,
            is_chat_model=True,
            is_function_calling_model=True,
            timeout=120.0,
        )
    except ModuleNotFoundError:
        return OpenAI(model=model, api_key=api_key, base_url=base_url, timeout=120.0)
