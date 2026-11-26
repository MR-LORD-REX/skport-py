"""Weapon display levels use identified unlock bounds and applied essence points."""

from copy import deepcopy

import pytest

from skport import ImageSource
from skport.games.endfield.calc.types import ResolvedCharacter
from skport.games.endfield.clean.weapon import build_weapon
from skport.games.endfield.models import Skill


def fixture(*, refine=0, levels=(9, 4), points=(6, 3), upper=(9, 4)):
    weapon = {
        "SkillList": [1, 2],
        "Icon": "/ui/ef/test_weapon.png",
        "LevelTemplateId": "curve",
        "TalentTemplateId": "refine",
        "BreakthroughTemplateId": "break",
    }
    raw = {
        "weapon": {
            "level": 1,
            "refineLevel": refine,
            "breakthroughLevel": 4,
            "weaponData": {
                "id": "opaque-weapon",
                "name": "Weapon",
                "rarity": {"key": "rarity_6"},
                "skillInfos": [
                    {"skill": {"key": "wire-key-a"}, "gemTagId": "tag-a", "maxLevel": upper[0]},
                    {"skill": {"key": "wire-key-b"}, "gemTagId": "tag-b", "maxLevel": upper[1]},
                ],
            },
            "skills": [
                {"key": "wire-key-a", "name": "Localized skill", "level": levels[0]},
                {"key": "wire-key-b", "name": "Different skill", "level": levels[1]},
            ],
        }
    }
    terms = ()
    if points is not None:
        raw["weapon"]["gem"] = {
            "id": "opaque-gem",
            "gemData": {"name": "Essence", "templateId": 1070},
            "terms": [
                {"id": "opaque-a", "name": "Completely different term label", "cost": points[0]},
                {"id": "opaque-b", "name": "Unrelated localized label", "cost": points[1]},
            ],
        }
        terms = ((10, points[0]), (20, points[1]))
    tables = {
        "skills": {
            "1": {
                "TagId": "tag-a",
                "PropMap": {
                    "42": {"Formula": "BaseAddition", "Values": list(range(1, 13))},
                },
            },
            "2": {"TagId": "tag-b", "PropMap": {}},
        },
        "weapon_meta": {
            "TalentSkillLevelBounds": {
                "refine": {
                    "1": [{"lowerBound": 0, "upperBound": 0}, {"lowerBound": 1, "upperBound": 1}],
                }
            },
            "BreakSkillLevelBounds": {
                "break": {
                    "4": [
                        {"lowerBound": 3, "upperBound": upper[0]},
                        {"lowerBound": 1, "upperBound": upper[1]},
                    ]
                }
            },
            "LevelCurves": {"curve": [100]},
        },
        "gems": {"TermNums": {"10": {"TagId": "tag-a"}, "20": {"TagId": "tag-b"}}},
    }
    resolved = ResolvedCharacter(
        avatar_id=1,
        avatar={"MainAttrId": 42, "SubAttrId": 41},
        raw=raw,
        weapon_id=1,
        weapon=weapon,
        weapon_skill_levels=levels,
        gem_template_id=1070 if points is not None else None,
        gem_terms=terms,
    )
    return raw, resolved, tables


def test_stable_tags_match_localized_terms_and_keep_effective_values_unchanged():
    raw, resolved, tables = fixture()
    original = deepcopy(raw)
    weapon = build_weapon(raw, resolved, tables, ImageSource.ENKA)
    assert [(s.tag_id, s.base_level, s.bonus_level, s.level) for s in weapon.skills] == [
        ("tag-a", 3, 6, 9),
        ("tag-b", 1, 3, 4),
    ]
    assert weapon.skills[0].effects[0].value == 9
    assert [term.points for term in weapon.gem.terms] == [6, 3]
    assert raw == original


def test_refinement_unlocks_are_part_of_base_not_essence_bonus():
    raw, resolved, tables = fixture(refine=1, levels=(9, 5), upper=(9, 4))
    weapon = build_weapon(raw, resolved, tables, ImageSource.ENKA)
    assert [(s.base_level, s.bonus_level, s.level) for s in weapon.skills] == [(3, 6, 9), (2, 3, 5)]


def test_capped_essence_points_do_not_reduce_the_observed_base_unlocks():
    raw, resolved, tables = fixture(levels=(7, 4), points=(6, 99), upper=(7, 4))
    weapon = build_weapon(raw, resolved, tables, ImageSource.ENKA)
    assert [(s.base_level, s.bonus_level, s.level) for s in weapon.skills] == [(3, 4, 7), (1, 3, 4)]
    assert [term.points for term in weapon.gem.terms] == [6, 99]


def test_no_essence_has_only_base_capsules():
    raw, resolved, tables = fixture(levels=(3, 1), points=None)
    weapon = build_weapon(raw, resolved, tables, ImageSource.ENKA)
    assert weapon.gem is None
    assert [(s.base_level, s.bonus_level) for s in weapon.skills] == [(3, 0), (1, 0)]


def test_reordered_wire_skills_preserve_identified_splits():
    raw, resolved, tables = fixture()
    raw["weapon"]["skills"].reverse()
    weapon = build_weapon(raw, resolved, tables, ImageSource.ENKA)
    assert [(s.key, s.base_level, s.bonus_level) for s in weapon.skills] == [
        ("wire-key-a", 3, 6),
        ("wire-key-b", 1, 3),
    ]


@pytest.mark.parametrize("unavailable", ["bounds", "matching-points"])
def test_unconfirmed_split_remains_unknown_while_source_level_is_preserved(unavailable):
    raw, resolved, tables = fixture(points=(2, 3))
    if unavailable == "bounds":
        tables["weapon_meta"]["BreakSkillLevelBounds"].clear()
    weapon = build_weapon(raw, resolved, tables, ImageSource.ENKA)
    assert weapon.skills[0].tag_id == "tag-a"
    assert weapon.skills[0].level == 9
    assert weapon.skills[0].base_level is weapon.skills[0].bonus_level is None
    assert weapon.skills[0].effects[0].value == 9


def test_wire_tag_is_retained_without_canonical_assets():
    raw, _, _ = fixture()
    weapon = build_weapon(raw, None, None, ImageSource.SKPORT)
    assert [skill.tag_id for skill in weapon.skills] == ["tag-a", "tag-b"]
    assert all(skill.base_level is skill.bonus_level is None for skill in weapon.skills)


def test_observed_level_below_confirmed_base_does_not_invent_smaller_base():
    raw, resolved, tables = fixture(levels=(2, 4))
    weapon = build_weapon(raw, resolved, tables, ImageSource.ENKA)
    skill = weapon.skills[0]
    assert skill.level == 2 and skill.effects[0].value == 2
    assert skill.tag_id == "tag-a"
    assert skill.base_level is skill.bonus_level is None


def test_existing_skill_snapshots_remain_valid_without_display_level_metadata():
    skill = Skill.model_validate({"id": "legacy", "level": 9, "max_level": 9})
    assert skill.tag_id is skill.base_level is skill.bonus_level is None
    assert Skill.model_validate_json(skill.model_dump_json()).level == 9
