# Account tokens

A Gryphline account token authenticates the SDK's SKPORT requests. Choose the
account according to the work you want to perform: public player lookups can
use a separate viewer account, while owner methods require the game account's
token.

## Choose an account

- **Public requests:** sign in to SKPORT with any account accepted by the service.
  A separate account can authenticate public requests so your main game account's
  token stays out of the public token pool. The viewer does not need an Endfield
  binding; the requested player's SKPORT ID selects the target.
- **Owner requests:** sign in with the same account you use for Endfield. Its
  token identifies the owner for roster, individual character, inventory,
  attendance, and pull-record methods.

You can use the game account for public requests too. Use separate viewer and
owner tokens when you want to keep their roles separate.

## Get the logged-in account's token

1. Open the [official SKPORT website](https://www.skport.com/) in your browser.
2. Sign in with the account you chose above.
3. In the **same browser profile and login session**, open the official internal
   [account-token endpoint](https://web-api.skport.com/cookie_store/account_token):

   ```text
   https://web-api.skport.com/cookie_store/account_token
   ```

4. Copy the **account token** returned for that logged-in account. Copy the token
   value itself rather than the surrounding response, and save it in your
   application's environment or secret storage.

To obtain the other account's token, sign in with that account before opening
the endpoint again. Separate browser profiles can help keep the two login
sessions distinct. If the endpoint does not return a token, complete sign-in on
the official website and reopen it in the same browser session.

The account token is different from the numeric **SKPORT ID** copied in the app
and from the Endfield game UID. See [SKPORT ID and privacy](../guides/skport-id-and-privacy.md)
for the illustrated ID and visibility steps.

## Configure a public viewer

Save the viewer account's token as `SKPORT_TOKEN`, and the target player's ID as
`SKPORT_ID`:

```powershell
$env:SKPORT_TOKEN = "your-viewer-account-token"
$env:SKPORT_ID = "target-skport-id"
```

```bash
export SKPORT_TOKEN="your-viewer-account-token"
export SKPORT_ID="target-skport-id"
```

The [quickstart](quickstart.md) uses these values. Public requests respect the
target player's global card visibility and individual section settings. A viewer
token does not grant access to another account's private owner data.

## Keep owner access separate

Save the game account's token as `SKPORT_OWNER_TOKEN` when you need owner methods.
Pass it explicitly to those methods, while using the viewer token to construct
the client:

```python
import asyncio
import os

from skport import SkportClient


async def main() -> None:
    public_token = os.environ["SKPORT_TOKEN"]
    owner_token = os.environ["SKPORT_OWNER_TOKEN"]

    async with SkportClient(tokens=[public_token]) as client:
        owner = await client.endfield.verify_token(owner_token)
        roster = await client.endfield.owned_characters(token=owner_token)
        print(owner.in_game_name, len(roster))


if __name__ == "__main__":
    asyncio.run(main())
```

The SDK retains an explicitly supplied owner token for owner requests without
adding it to public rotation. You can keep your card private and use token-bound
owner methods for your own account; public sharing settings control what viewers
can read.

Continue with [owner accounts](../guides/owner-accounts.md) for account-specific
methods, or [public profiles](../guides/public-profiles.md) for public lookups.
