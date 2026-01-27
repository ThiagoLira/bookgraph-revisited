
import asyncio
from lib.wikipedia_agent import WikipediaLookup

async def main():
    wiki = WikipediaLookup()
    await wiki.initialize()
    
    print("Lookup: Shakespeare")
    dates = await wiki.get_person_dates("Shakespeare")
    print(f"Dates: {dates}")

    print("\nLookup: Bismarck")
    dates = await wiki.get_person_dates("Bismarck")
    print(f"Dates: {dates}")

if __name__ == "__main__":
    asyncio.run(main())
