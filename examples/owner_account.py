"""Read owner data without adding its token to public rotation."""

import asyncio
import json
import os

from skport import SkportAPI


async def main() -> None:
    """Fetch attendance for an explicitly selected owner account."""
    public_tokens = json.loads(os.environ["SKPORT_TOKENS"])
    owner_token = os.environ["SKPORT_OWNER_TOKEN"]
    async with SkportAPI(tokens=public_tokens) as api:
        attendance = await api.endfield.attendance(token=owner_token)
        print(json.dumps(attendance, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
