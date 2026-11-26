"""Output models preserve image choices, stat units and partial-build semantics."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from skport import ConfigError, SkportClient
from skport.config import ImageSource
from skport.games.endfield.models import (
    CalculationState,
    CharacterBuild,
    CharacterIdentity,
    Equipment,
    ImageLinks,
    ModelIssue,
    ResourceMeter,
    StatBlock,
    StatLine,
    StatUnit,
    StatValue,
    TalentNode,
    TalentTree,
    format_percent,
)


def test_image_preference_preserves_both_sources_and_falls_back() -> None:
    links = ImageLinks(skport="https://skport.invalid/icon.png", enka="https://enka.invalid/icon.png")
    assert links.url == links.skport
    assert links.effective_source is ImageSource.SKPORT
    alternate = links.model_copy(update={"preferred": ImageSource.ENKA})
    assert alternate.url == alternate.enka
    assert alternate.skport == links.skport
    missing = ImageLinks(enka=links.enka)
    assert missing.url == links.enka and missing.effective_source is ImageSource.ENKA
    assert ImageLinks().url is None
    with pytest.raises(ValidationError):
        ImageLinks(enka="charicon/unresolved.png")


def test_percent_values_are_fractions_without_a_zero_to_one_limit() -> None:
    stats = StatBlock(
        values={
            9: StatValue(id=9, value=0.05, unit=StatUnit.FRACTION),
            44: StatValue(id=44, value=1.892, unit=StatUnit.FRACTION),
            87: StatValue(id=87, value=26, unit=StatUnit.FLAT),
            9999: StatValue(id=9999, value=0.925, unit=StatUnit.FACTOR),
        }
    )
    assert stats.percent("critical_rate") == "5.0%"
    assert stats.percent(44) == "189.2%"
    assert stats.arts_intensity == 26
    assert stats.values[9999].display == "0.925×"
    with pytest.raises(ValueError):
        stats.percent(87)
    with pytest.raises(KeyError):
        stats.percent(8888)
    assert format_percent(0.0005) == "0.1%"


def test_unknown_properties_and_metadata_survive_serialization() -> None:
    stats = StatBlock(values={9876: StatValue(id=9876, value=2.75, unit=StatUnit.NUMBER)})
    build = CharacterBuild(
        identity=CharacterIdentity(skport_id="opaque-id"),
        name="New operator",
        stats=stats,
        calculation_state=CalculationState.CALCULATED,
        future_metadata={"source": "skport"},
    )
    payload = json.loads(build.model_dump_json())
    assert payload["stats"]["values"]["9876"]["value"] == 2.75
    assert payload["future_metadata"] == {"source": "skport"}
    assert payload["identity"]["template_id"] is None
    assert payload["images"]["avatar"]["url"] is None


def test_partial_build_remains_renderable_without_canonical_math() -> None:
    build = CharacterBuild(
        identity=CharacterIdentity(skport_id="opaque-id"),
        name="Operator awaiting upstream assets",
        calculation_state=CalculationState.UNAVAILABLE,
        issues=[ModelIssue(code="missing_assets", message="canonical identity unavailable")],
    )
    assert build.stats is None
    assert json.loads(build.model_dump_json())["calculation_state"] == "unavailable"
    with pytest.raises(ValidationError):
        CharacterBuild(
            identity=CharacterIdentity(skport_id="opaque-id"),
            calculation_state=CalculationState.CALCULATED,
        )


def test_duplicate_equipment_slots_are_rejected_but_missing_slots_are_allowed() -> None:
    identity = CharacterIdentity(skport_id="opaque-id")
    CharacterBuild(identity=identity, equipment=[Equipment(slot="body", id="gear")])
    with pytest.raises(ValidationError):
        CharacterBuild(
            identity=identity,
            equipment=[
                Equipment(slot="body", id="gear-a"),
                Equipment(slot="body", id="gear-b"),
            ],
        )


def test_resource_overflow_and_talent_unlock_identity_are_preserved() -> None:
    sanity = ResourceMeter(current=792, maximum=352)
    assert sanity.current == 792 and sanity.ratio == 2.25 and sanity.complete
    tree = TalentTree(
        nodes=[TalentNode(id="a"), TalentNode(id="b", unlocked=True)],
        unlocked_node_ids=["a"],
    )
    assert tree.unlocked_count == 2 and tree.total_count == 2 and tree.progress == 1
    assert ResourceMeter().ratio == 0
    assert TalentTree().progress == 0


def test_canonical_and_display_identity_are_independent() -> None:
    identity = CharacterIdentity(
        skport_id="opaque-id",
        template_id=38,
        str_id="chr_0000_endmin",
        display_template_id=22,
        display_str_id="chr_0001_endminm",
    )
    assert identity.template_id == 38 and identity.display_template_id == 22
    with pytest.raises(ValidationError):
        StatBlock(values={1: StatValue(id=2, value=100)})


def test_unresolved_equipment_line_does_not_invent_a_zero_value() -> None:
    line = StatLine(name="New stat awaiting canonical assets")
    assert line.value is None and line.display is None


def test_invalid_client_icon_preference_uses_the_sdk_configuration_error() -> None:
    with pytest.raises(ConfigError, match="unsupported image source"):
        SkportClient(tokens=["placeholder"], icon_source="unavailable-provider")
