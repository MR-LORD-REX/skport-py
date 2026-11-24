"""Read a card-ready build with local calculation data and SKPORT artwork."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

from skport import ClientConfig, SkportClient
from skport.games.endfield.models import CharacterBuild


async def main() -> None:
    """Use a saved asset snapshot, refreshing it only when explicitly requested."""
    tokens = json.loads(os.environ["SKPORT_TOKENS"])
    asset_path = os.environ.get("SKPORT_ASSETS_DIR")
    config = ClientConfig(assets_dir=Path(asset_path) if asset_path else None)
    async with SkportClient(tokens=tokens, config=config) as client:
        if os.environ.get("SKPORT_UPDATE_ASSETS") == "1":
            await client.update_assets()
        build = await client.endfield.character(
            skport_id=os.environ["SKPORT_ID"],
            role_id=os.environ.get("ENDFIELD_UID"),
            index=0,
        )
        assert isinstance(build, CharacterBuild)
        print(build.model_dump_json(indent=2))


if __name__ == "__main__":
    asyncio.run(main())
