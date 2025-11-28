from llama_index.core.workflow import Context, Workflow

async def test():
    w = Workflow()
    ctx = Context(w)
    print(f"Has set? {hasattr(ctx, 'set')}")
    print(f"Has get? {hasattr(ctx, 'get')}")
    print(f"Has data? {hasattr(ctx, 'data')}")
    try:
        await ctx.set("key", "value")
        print("set worked")
    except Exception as e:
        print(f"set failed: {e}")
    
    try:
        ctx.data["key"] = "value"
        print("data worked")
    except Exception as e:
        print(f"data failed: {e}")

import asyncio
asyncio.run(test())
