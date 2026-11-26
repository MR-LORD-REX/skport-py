"""Summarize the operator, weapon, equipment, and tactical inventory."""

import asyncio
import os

from skport import SkportClient


async def main() -> None:
    token = os.environ["SKPORT_OWNER_TOKEN"]
    async with SkportClient(tokens=[token]) as client:
        inventory = await client.endfield.inventory(token=token, raw=False)

    print("Owned operators:", sum(operator.owned is True for operator in inventory.operators.values()))
    print("Owned weapons:", sum(weapon.owned is True for weapon in inventory.weapons.values()))
    print("Equipment quantity:", sum(item.count or 0 for item in inventory.equipment.values()))
    print("Tactical item quantity:", sum(item.count or 0 for item in inventory.tactical_items.values()))


if __name__ == "__main__":
    asyncio.run(main())
