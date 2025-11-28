from llama_index.core.workflow import Context, Workflow, StartEvent, StopEvent, step
import asyncio

class MyWorkflow(Workflow):
    @step
    async def start(self, ctx: Context, ev: StartEvent) -> StopEvent:
        print(f"Store type: {type(ctx.store)}")
        print(f"Store dir: {dir(ctx.store)}")
        return StopEvent(result="Done")

asyncio.run(MyWorkflow().run())
