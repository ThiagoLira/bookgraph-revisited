import asyncio
import json
import unittest
from pathlib import Path
from types import SimpleNamespace

from extract_citations import (
    DEFAULT_SYSTEM_PROMPT,
    SentenceChunk,
    build_chunks,
    call_model,
    estimate_prompt_tokens,
    format_user_prompt,
    load_sentences,
)


class DummyEncoding:
    def __init__(self, length: int) -> None:
        self.ids = list(range(length))


class DummyTokenizer:
    """Lightweight tokenizer that assigns a fixed cost per newline-delimited sentence."""

    def encode(self, text: str) -> DummyEncoding:
        base_cost = 4
        marker = "===== BEGIN BOOK EXCERPT ====="
        if marker in text:
            excerpt = text.split(marker, 1)[1]
        else:
            excerpt = text
        lines = [line for line in excerpt.splitlines() if line.strip()]
        sentence_markers = max(1, len(lines))
        total_tokens = base_cost + sentence_markers * 3
        return DummyEncoding(total_tokens)


class BuildChunksTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        repo_root = Path(__file__).resolve().parent.parent
        cls.book_path = repo_root / "books" / "Justice_ What's the Right Thing - Michael J. Sandel.txt"
        cls.sentences = load_sentences(cls.book_path)
        cls.tokenizer = DummyTokenizer()
        cls.system_prompt = DEFAULT_SYSTEM_PROMPT
        cls.book_title = cls.book_path.stem

    def test_chunks_cover_sample_without_exceeding_token_limit(self) -> None:
        sample_sentences = self.sentences[:30]
        available_input_tokens = 12
        max_completion_tokens = 8
        max_context_per_request = available_input_tokens + max_completion_tokens
        chunks = list(
            build_chunks(
                sample_sentences,
                chunk_size=0,
                tokenizer=self.tokenizer,
                system_prompt=self.system_prompt,
                max_context_per_request=max_context_per_request,
                max_completion_tokens=max_completion_tokens,
                book_title=self.book_title,
            )
        )
        self.assertGreater(len(chunks), 1)

        processed = 0
        for chunk in chunks:
            prompt = format_user_prompt(chunk, self.book_title)
            token_count = estimate_prompt_tokens(
                self.tokenizer, self.system_prompt, prompt
            )
            self.assertLessEqual(token_count, available_input_tokens)
            self.assertEqual(chunk.start_sentence, processed + 1)
            processed = chunk.end_sentence

        self.assertEqual(processed, len(sample_sentences))

    def test_chunks_trim_sentences_when_needed(self) -> None:
        sample_sentences = self.sentences[:5]
        available_input_tokens = 8
        max_completion_tokens = 4
        max_context_per_request = available_input_tokens + max_completion_tokens
        chunks = list(
            build_chunks(
                sample_sentences,
                chunk_size=10,
                tokenizer=self.tokenizer,
                system_prompt=self.system_prompt,
                max_context_per_request=max_context_per_request,
                max_completion_tokens=max_completion_tokens,
                book_title=self.book_title,
            )
        )
        self.assertGreater(len(chunks), 1)
        for chunk in chunks:
            self.assertLessEqual(len(chunk.sentences), 1)


class DummyMessage:
    def __init__(self, content: str) -> None:
        self.content = content
        self.reasoning_content = None


class DummyChoice:
    def __init__(self, content: str, finish_reason: str = "stop") -> None:
        self.message = DummyMessage(content)
        self.finish_reason = finish_reason


class DummyChatResponse:
    def __init__(self, content: str) -> None:
        self.choices = [DummyChoice(content)]
        self.usage = None


class DummyCompletions:
    def __init__(self, response: DummyChatResponse) -> None:
        self._response = response

    async def create(self, **kwargs):
        return self._response


class DummyClient:
    def __init__(self, response: DummyChatResponse) -> None:
        self.chat = SimpleNamespace(completions=DummyCompletions(response))


class CallModelTests(unittest.IsolatedAsyncioTestCase):
    async def test_call_model_returns_successful_chunk(self) -> None:
        tokenizer = DummyTokenizer()
        book_title = "Sample Book"
        chunk = SentenceChunk(
            index=0,
            start_sentence=1,
            end_sentence=2,
            sentences=("Sentence one.", "Sentence two."),
        )
        completion_content = json.dumps(
            {
                "citations": [
                    {"title": "Justice", "author": "Michael Sandel", "note": None}
                ],
            }
        )
        response = DummyChatResponse(completion_content)
        client = DummyClient(response)
        semaphore = asyncio.Semaphore(1)

        effective_chunk, success, failure = await call_model(
            client=client,
            tokenizer=tokenizer,
            chunk=chunk,
            system_prompt=DEFAULT_SYSTEM_PROMPT,
            book_title=book_title,
            semaphore=semaphore,
            model="dummy",
            max_completion_tokens=32,
            max_context_per_request=40,
        )

        self.assertIsNone(failure)
        self.assertEqual(effective_chunk.start_sentence, 1)
        self.assertIsNotNone(success)
        self.assertEqual(success.chunk_index, 0)
        self.assertEqual(success.citations[0].author, "Michael Sandel")


if __name__ == "__main__":
    unittest.main()
