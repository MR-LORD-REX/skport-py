"""Read an operator wiki article and print its profile and skills."""

import argparse
import asyncio
import json
import os

from skport import SkportClient


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--item-id", help="Wiki ID. Defaults to the first operator in the catalog.")
    parser.add_argument("--lang", default="en")
    args = parser.parse_args()

    async with SkportClient(tokens=json.loads(os.environ["SKPORT_TOKENS"])) as client:
        operators = await client.endfield.wiki_catalog(type_sub_id=1, lang=args.lang)
        if not args.item_id and not operators:
            print("The operator catalog is empty.")
            return
        item_id = args.item_id or operators[0].id
        page = await client.endfield.wiki_item(item_id, lang=args.lang)

    print(page.summary.name)
    if page.quote:
        print(page.quote)
    for field in page.info_fields:
        print(f"{field.label}: {field.value}")
    for skill in page.skill_entries:
        print(f"\n{skill.name}\n{skill.description or skill.text}")


if __name__ == "__main__":
    asyncio.run(main())
