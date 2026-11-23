from src.skport import SkportAPI, SkportClient
import asyncio

async def main():
    token_a="yhyLogq8J5MJUiNNFy6tUI0i"
    skport_id="2348675939926"
    game_uid="4925086679"

    async with SkportAPI(tokens=[token_a], lang="en") as api:
        await api.warm()
        async with SkportClient(api=api) as client:
            card = await client.endfield.card(
                skport_id=skport_id, lang="en"
            )
            for i in range(0,8):
                character = await client.endfield.character(
                    skport_id=skport_id, index=i, lang="en"
                )
                print(character["charData"]["name"])

asyncio.run(main())