"""World normalization distinguishes absent source numbers from observed zero."""

from copy import deepcopy

import pytest

from skport import ImageSource
from skport.games.endfield.clean.world import build_factory_state
from skport.games.endfield.models import PlayerIdentity

PLAYER = PlayerIdentity(skport_id="social", game_uid="game", name="Owner")


def snapshot(*, supplied: bool = False, null: bool = False) -> dict:
    values = (
        {
            "level": None if null else 0,
            "exp": None if null else "0",
            "expToLevelUp": None if null else 0,
            "remainMoney": None if null else 0,
            "moneyMax": None if null else "0",
            "isFinalMaxLevel": None if null else False,
        }
        if supplied or null
        else {}
    )
    meter = {"count": None if null else 0, "total": None if null else "0"} if supplied or null else {}
    return {
        "detail": {
            "domain": [
                {
                    "domainId": "region",
                    "name": "Region",
                    **({"level": values["level"]} if values else {}),
                    "moneyMgr": deepcopy(meter),
                    "settlements": [{"id": "settlement", "name": "Settlement", **values}],
                    "levels": [{"levelId": "area", "name": "Area", "puzzleCount": deepcopy(meter)}],
                }
            ],
            "spaceShip": {"rooms": [{"id": "room", **({"level": values["level"]} if values else {})}]},
        }
    }


@pytest.mark.parametrize("null", [False, True])
def test_missing_and_null_numbers_remain_unset_through_all_world_sections(null: bool):
    raw = snapshot(null=null)
    original = deepcopy(raw)
    model = build_factory_state(raw, PLAYER, ImageSource.SKPORT)
    region, cabin = model.regions[0], model.cabins[0]
    settlement, counter = region.settlements[0], region.areas[0].counters[0]
    assert "level" not in region.model_fields_set and "level" not in cabin.model_fields_set
    assert not {"level", "maximum_level"} & settlement.model_fields_set
    for meter in (region.funds, settlement.experience, settlement.stock, counter):
        assert not {"current", "maximum"} & meter.model_fields_set
    assert raw == original


def test_observed_zero_and_false_are_preserved_as_supplied_values():
    model = build_factory_state(snapshot(supplied=True), PLAYER, ImageSource.SKPORT)
    region, cabin = model.regions[0], model.cabins[0]
    settlement, counter = region.settlements[0], region.areas[0].counters[0]
    assert region.level == cabin.level == settlement.level == 0
    assert "level" in region.model_fields_set and "level" in cabin.model_fields_set
    assert {"level", "maximum_level"} <= settlement.model_fields_set
    assert settlement.maximum_level is False
    for meter in (region.funds, settlement.experience, settlement.stock, counter):
        assert meter.current == meter.maximum == 0
        assert {"current", "maximum"} <= meter.model_fields_set


def test_partial_meters_keep_observed_current_separate_from_missing_maximum():
    raw = snapshot()
    region = raw["detail"]["domain"][0]
    region["moneyMgr"] = {"count": "7"}
    region["settlements"][0].update({"exp": 0, "moneyMax": "12", "isFinalMaxLevel": True})
    region["levels"][0]["puzzleCount"] = {"total": 43}
    model = build_factory_state(raw, PLAYER, ImageSource.SKPORT)
    region = model.regions[0]
    settlement, counter = region.settlements[0], region.areas[0].counters[0]
    assert region.funds.current == 7 and "maximum" not in region.funds.model_fields_set
    assert settlement.experience.current == 0 and "maximum" not in settlement.experience.model_fields_set
    assert settlement.stock.maximum == 12 and "current" not in settlement.stock.model_fields_set
    assert counter.maximum == 43 and "current" not in counter.model_fields_set
    assert settlement.maximum_level is True and settlement.experience.note == "maximum level"
