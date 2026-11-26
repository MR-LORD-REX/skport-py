# Pull history

Pull records require the token for the Endfield account whose history you want
to read. If several roles are bound, pass a `Role` or a
`"3_<roleId>_<serverId>"` header to select one.

```python
import asyncio
import os
from pathlib import Path

from skport import SkportClient
from skport.games.endfield.models import PullHistory

async def main():
    token = os.environ["SKPORT_OWNER_TOKEN"]
    path = Path("local/pull-history.json")
    previous = PullHistory.load(path) if path.is_file() else None

    async with SkportClient(tokens=[token]) as client:
        history = await client.endfield.pulls(token=token, since=previous)

    path.parent.mkdir(parents=True, exist_ok=True)
    history.save(path)
    history.to_csv(path.with_suffix(".csv"))

asyncio.run(main())
```

## Fetch and resume

A fresh fetch walks the supported character streams and the owner's available weapon
pools. To fetch only records later than a particular instant, pass an aware
`datetime` as `after`. The cutoff is exclusive. Use `since` with an existing
`PullHistory` to merge updates into a fresh result. Each stream resumes from its
own sequence checkpoint, including when several draws share a timestamp.
Resume validates the saved SKPORT account, role, and server.

`records` are newest first. Each record carries its stream, original sequence
ID, and UTC timestamp. Its `kind` preserves the service's distinction between
draws and gifts. This includes gifts with absent item IDs or rarities.
`history.checkpoints` indicate the streams visited and whether SKPORT returned
the end of its available window. Read `history.issues` for detected gaps.
`history.complete_history` reflects whether all-time coverage can be established.

## Pity

`history.pity` contains observed paid totals per banner and reported hard-pity
state. `pool_version` distinguishes versions of a recurring banner. Use
`hard_scope` to identify rows that share a counter.

- Limited character draws share an 80-draw hard threshold across the supported
  limited streams. The first-featured threshold is 120 paid draws per banner.
- Standard character draws have an 80-draw hard threshold and a distinct
  300-draw selector threshold.
- The beginner stream has a 50-draw threshold.
- Weapon thresholds are 40 draws for hard pity and 80 for the featured
  threshold per pool.

`observed_since_six_star` counts recorded paid draws after the latest observed
paid six-star, or across the observed records if a reset is absent.
`current` is populated when the history supports an exact hard-pity count.
Free draws and gifts are excluded from hard pity. `total` is the observed
paid count for the specific banner or pool.

Provide `featured_items` keyed by
`(stream.key, banner_id, pool_version)` with the banner's verified in-game
featured item IDs to identify a recorded featured result. `featured_received`
is true when a matching paid six-star is observed. It is `None` when the
recorded history and identity information leave the result unknown. A saved
history retains the supplied IDs for incremental refresh.

## Export

Use JSON with `save()` and `load()` to keep player, records, coverage, and
checkpoints. CSV contains one row per record. Use
`PullHistory.from_csv(path, player=history.player)` to import a CSV export
and rebuild observed totals. To preserve sync checkpoints, resume from JSON.

The versioned JSON and CSV formats contain account history. Keep exports
in a directory appropriate for that account's data.

See the runnable [pull history example](https://github.com/MR-LORD-REX/skport-py/blob/main/examples/pull_history.py).
