"""Print listed banners and their regional schedules."""

import asyncio
import json
import os

from skport import SkportClient


async def main() -> None:
    async with SkportClient(tokens=json.loads(os.environ["SKPORT_TOKENS"])) as client:
        characters, weapons = await asyncio.gather(
            client.endfield.char_banners(),
            client.endfield.weapon_banners(),
        )

    for banner in characters + weapons:
        print(banner.kind, banner.name or banner.id)
        for item in banner.items:
            print(f"  {item.name or item.id} ({item.rarity or '?'} stars)")
        for window in banner.windows:
            print(f"  {window.region}: {window.starts_at} to {window.ends_at}")


if __name__ == "__main__":
    asyncio.run(main())
