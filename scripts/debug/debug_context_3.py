from llama_index.core.workflow import Context, Workflow, StartEvent, StopEvent, step

class MyWorkflow(Workflow):
    @step
    async def start(self, ctx: Context, ev: StartEvent) -> StopEvent:
        print(f"Type of store: {type(ctx.store)}")
        print(f"Store content: {ctx.store}")
        ctx.store["test_key"] = "test_value"
        val = ctx.store.get("test_key")
        print(f"Retrieved: {val}")
        return StopEvent(result="Done")

import asyncio
asyncio.run(MyWorkflow().run())
