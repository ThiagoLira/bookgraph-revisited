import asyncio
import time
from typing import Any, Dict, List
from unittest.mock import MagicMock, AsyncMock
from llama_index.core.workflow import Workflow, StartEvent, StopEvent, step, Context

# Mock Workflow that simulates delay
class MockSlowWorkflow(Workflow):
    def __init__(self, delay: float = 0.5):
        super().__init__(timeout=10, verbose=False)
        self.delay = delay

    @step
    async def process(self, ctx: Context, ev: StartEvent) -> StopEvent:
        await asyncio.sleep(self.delay)
        return StopEvent(result={"match_type": "found", "metadata": {"book_id": "123"}})

async def run_test():
    # Simulate the parallel logic from calibre_citations_pipeline.py
    max_concurrency = 5
    total_citations = 10
    delay_per_citation = 0.2
    
    workflow = MockSlowWorkflow(delay=delay_per_citation)
    sem = asyncio.Semaphore(max_concurrency)
    
    async def process_citation_safe(citation: Dict[str, Any]):
        async with sem:
            start = time.time()
            await workflow.run(citation=citation)
            end = time.time()
            return start, end

    citations = [{"id": i} for i in range(total_citations)]
    
    print(f"Starting test with {total_citations} citations, {delay_per_citation}s delay each, max concurrency {max_concurrency}")
    start_time = time.time()
    
    tasks = [process_citation_safe(c) for c in citations]
    results = await asyncio.gather(*tasks)
    
    total_time = time.time() - start_time
    print(f"Total time: {total_time:.2f}s")
    
    # Expected time: (total / concurrency) * delay
    # 10 / 5 * 0.2 = 0.4s (plus overhead)
    # Sequential would be 10 * 0.2 = 2.0s
    
    expected_parallel_time = (total_citations / max_concurrency) * delay_per_citation
    expected_sequential_time = total_citations * delay_per_citation
    
    print(f"Expected parallel time: ~{expected_parallel_time:.2f}s")
    print(f"Expected sequential time: ~{expected_sequential_time:.2f}s")
    
    if total_time < expected_sequential_time * 0.8:
        print("SUCCESS: Execution was significantly faster than sequential.")
    else:
        print("FAILURE: Execution was not significantly faster.")

if __name__ == "__main__":
    asyncio.run(run_test())
