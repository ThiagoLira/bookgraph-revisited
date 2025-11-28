import asyncio
import sys
import os
from llama_index.core.workflow import Workflow, StartEvent, StopEvent, Event, step, Context
from typing import Union

# Add root to path
sys.path.append(os.getcwd())

class RetryEvent(Event):
    count: int

class TestWorkflow(Workflow):
    @step
    async def start(self, ctx: Context, ev: Union[StartEvent, RetryEvent]) -> StopEvent | RetryEvent:
        print(f"Step 'start' received event type: {type(ev).__name__}")
        
        count = 0
        if isinstance(ev, RetryEvent):
            count = ev.count
            print(f"Retry count: {count}")
        
        if count < 2:
            print("Emitting RetryEvent")
            return RetryEvent(count=count + 1)
        
        print("Done")
        return StopEvent(result="Success")

async def main():
    w = TestWorkflow(timeout=10, verbose=True)
    result = await w.run()
    print(f"Result: {result}")

if __name__ == "__main__":
    asyncio.run(main())
