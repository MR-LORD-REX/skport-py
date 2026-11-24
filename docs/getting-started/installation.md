# Installation

Install `skport-py` in a Python 3.11 or newer environment. The package uses
`aiohttp` for asynchronous requests and Pydantic 2 for normalized output models.

## Install from PyPI

```bash
python -m pip install skport-py
```

Check the installed version:

```bash
python -c "import skport; print(skport.__version__)"
```

## Install from a checkout

From the repository directory, install the package in editable mode:

```bash
python -m pip install -e .
```

For development tools such as pytest, Ruff, mypy, and the package builder:

```bash
python -m pip install -e ".[dev]"
```

## Prepare authentication

Follow [Account tokens](account-tokens.md) to sign in to the official SKPORT
website and retrieve the logged-in account's token from its internal endpoint.
Use a separate viewer account for public requests if you prefer to keep your
main game account's token outside the public pool. Account-specific methods
require the game account's token.

Public requests also require a target **SKPORT ID**. This social ID differs from
an Endfield game UID and from a character ID.

Download the official SKPORT community app and sign in with the same account you
use for Endfield. Follow the illustrated [SKPORT ID and privacy guide](../guides/skport-id-and-privacy.md)
to copy your profile ID and configure public card access. The profile copy button
copies your ID; the account token comes from the authenticated website endpoint.

The client accepts account tokens directly. It does not provide an interactive
sign-in screen. Pass at least one token through `SkportClient(tokens=[...])` or
create a reusable `SkportAPI` for the client to borrow.

Store the values as environment variables for the quickstart. The placeholders
below must be replaced with your values.

### PowerShell

```powershell
$env:SKPORT_TOKEN = "your-account-token"
$env:SKPORT_ID = "target-skport-id"
```

### Bash or zsh

```bash
export SKPORT_TOKEN="your-account-token"
export SKPORT_ID="target-skport-id"
```

Keep account tokens in environment variables or your application's secret
storage. They are not game UIDs, character IDs, or API keys issued by this SDK.

## Async applications

Every network method is asynchronous and must be awaited. A command-line script
can start its event loop with `asyncio.run(main())`. Within a running event loop,
such as a bot, web application, or notebook, await your coroutine directly.

Continue with the [quickstart](quickstart.md).
