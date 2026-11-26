"""Reject unsupported curve inputs while retaining valid cached calculations."""

from __future__ import annotations

from dataclasses import replace

import pytest

from skport.errors import ConfigError, MappingError
from skport.games.endfield.calc import ResolvedCharacter, calculate_character


def loadout():
    avatar = {
        "StrId": "chr_example",
        "MainAttrId": 39,
        "SubAttrId": 42,
        "BaseAttributes": {
            "39": {"BaseValue": 20},
            "42": {"BaseValue": 30},
        },
        "BaseHpByLevel": [100],
        "BaseAtkByLevel": [10],
        "AttributeNodes": {"strength": {"39": 10}},
    }
    weapon = {"LevelTemplateId": "example", "SkillList": [1]}
    tables = {
        "weapon_meta": {"LevelCurves": {"example": [10]}},
        "skills": {"1": {"PropMap": {"39": {"Values": [10, 20], "Formula": "BaseAddition"}}}},
        "equips": {"Items": {}, "Suits": {}},
    }
    resolved = ResolvedCharacter(
        1,
        avatar,
        {"level": 1, "weapon": {"level": 1}, "talent": {}},
        weapon_id=1,
        weapon=weapon,
        weapon_skill_levels=(1,),
    )
    return tables, resolved


@pytest.mark.parametrize("value", [True, False, 1.9, None, "invalid"])
@pytest.mark.parametrize("source", ["character", "weapon"])
def test_invalid_wire_levels_do_not_become_valid_curve_indices(value, source):
    tables, resolved = loadout()
    raw = dict(resolved.raw)
    if source == "character":
        raw["level"] = value
    else:
        raw["weapon"] = {"level": value}
    with pytest.raises(ConfigError) as failure:
        calculate_character(tables, replace(resolved, raw=raw))
    assert failure.value.context["source"] == source


def test_future_skill_level_is_reported_as_missing_local_data():
    tables, resolved = loadout()
    with pytest.raises(MappingError) as failure:
        calculate_character(tables, replace(resolved, weapon_skill_levels=(3,)))
    assert failure.value.context["skill_id"] == 1
    assert failure.value.context["stat_id"] == "39"
    assert failure.value.context["level"] == 3


def test_one_static_skill_value_remains_valid_for_higher_effective_levels():
    tables, resolved = loadout()
    tables["skills"]["1"]["PropMap"]["39"]["Values"] = [10]
    result = calculate_character(tables, replace(resolved, weapon_skill_levels=(9,)))
    assert result.values[39] == 30


@pytest.mark.parametrize("value", [-1, True, 1.5])
def test_invalid_effective_skill_level_is_not_silently_ignored(value):
    tables, resolved = loadout()
    with pytest.raises(ConfigError):
        calculate_character(tables, replace(resolved, weapon_skill_levels=(value,)))


@pytest.mark.parametrize("canonical", [False, True])
def test_duplicate_unlock_ids_do_not_double_the_character_attribute_bonus(canonical):
    tables, resolved = loadout()
    nodes = ("strength", "strength")
    raw = {**resolved.raw, "talent": {"attrNodes": list(nodes)}}
    result = calculate_character(
        tables,
        replace(resolved, raw=raw, attribute_nodes=nodes if canonical else ()),
    )
    assert result.values[39] == 40
    assert result.values[1] == 300
    assert len([part for part in result.contributions if part.source == "talent:strength"]) == 1
