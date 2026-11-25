from skport import SkportAPI, SkportClient , ClientConfig , ImageSource 
import asyncio

async def main():
    token_a=""
    skport_id="2348675939926"
    game_uid="4925086679"

    cfg=ClientConfig(
        icon_source=ImageSource.ENKA
    )

    async with SkportAPI(tokens=[token_a], lang="en",config=cfg) as api:
        await api.warm()
        async with SkportClient(api=api) as client:
            # await client.update_assets()
            # characters = await client.endfield.characters(skport_id=1705883884575)
            # for c in characters:
            #     print(c.name)

            char=await client.endfield.character(skport_id=1705883884575,index=1)
            with open(f"{char.name}.json","w",encoding="utf-8") as f:
                c=char.model_dump_json(indent=2)
                f.write(c)
                

asyncio.run(main())