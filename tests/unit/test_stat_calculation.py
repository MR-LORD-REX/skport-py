"""Calculation policy regressions using hand-computed static sheet values."""

from __future__ import annotations

import copy

import pytest

from skport import ConfigError, MappingError, UnsupportedFormula
from skport.games.endfield.calc import ResolvedCharacter, ResolvedEquipment, StatSheet, calculate_character
from skport.games.endfield.calc.levels import weapon_skill_levels


def simple_loadout():
    avatar = {
        "StrId": "chr_example",
        "MainAttrId": 39,
        "SubAttrId": 42,
        "BaseAttributes": {
            "39": {"BaseValue": 20, "AddValue": 0},
            "40": {"BaseValue": 10, "AddValue": 0},
            "41": {"BaseValue": 5, "AddValue": 0},
            "42": {"BaseValue": 30, "AddValue": 0},
        },
        "BaseHpByLevel": [100],
        "BaseAtkByLevel": [10],
        "AttributeNodes": {},
        "PotAttributes": [],
    }
    tables = {"skills": {}, "weapon_meta": {}, "gems": {}, "equips": {"Items": {}, "Suits": {}}}
    return tables, ResolvedCharacter(1, avatar, {"level": 1, "talent": {}})


def test_formula_stages_are_independent_of_modifier_order():
    modifiers = [
        (100, "BaseAddition"),
        (0.1, "BaseMultiplier"),
        (5, "BaseFinalAddition"),
        (0.9, "BaseFinalMultiplier"),
        (7, "Addition"),
    ]
    for order in (modifiers, list(reversed(modifiers))):
        sheet = StatSheet(39, 42)
        for amount, formula in order:
            sheet.add(1, amount, formula, source="fixture")
        assert sheet.value(1) == pytest.approx(110.5)
        assert sheet.integer(1) == 110
        assert len(sheet.contributions) == 5


def test_fractional_contributions_are_not_truncated_and_pseudo_stat_is_not_guessed():
    sheet = StatSheet(39, 42)
    sheet.add(39, 100, source="base")
    sheet.add(10000, 0.6, source="first")
    sheet.add(10000, 0.6, source="second")
    assert sheet.value(39) == pytest.approx(101.2)
    assert sheet.integer(39) == 101
    assert sheet.contributions[-1].original_stat_id == 10000
    sheet.add(10001, 1.0, source="flat-secondary")
    assert sheet.value(42) == 1.0


def test_final_factors_have_neutral_one_and_unknown_stats_survive():
    sheet = StatSheet(39, 42)
    sheet.add(47, 0.9, "BaseFinalMultiplier", source="first")
    sheet.add(47, 0.8, "BaseFinalMultiplier", source="second")
    sheet.add(98765, 1.2345, source="future")
    assert sheet.output()[47] == pytest.approx(0.72)
    assert sheet.output()[98765] == 1.2345
    with pytest.raises(UnsupportedFormula):
        sheet.add(1, 5, "NewFormula", source="future")
    with pytest.raises(ConfigError):
        sheet.add(1, float("nan"), source="invalid")


def test_derived_stats_keep_direct_treatment_and_all_talent_attributes():
    tables, resolved = simple_loadout()
    avatar = copy.deepcopy(resolved.avatar)
    avatar["AttributeNodes"] = {"dual": {"41": 4, "42": 5}}
    avatar["PotAttributes"] = [
        {
            "Level": 1,
            "Attrs": {"30": {"Value": 0.2, "Formula": "Addition"}},
        }
    ]
    raw = {"level": 1, "potentialLevel": 1, "talent": {"attrNodes": ["dual"]}}
    result = calculate_character(tables, ResolvedCharacter(1, avatar, raw))
    assert result.values[41] == 9
    assert result.values[42] == 35
    assert result.values[1] == 200
    assert result.values[2] == 11
    assert result.values[30] == pytest.approx(0.235)
    assert result.units[30] == "fraction"
    assert result.units[41] == "flat"


def test_gear_enhancements_use_explicit_shared_line_slots():
    tables, resolved = simple_loadout()
    item = {
        "SuitId": "",
        "AttrModifiers": [
            {"AttrType": 3, "Formula": "BaseAddition", "Values": [10, 10]},
            {"AttrType": 52, "Formula": "BaseAddition", "Values": [0.1, 0.2]},
            {"AttrType": 53, "Formula": "BaseAddition", "Values": [0.1, 0.2]},
        ],
    }
    equipment = ResolvedEquipment("bodyEquip", 2, item, {"1": 1}, (0, 1, 1))
    loadout = ResolvedCharacter(1, resolved.avatar, resolved.raw, equipment=(equipment,))
    result = calculate_character(tables, loadout)
    assert result.values[52] == result.values[53] == 0.2
    assert result.values[3] == 10
    invalid = ResolvedEquipment("bodyEquip", 2, item, {"1": 2}, (0, 1, 1))
    with pytest.raises(ConfigError):
        calculate_character(tables, ResolvedCharacter(1, resolved.avatar, resolved.raw, equipment=(invalid,)))


def test_three_piece_suit_reads_first_value_and_two_pieces_are_inactive():
    tables, resolved = simple_loadout()
    tables["skills"]["suit-skill"] = {"PropMap": {"9": {"Formula": "BaseAddition", "Values": [0.05, 0.9]}}}
    tables["equips"]["Suits"]["set"] = {"SkillId": "suit-skill"}
    item = {"SuitId": "set", "AttrModifiers": []}
    equipment = tuple(ResolvedEquipment(str(index), index, item, {}, ()) for index in range(3))
    assert (
        9
        not in calculate_character(
            tables, ResolvedCharacter(1, resolved.avatar, resolved.raw, equipment=equipment[:2])
        ).values
    )
    assert (
        calculate_character(
            tables, ResolvedCharacter(1, resolved.avatar, resolved.raw, equipment=equipment)
        ).values[9]
        == 0.05
    )


@pytest.mark.parametrize("level", [0, 2])
def test_out_of_range_character_levels_fail(level):
    tables, resolved = simple_loadout()
    with pytest.raises(ConfigError):
        calculate_character(tables, ResolvedCharacter(1, resolved.avatar, {"level": level}))


def test_operator_correction_uses_highest_unlocked_tier_and_total_attack_ratio():
    tables, resolved = simple_loadout()
    avatar = copy.deepcopy(resolved.avatar)
    avatar["StrId"] = "chr_0015_lifeng"
    nodes = ["chr_0015_lifeng_passive_skill_0_1", "chr_0015_lifeng_passive_skill_0_2"]
    result = calculate_character(
        tables,
        ResolvedCharacter(1, avatar, {"level": 1, "talent": {"latestPassiveSkillNodes": nodes}}),
    )
    passive = next(c for c in result.contributions if c.source.startswith("passive:lifeng"))
    assert passive.value == pytest.approx(10 * (5 + 30) * 0.0015)
    assert result.values[2] == 12


def test_defense_passive_adds_will_conversion_after_base_defense():
    tables, resolved = simple_loadout()
    avatar = copy.deepcopy(resolved.avatar)
    avatar["StrId"] = "chr_0020_meurs"
    raw = {"level": 1, "talent": {"latestPassiveSkillNodes": ["chr_0020_meurs_passive_skill_0_2"]}}
    result = calculate_character(tables, ResolvedCharacter(1, avatar, raw))
    assert result.values[3] == 3
    assert next(c for c in result.contributions if c.source.startswith("passive:")).value == pytest.approx(
        3.6
    )


def test_weapon_essence_points_change_skill_levels_with_upper_bounds():
    tables = {
        "weapon_meta": {
            "TalentSkillLevelBounds": {"refine": {"0": [{"lowerBound": 1, "upperBound": 2}]}},
            "BreakSkillLevelBounds": {"break": {"1": [{"lowerBound": 1, "upperBound": 3}]}},
        },
        "skills": {"skill": {"TagId": "strength"}},
        "gems": {"TermNums": {"7": {"TagId": "strength"}}},
    }
    weapon = {"TalentTemplateId": "refine", "BreakthroughTemplateId": "break", "SkillList": ["skill"]}
    assert weapon_skill_levels(tables, weapon, 0, 1, ((7, 99),)) == (5,)
    with pytest.raises(MappingError):
        weapon_skill_levels(tables, weapon, 0, 2)
