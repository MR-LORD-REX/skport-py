"""Inspect a public profile using environment-supplied account tokens."""

import asyncio
import json
import os

from skport import SkportAPI, SkportClient


async def main() -> None:
    """Reuse one API across public profile and character requests."""
    tokens = json.loads(os.environ["SKPORT_TOKENS"])
    skport_id = os.environ["SKPORT_ID"]
    game_uid = os.environ.get("ENDFIELD_UID")
    async with SkportAPI(tokens=tokens) as api:
        await api.warm()
        async with SkportClient(api=api) as client:
            characters = await client.endfield.characters(skport_id=skport_id, role_id=game_uid)
            print(json.dumps([{"id": char["id"], "name": char["charData"]["name"]} for char in characters]))


if __name__ == "__main__":
    asyncio.run(main())
