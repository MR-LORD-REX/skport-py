"""Save an owner history, then incrementally refresh it on the next run."""

import asyncio
import os
from pathlib import Path

from skport import SkportClient
from skport.games.endfield.models import PullHistory


async def main() -> None:
    token = os.environ["SKPORT_OWNER_TOKEN"]
    path = Path(os.environ.get("SKPORT_PULL_HISTORY", "local/pull-history.json"))
    previous = PullHistory.load(path) if path.is_file() else None

    async with SkportClient(tokens=[token]) as client:
        history = await client.endfield.pulls(token=token, since=previous)

    path.parent.mkdir(parents=True, exist_ok=True)
    history.save(path)
    history.to_csv(path.with_suffix(".csv"))
    print(f"{len(history.records)} saved records")
    for banner in history.pity:
        hard = "unknown" if banner.current is None else str(banner.current)
        print(f"{banner.name or banner.banner_id}: hard pity {hard}/{banner.hard_limit or '?'}.")
        if banner.featured_guarantee is not None:
            print(f"  {banner.total} paid draws observed toward a {banner.featured_guarantee}-draw threshold.")
    for issue in history.issues:
        print(issue.message)


if __name__ == "__main__":
    asyncio.run(main())
