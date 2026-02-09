#!/usr/bin/env python3
"""Library for extracting book and author citations from local LLM responses."""

from __future__ import annotations

import asyncio
import copy
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, List, Optional, Sequence

import nltk
from nltk.tokenize import sent_tokenize
from openai import AsyncOpenAI
from openai.types.chat import ChatCompletion
from pydantic import BaseModel, Field, ValidationError
from tokenizers import Tokenizer

DEFAULT_SYSTEM_PROMPT = (
    "You are an expert research librarian. Extract only citations that refer to "
    "books or book authors mentioned as sources of ideas. "
    "Ignore references to papers, articles, movies, podcasts, websites, or other works of art. "
    "CRITICAL: IGNORE lists of books, Bibliographies, Acknowledgements, Prefaces, or 'Other books by...' sections. "
    "Focus ONLY on citations that appear within the narrative prose. "
    "Authors MUST be named individuals (real people like 'Aristotle', 'Virginia Woolf'). "
    "Do NOT extract groups, schools of thought, or generic terms ('the Stoics', 'Greek philosophers', 'poets', 'thinkers'). "
    "Do NOT extract unnamed or generic references ('a philosopher once said', 'ancient authors'). "
    "If a name is a mythological character or fictional entity rather than a real historical author, exclude it."
)

USER_PROMPT_TEMPLATE = """You are extracting book citations from a bounded excerpt of "{{book_title}}".

Return ONLY JSON with this shape:
{
  "citations": [
    {
      "title": str | null, // If only an author is mentioned (Person Reference), set title to null.
      "author": str,       // Cite the ORIGINAL author (e.g., 'Plato', not the translator).
      "citation_excerpt": str,
      "commentary": str    // Third-person commentary on how the book is referenced.
    }
  ]
}

Rules:
- Use only information inside the excerpt; do not invent books or authors.
- **Original Authors Only**: If a translator is mentioned, extract the original author (e.g. for "Homer's Iliad translated by Pope", author is "Homer").
- **Person References**: If an author is mentioned as a source of ideas but no specific book is named (e.g. "As Socrates argued..."), extract them with `title: null`.
- **Real People Only**: Authors MUST be real named individuals. Do NOT extract groups, schools, or generic terms like "the Stoics", "Greek philosophers", "poets", "thinkers", "Epicureans". Do NOT extract mythological or fictional characters (e.g. "Dionysus", "Hamlet") as authors.
- **Ignore Meta-Content**: Do NOT extract from Bibliographies, Footnotes, Indices, or "Further Reading" lists.
- **Deduplicate**: Include each cited book/author at most once per chunk.
- `citation_excerpt` MUST be the exact text snippet from the excerpt where the citation appears.
- `commentary`: Write a brief third-person note explaining what the author says about the book (e.g., "The author mentions reading this book in his youth," "The author cites this as a prime example of modernism").

===== BEGIN BOOK EXCERPT =====
{{sentences_block}}
===== END BOOK EXCERPT =====
"""

CHAR_PER_TOKEN_SAFETY = 6


class BookCitation(BaseModel):
    title: Optional[str] = Field(None, description="Title of the referenced book.")
    author: str = Field(
        ..., description="Book Author mentioned"
    )
    citation_excerpt: str = Field(
        ...,
        description="The exact text snippet where the citation appears.",
    )
    commentary: str = Field(
        ...,
        description="A brief third-person commentary explaining the context or sentiment of the citation.",
    )


class ChunkExtraction(BaseModel):
    chunk_index: int
    start_sentence: int
    end_sentence: int
    citations: List[BookCitation]


class ChunkFailure(BaseModel):
    chunk_index: int
    start_sentence: int
    end_sentence: int
    error: str
    raw_response: Optional[str] = None


class ExtractionResult(BaseModel):
    source_path: str
    model: str
    chunk_size: int
    total_sentences: int
    chunks: List[ChunkExtraction]
    failures: List[ChunkFailure] = Field(default_factory=list)


class ModelChunkCitations(BaseModel):
    citations: List[BookCitation] = Field(
        default_factory=list,
        description="Citations drawn strictly from the provided excerpt.",
    )


CHUNK_EXTRACTION_JSON_SCHEMA = ModelChunkCitations.model_json_schema(
    ref_template="#/$defs/{model}",
)


def chunk_extraction_response_format() -> dict[str, object]:
    """Return a response_format dict that shares the Pydantic schema with llama.cpp."""
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "chunk_extraction",
            "strict": True,
            "schema": copy.deepcopy(CHUNK_EXTRACTION_JSON_SCHEMA),
        },
    }


@dataclass(frozen=True)
class SentenceChunk:
    index: int
    start_sentence: int
    end_sentence: int
    sentences: Sequence[str]


@dataclass(frozen=True)
class ExtractionConfig:
    input_path: Path
    chunk_size: int = 15
    max_concurrency: int = 10
    base_url: str = "http://localhost:8080/v1"
    api_key: str = "test"
    model: str = "deepseek/deepseek-v3.2"
    max_completion_tokens: int = 4096
    max_context_per_request: int = 8192  # Total context window per request (input + output)
    tokenizer_name: str = "deepseek-ai/DeepSeek-V3"
    book_title: Optional[str] = None
    verbose: bool = False


def drop_last_sentence(chunk: SentenceChunk) -> Optional[SentenceChunk]:
    sentences = list(chunk.sentences)
    if len(sentences) <= 1:
        return None
    trimmed = tuple(sentences[:-1])
    new_end = chunk.start_sentence + len(trimmed) - 1
    return SentenceChunk(
        index=chunk.index,
        start_sentence=chunk.start_sentence,
        end_sentence=new_end,
        sentences=trimmed,
    )


def ensure_punkt() -> None:
    try:
        nltk.data.find("tokenizers/punkt")
    except LookupError:
        nltk.download("punkt", quiet=True)


def load_sentences(path: Path) -> List[str]:
    ensure_punkt()
    text = path.read_text(encoding="utf-8")
    sentences = sent_tokenize(text)
    return [s.strip() for s in sentences if s.strip()]


def build_chunks(
    sentences: Sequence[str],
    chunk_size: int,
    tokenizer: Tokenizer,
    system_prompt: str,
    max_context_per_request: int,
    max_completion_tokens: int,
    book_title: str,
    *,
    char_per_token: int = CHAR_PER_TOKEN_SAFETY,
) -> Iterable[SentenceChunk]:
    if max_context_per_request <= 0:
        raise ValueError("max_context_per_request must be positive.")
    if max_completion_tokens <= 0:
        raise ValueError("max_completion_tokens must be positive.")
    if char_per_token <= 0:
        raise ValueError("char_per_token must be positive.")

    # Reserve space for output tokens in the context window
    available_input_tokens = max_context_per_request - max_completion_tokens
    if available_input_tokens <= 0:
        raise ValueError("max_context_per_request must be greater than max_completion_tokens.")
    char_budget = available_input_tokens * char_per_token
    total_sentences = len(sentences)
    chunk_index = 0
    cursor = 0

    while cursor < total_sentences:
        current_sentences: list[str] = []
        chars_used = 0
        while cursor + len(current_sentences) < total_sentences:
            if chunk_size > 0 and len(current_sentences) >= chunk_size:
                break
            source_index = cursor + len(current_sentences)
            sentence_text = sentences[source_index]
            addition = len(sentence_text) + 1  # include newline separator
            if current_sentences and chars_used + addition > char_budget:
                break
            if not current_sentences and addition > char_budget:
                current_sentences.append(sentence_text)
                chars_used += addition
                break
            current_sentences.append(sentence_text)
            chars_used += addition
            if chars_used >= char_budget:
                break

        if not current_sentences:
            # Should not happen, but guard against empty chunks.
            current_sentences.append(sentences[cursor])

        chunk = SentenceChunk(
            index=chunk_index,
            start_sentence=cursor + 1,
            end_sentence=cursor + len(current_sentences),
            sentences=tuple(current_sentences),
        )

        effective_chunk = chunk
        while True:
            user_prompt = format_user_prompt(effective_chunk, book_title)
            token_count = estimate_prompt_tokens(tokenizer, system_prompt, user_prompt)
            if token_count <= available_input_tokens:
                break
            next_chunk = drop_last_sentence(effective_chunk)
            if next_chunk is None:
                # Skip this sentence instead of erroring out
                print(f"Warning: Skipping sentence at position {cursor + 1} (exceeds token limit)", flush=True)
                cursor += 1
                effective_chunk = None
                break
            effective_chunk = next_chunk

        if effective_chunk is not None:
            yield effective_chunk
            cursor += len(effective_chunk.sentences)
            chunk_index += 1


def _normalize_sentence(sentence: str) -> str:
    return " ".join(sentence.split())


def chunk_text(chunk: SentenceChunk) -> str:
    return "\n".join(_normalize_sentence(sentence) for sentence in chunk.sentences)


def format_user_prompt(chunk: SentenceChunk, book_title: str) -> str:
    return (
        USER_PROMPT_TEMPLATE.replace("{{book_title}}", book_title).replace(
            "{{sentences_block}}", chunk_text(chunk)
        )
    )


def estimate_prompt_tokens(tokenizer: Tokenizer, system_prompt: str, user_prompt: str) -> int:
    prompt = f"<|system|>\n{system_prompt}\n<|user|>\n{user_prompt}"
    return len(tokenizer.encode(prompt).ids)


async def call_model(
    client: AsyncOpenAI,
    tokenizer: Tokenizer,
    chunk: SentenceChunk,
    system_prompt: str,
    book_title: str,
    *,
    semaphore: asyncio.Semaphore,
    model: str,
    max_completion_tokens: int,
    max_context_per_request: int,
    verbose: bool = False,
) -> tuple[SentenceChunk, ChunkExtraction | None, ChunkFailure | None]:
    # build_chunks already ensures chunks fit within token limits
    user_prompt = format_user_prompt(chunk, book_title)

    if verbose:
        print(f"\n[DEBUG] Prompt (Chunk {chunk.index}):\n{user_prompt}\n---", flush=True)

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    max_retries = 2
    last_failure: Optional[ChunkFailure] = None

    for attempt in range(max_retries + 1):
        try:
            async with semaphore:
                response: ChatCompletion = await client.chat.completions.create(
                    model=model,
                    messages=messages,
                    max_tokens=max_completion_tokens,
                    temperature=0.0,
                    response_format=chunk_extraction_response_format(),
                    extra_body={
                        "chat_template_kwargs": {"enable_thinking": True},
                        # "reasoning_format": "none",
                    },
                    timeout=150.0,
                )
        except Exception as e:
            print(f"[DEBUG] Chunk {chunk.index}: API Failed (Attempt {attempt+1}/{max_retries+1}): {e}", flush=True)
            last_failure = ChunkFailure(
                chunk_index=chunk.index,
                start_sentence=chunk.start_sentence,
                end_sentence=chunk.end_sentence,
                error=f"API Error: {str(e)}",
            )
            continue

        content = ""
        finish_reason = None
        if response.choices:
            choice = response.choices[0]
            finish_reason = choice.finish_reason
            message = choice.message
            content = (message.content or "").strip()
            
            if verbose:
                print(f"\n[DEBUG] Response (Chunk {chunk.index}):\n{content}\n---", flush=True)

            if not content:
                reasoning_content = getattr(message, "reasoning_content", None)
                if reasoning_content:
                    content = reasoning_content.strip()

        if not content:
            print(f"[DEBUG] Chunk {chunk.index}: Empty content (Attempt {attempt+1}/{max_retries+1}).", flush=True)
            last_failure = ChunkFailure(
                chunk_index=chunk.index,
                start_sentence=chunk.start_sentence,
                end_sentence=chunk.end_sentence,
                error="Empty response from model.",
            )
            continue

        if finish_reason == "length":
            print(f"[DEBUG] Chunk {chunk.index}: Finish reason length (Attempt {attempt+1}/{max_retries+1}).", flush=True)
            last_failure = ChunkFailure(
                chunk_index=chunk.index,
                start_sentence=chunk.start_sentence,
                end_sentence=chunk.end_sentence,
                error="Model stopped early due to max token limit; increase --max-completion-tokens.",
                raw_response=content,
            )
            continue

        try:
            parsed = ModelChunkCitations.model_validate_json(content)
            extraction = ChunkExtraction(
                chunk_index=chunk.index,
                start_sentence=chunk.start_sentence,
                end_sentence=chunk.end_sentence,
                citations=parsed.citations,
            )
            return chunk, extraction, None

        except ValidationError as exc:
            print(f"[DEBUG] Chunk {chunk.index}: Validation Error (Attempt {attempt+1}/{max_retries+1}): {exc}", flush=True)
            last_failure = ChunkFailure(
                chunk_index=chunk.index,
                start_sentence=chunk.start_sentence,
                end_sentence=chunk.end_sentence,
                error=f"Pydantic validation failed: {exc}",
                raw_response=content,
            )
        except json.JSONDecodeError as exc:
            print(f"[DEBUG] Chunk {chunk.index}: JSON Error (Attempt {attempt+1}/{max_retries+1}): {exc}", flush=True)
            last_failure = ChunkFailure(
                chunk_index=chunk.index,
                start_sentence=chunk.start_sentence,
                end_sentence=chunk.end_sentence,
                error=f"Invalid JSON output: {exc}",
                raw_response=content,
            )

    # If we exhaust all retries, return the last failure
    return chunk, None, last_failure


ProgressCallback = Callable[[int, int], None]


async def process_book(
    config: ExtractionConfig,
    *,
    debug_limit: Optional[int] = None,
    progress_callback: Optional[ProgressCallback] = None,
) -> ExtractionResult:
    input_path = config.input_path
    if not input_path.exists():
        raise FileNotFoundError(f"Book file not found: {input_path}")

    book_title = config.book_title or input_path.stem

    try:
        tokenizer = Tokenizer.from_pretrained(config.tokenizer_name)
    except Exception as exc:
        print(f"Warning: Failed to load tokenizer '{config.tokenizer_name}': {exc}. Falling back to 'deepseek-ai/DeepSeek-V3'.")
        try:
            tokenizer = Tokenizer.from_pretrained("deepseek-ai/DeepSeek-V3")
        except Exception as fallback_exc:
            raise RuntimeError(
                f"Failed to load fallback tokenizer 'deepseek-ai/DeepSeek-V3': {fallback_exc}"
            ) from fallback_exc

    sentences = load_sentences(input_path)
    chunks = list(
        build_chunks(
            sentences,
            config.chunk_size,
            tokenizer,
            DEFAULT_SYSTEM_PROMPT,
            config.max_context_per_request,
            config.max_completion_tokens,
            book_title,
        )
    )
    if debug_limit is not None:
        if debug_limit < 1:
            raise ValueError("--debug-limit must be positive.")
        chunks = chunks[: debug_limit]

    semaphore = asyncio.Semaphore(config.max_concurrency)

    async with AsyncOpenAI(api_key=config.api_key, base_url=config.base_url) as client:
        tasks = [
            asyncio.create_task(
                call_model(
                    client,
                    tokenizer,
                    chunk,
                    DEFAULT_SYSTEM_PROMPT,
                    book_title,
                    semaphore=semaphore,
                    model=config.model,
                    max_completion_tokens=config.max_completion_tokens,
                    max_context_per_request=config.max_context_per_request,
                    verbose=config.verbose,
                )
            )
            for chunk in chunks
        ]

        chunk_results: List[ChunkExtraction] = []
        failures: List[ChunkFailure] = []

        completed = 0
        total_chunks = len(chunks)

        for coro in asyncio.as_completed(tasks):
            _, success, failure = await coro
            if success:
                chunk_results.append(success)
            if failure:
                failures.append(failure)
            completed += 1
            if progress_callback:
                progress_callback(completed, total_chunks)

    chunk_results.sort(key=lambda c: c.chunk_index)
    failures.sort(key=lambda f: f.chunk_index)

    return ExtractionResult(
        source_path=str(input_path),
        model=config.model,
        chunk_size=config.chunk_size,
        total_sentences=len(sentences),
        chunks=chunk_results,
        failures=failures,
    )


def write_output(result: ExtractionResult, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(result.model_dump_json(indent=2), encoding="utf-8")
