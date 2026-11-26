# skport-py documentation

Build Endfield integrations with an asynchronous Python client for SKPORT. Fetch
public player profiles, inspect character loadouts, calculate static stats, and
access an account owner's data through explicit authentication.

`skport-py` requires Python 3.11 or newer. The current release supports the global
SKPORT deployment and Endfield.

## Get started

1. [Install the package](getting-started/installation.md).
2. [Get an account token](getting-started/account-tokens.md) for a public viewer or your game account.
3. [Copy your SKPORT ID and configure privacy](guides/skport-id-and-privacy.md).
4. [Run your first request](getting-started/quickstart.md) with `SkportClient`.

## What the client provides

- **Player information:** verify SKPORT identities and read public player cards.
- **Character builds:** obtain skills, talents, weapons, essence terms, equipment,
  equipment sets, artwork links, and static calculated stats.
- **Account-owner access:** fetch the supplied token owner's roster, inventory,
  attendance, and pull records.
- **Activity reports:** read resource counters, regional and spaceship progress,
  monument records, and crisis contracts.
- **Raw access:** use the service's decoded response data when your application
  needs fields outside the normalized models.

SKPORT supplies player data and the default image URLs. A locally cached snapshot
of official Enka tables supplies canonical identities and calculation inputs.
Player requests do not depend on Enka's live player API.

## Guides

- [SKPORT ID and privacy](guides/skport-id-and-privacy.md)
- [Public profiles](guides/public-profiles.md)
- [Character builds](guides/character-builds.md)
- [Stat calculation](guides/stat-calculation.md)
- [Owner accounts](guides/owner-accounts.md)
- [Assets and images](guides/assets-and-images.md)
- [Languages and configuration](guides/languages-and-configuration.md)
- [Errors and retries](guides/errors-and-retries.md)

## Reference

- [Main client](reference/client.md): construction, resource ownership, and asset updates.
- [Endfield client](reference/endfield.md): verification, player reads, and owner methods.
- [Output models](reference/output-models.md): fields, serialization, images, and stat units.

## Data and rendering

Most game methods return Pydantic models. The SDK supplies data for your
application or card renderer; image downloads, bitmap caching, themes, and layout
belong in that application. Raw wiki and pull-record endpoints are available,
while complete typed wiki and pull-history adapters are not yet exposed.

Public visibility still applies to public reads. A public profile's returned
characters are the records SKPORT exposes, which may be a subset of the owner's
roster. Use [owner methods](guides/owner-accounts.md) when you have that account's
token and need its returned account data.
