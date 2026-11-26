"""Claim today's daily reward for the selected owner account."""

import asyncio
import os

from skport import AlreadyCheckedIn, SkportClient


async def main() -> None:
    token = os.environ["SKPORT_OWNER_TOKEN"]
    async with SkportClient(tokens=[token]) as client:
        try:
            result = await client.endfield.check_in(token=token, raw=False)
        except AlreadyCheckedIn:
            print("Today's reward was already claimed.")
            return

    for award, reward in zip(result.awards, result.rewards, strict=True):
        print(f"{reward.count} × {reward.name}" if reward else award.id)


if __name__ == "__main__":
    asyncio.run(main())
