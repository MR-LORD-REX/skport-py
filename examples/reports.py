"""Read public activity, Monument, and Crisis Contract reports."""

import asyncio
import json
import os

from skport import SkportClient


async def main() -> None:
    skport_id = os.environ["SKPORT_ID"]
    async with SkportClient(tokens=json.loads(os.environ["SKPORT_TOKENS"])) as client:
        activity, monument, contract = await asyncio.gather(
            client.endfield.activity(skport_id=skport_id),
            client.endfield.monument(skport_id=skport_id),
            client.endfield.contract(skport_id=skport_id),
        )

    for report in (activity, monument, contract):
        print(report.model_dump_json(indent=2))


if __name__ == "__main__":
    asyncio.run(main())
