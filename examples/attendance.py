"""Read the monthly and first-time rewards available to an owner."""

import asyncio
import os

from skport import SkportClient


async def main() -> None:
    token = os.environ["SKPORT_OWNER_TOKEN"]
    async with SkportClient(tokens=[token]) as client:
        status = await client.endfield.attendance(token=token, raw=False)

    for day in status.available_days:
        reward = status.rewards_by_id.get(day.award_id)
        print(f"{reward.count} × {reward.name}" if reward else day.award_id)


if __name__ == "__main__":
    asyncio.run(main())
