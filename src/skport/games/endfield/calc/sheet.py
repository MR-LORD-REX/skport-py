"""Order-independent property aggregation with explicit formula stages."""

from __future__ import annotations

import math
from dataclasses import dataclass

from skport.errors import ConfigError, UnsupportedFormula
from skport.games.endfield.calc.types import Contribution

FLAT_STATS = frozenset({1, 2, 3, 39, 40, 41, 42, 87})
FRACTION_STATS = frozenset(
    {
        9,
        10,
        17,
        19,
        28,
        29,
        30,
        32,
        33,
        35,
        36,
        37,
        38,
        43,
        44,
        50,
        51,
        52,
        53,
        54,
        55,
        56,
        57,
        58,
        59,
        61,
        64,
        65,
        66,
        67,
        68,
        69,
        70,
        71,
        72,
        73,
        74,
        75,
        88,
        89,
    }
)
FACTOR_STATS = frozenset(
    {4, 5, 6, 7, 13, 14, 15, 16, 23, 24, 25, 26, 27, 31, 47, 48, 49, 60, 80, 81, 82, 83, 84, 85, 86}
)
FORMULAS = frozenset(
    {"BaseAddition", "BaseMultiplier", "BaseFinalAddition", "BaseFinalMultiplier", "Addition"}
)


def stat_unit(stat_id: int) -> str:
    """Return metadata-defined units without inferring them from magnitude."""
    if stat_id in FLAT_STATS:
        return "flat"
    if stat_id in FRACTION_STATS:
        return "fraction"
    if stat_id in FACTOR_STATS:
        return "factor"
    return "number"


@dataclass(slots=True)
class _Property:
    base: float = 0.0
    ratio: float = 0.0
    final_addition: float = 0.0
    final_factor: float = 1.0
    addition: float = 0.0
    has_base: bool = False

    def total(self, neutral: float) -> float:
        base = self.base if self.has_base else neutral
        return (base * (1 + self.ratio) + self.final_addition) * self.final_factor + self.addition


class StatSheet:
    """Retain float contributions until the explicit presentation boundary."""

    def __init__(self, main: int, secondary: int) -> None:
        self.main = main
        self.secondary = secondary
        self.properties: dict[int, _Property] = {}
        self.contributions: list[Contribution] = []

    def add(self, stat_id: int | str, value: float, formula: str = "BaseAddition", *, source: str) -> None:
        """Apply one modifier, expanding main/sub attributes by identity."""
        original = int(stat_id)
        resolved = {10000: self.main, 10001: self.secondary}.get(original, original)
        if formula not in FORMULAS:
            raise UnsupportedFormula(
                f"unsupported stat formula {formula!r}",
                context={"stat_id": resolved, "formula": formula, "source": source},
            )
        amount = float(value)
        if not math.isfinite(amount):
            raise ConfigError("stat contributions must be finite", context={"stat_id": resolved})
        prop = self.properties.setdefault(resolved, _Property())
        if formula == "BaseAddition":
            prop.base += amount
            prop.has_base = True
        elif formula == "BaseMultiplier":
            prop.ratio += amount
        elif formula == "BaseFinalAddition":
            prop.final_addition += amount
        elif formula == "BaseFinalMultiplier":
            prop.final_factor *= amount
        else:
            prop.addition += amount
        self.contributions.append(Contribution(resolved, amount, formula, source, original))

    def value(self, stat_id: int) -> float:
        """Read an unrounded total; factor-only properties have neutral one."""
        prop = self.properties.get(stat_id)
        if prop is None:
            return 0.0
        return prop.total(1.0 if stat_id in FACTOR_STATS else 0.0)

    def integer(self, stat_id: int) -> int:
        """Floor a flat stat at a game-defined derived-stat boundary."""
        return math.floor(self.value(stat_id) + 1e-9)

    def output(self) -> dict[int, float | int]:
        """Preserve all properties, flooring only known integer sheet values."""
        return {
            stat: self.integer(stat) if stat in FLAT_STATS else self.value(stat)
            for stat in sorted(self.properties)
        }
