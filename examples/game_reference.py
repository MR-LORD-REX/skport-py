"""Read the game bulletin and localized enum labels."""

import asyncio
import json
import os

from skport import SkportClient


async def main() -> None:
    async with SkportClient(tokens=json.loads(os.environ["SKPORT_TOKENS"])) as client:
        catalog, news = await asyncio.gather(client.endfield.enums(), client.endfield.news())

    print(", ".join(entry.name for entry in catalog.groups.get("professions", [])))
    for notice in news:
        print(f"\n{notice.title}")
        if notice.text:
            print(notice.text.splitlines()[0])


if __name__ == "__main__":
    asyncio.run(main())
