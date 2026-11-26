# Captured build calculation

`skport-sample-tables.json` contains selected rows from the seven canonical
tables used to calculate `../skport/character_snapshot.json`. The checked-in
rows retain their original values. The original table files were verified
against the commit's Git blob hashes. [Pinned Enka tables](https://github.com/EnkaNetwork/API-docs/tree/2a63e0971795bd0d4f8753e61d266b1ab565a417/store/ef)

The offline test compares these expectations calculated from the retained inputs.

- HP is `5495 + 109 * 5 = 6040`.
- ATK is `(321 + 505) * (1 + 671 * 0.005 + 230 * 0.002) = 3977.19`, floored to `3977`.
- DEF is `56 + 42 + 21 + 21 = 140`.
- STR is `floor(82.6701030927835 + 27) = 109`.
- AGI is `floor(128.1521986114036 + 75 + 27) = 230`.
- INT is `floor(176.68156953503097 + 156 + 113 + 84 + 41 + 41 + 10 + 15 + 15 + 20) = 671`.
- WILL is `floor(105.12371134020619 + 55) = 160`.
- Critical Rate is `0.05 + 0.145 + 0.112125 + 0.13455 + 0.05 = 0.491675`.

The test also checks source contributions for the operator, weapon, equipment,
set, talents, and derived stats. These values establish reproducibility for one
captured build. Direct in-game display comparisons remain unverified.
