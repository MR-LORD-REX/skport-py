"""Assemble card-ready builds while keeping resolution and arithmetic separate."""

from __future__ import annotations

from typing import Any

from skport.assets import AssetSnapshot
from skport.config import ClientConfig, ImageSource, MissingAssetPolicy
from skport.errors import MappingError, SkportError
from skport.games.endfield.calc import calculate_character
from skport.games.endfield.calc.types import ResolvedCharacter
from skport.games.endfield.clean.common import description, image_links, rarity, semantic
from skport.games.endfield.models import (
    BuildStatus,
    CalculationState,
    CharacterBuild,
    CharacterIdentity,
    CharacterImages,
    ItemSummary,
    ModelIssue,
    PlayerIdentity,
    Skill,
    SkillForm,
)
from skport.games.endfield.resolve import resolve_character

_SKILL_SUFFIX = {
    "skill_type_normal_attack": "NormalAttack",
    "skill_type_normal_skill": "NormalSkill",
    "skill_type_combo_skill": "ComboSkill",
    "skill_type_ultimate_skill": "UltimateSkill",
}


def build_skills(
    raw: dict[str, Any],
    resolved: ResolvedCharacter | None,
    preferred: ImageSource,
) -> list[Skill]:
    """Join observed levels with wire descriptions and verified canonical icons."""
    result = []
    observed = raw.get("userSkills") or {}
    avatar = resolved.avatar if resolved else {}
    for entry in (raw.get("charData") or {}).get("skills") or []:
        state = observed.get(entry.get("id"), {})
        level = int(state.get("level") or 0)
        level_entry = (entry.get("descLevelParams") or {}).get(str(level)) or {}
        params = {
            **(entry.get("descParams") or {}),
            **(level_entry.get("params", level_entry) or {}),
        }
        suffix = _SKILL_SUFFIX.get(str((entry.get("type") or {}).get("key") or ""))
        canonical_key = f"{avatar.get('StrId')}_{suffix}" if avatar and suffix else ""
        canonical = (avatar.get("SkillInfoMap") or {}).get(canonical_key) or {}
        result.append(
            Skill(
                id=str(entry.get("id") or ""),
                key=canonical_key,
                name=str(entry.get("name") or ""),
                type=semantic(entry.get("type"), preferred),
                icon=image_links(entry.get("iconUrl"), canonical.get("Icon"), preferred),
                level=level,
                max_level=int(state.get("maxLevel") or 12),
                description=description(entry.get("desc") or "", params),
                params=params,
                forms=[
                    SkillForm(
                        name=str(form.get("name") or ""),
                        description=description(form.get("desc") or "", form.get("descParams")),
                        params=form.get("descParams") or {},
                    )
                    for form in entry.get("forms") or []
                ],
                raw_description=entry.get("desc") or "",
                level_params=entry.get("descLevelParams") or {},
            )
        )
    return result


def build_character(
    raw: dict[str, Any],
    snapshot: AssetSnapshot | None,
    config: ClientConfig,
    *,
    owner: PlayerIdentity | None = None,
    locale: str = "en",
    labels: dict[str, str] | None = None,
    asset_issue: ModelIssue | None = None,
) -> CharacterBuild:
    """Normalize a build, returning explicit partial state for missing assets."""
    from skport.games.endfield.clean.equipment import build_equipment
    from skport.games.endfield.clean.equipment_set import build_equipment_sets
    from skport.games.endfield.clean.stats import build_stats
    from skport.games.endfield.clean.talents import build_talents
    from skport.games.endfield.clean.weapon import build_weapon

    metadata = raw.get("charData") or {}
    issues = [asset_issue] if asset_issue else []
    resolved = None
    result = None
    if snapshot is not None:
        try:
            resolved = resolve_character(snapshot.tables, raw, revision=snapshot.revision)
            if config.calculate_stats:
                result = calculate_character(snapshot.tables, resolved)
        except SkportError as exc:
            if config.missing_assets is MissingAssetPolicy.RAISE:
                raise
            issues.append(ModelIssue(code=type(exc).__name__, message=str(exc), path=exc.path))
    elif config.calculate_stats and asset_issue is None:
        issues.append(ModelIssue(code="MissingAssets", message="canonical assets are unavailable"))
    if snapshot is None and config.missing_assets is MissingAssetPolicy.RAISE:
        raise MappingError("canonical assets are required to resolve this build")

    avatar = resolved.avatar if resolved else {}
    tables = snapshot.tables if snapshot else None
    display_id = resolved.display_avatar_id if resolved else None
    display = (tables["avatars"].get(str(display_id)) or avatar) if tables and display_id else avatar
    sid = str(avatar.get("StrId") or "") or None
    display_sid = str(display.get("StrId") or "") or None
    images = CharacterImages(
        avatar=image_links(
            metadata.get("avatarSqUrl"),
            f"charremoteicon/icon_{display_sid}.png" if display_sid else None,
            config.icon_source,
        ),
        portrait=image_links(metadata.get("avatarRtUrl"), preferred=config.icon_source),
        half_body=image_links(metadata.get("avatarRtUrl"), preferred=config.icon_source),
        splash=image_links(
            metadata.get("illustrationUrl"),
            f"splash/{display_sid}.webp" if display_sid else None,
            config.icon_source,
        ),
    )
    tactical_raw = (raw.get("tacticalItem") or {}).get("tacticalItemData")
    tactical = (
        ItemSummary(
            id=str(tactical_raw.get("id") or ""),
            name=str(tactical_raw.get("name") or ""),
            description=description(
                tactical_raw.get("activeEffect") or "", tactical_raw.get("activeEffectParams")
            ),
            rarity=rarity(tactical_raw.get("rarity")),
            icon=image_links(tactical_raw.get("iconUrl"), preferred=config.icon_source),
        )
        if tactical_raw
        else None
    )
    if resolved:
        issues.extend(ModelIssue(code="CanonicalAlias", message=warning) for warning in resolved.warnings)
    state = (
        CalculationState.CALCULATED
        if result
        else CalculationState.UNAVAILABLE
        if config.calculate_stats
        else CalculationState.NOT_REQUESTED
    )
    equipment_sets = build_equipment_sets(raw, resolved, tables, config.icon_source, locale)
    build = CharacterBuild(
        identity=CharacterIdentity(
            skport_id=str(raw.get("id") or metadata.get("id") or ""),
            template_id=resolved.avatar_id if resolved else None,
            str_id=sid,
            display_template_id=display_id,
            display_str_id=display_sid,
        ),
        owner=owner,
        name=str(metadata.get("name") or ""),
        level=int(raw.get("level") or 1),
        evolution=int(raw.get("evolvePhase") or 0),
        potential=int(raw.get("potentialLevel") or 0),
        rarity=rarity(metadata.get("rarity")),
        element=semantic(metadata.get("property"), config.icon_source),
        profession=semantic(metadata.get("profession"), config.icon_source),
        weapon_type=semantic(metadata.get("weaponType"), config.icon_source),
        images=images,
        skills=build_skills(raw, resolved, config.icon_source),
        talents=build_talents(raw, resolved, tables, config.icon_source),
        equipment=build_equipment(raw, resolved, tables, config.icon_source, labels=labels),
        equipment_sets=equipment_sets,
        set_effects=[
            effect
            for equipment_set in equipment_sets
            if equipment_set.active
            for effect in equipment_set.effects
        ],
        weapon=build_weapon(raw, resolved, tables, config.icon_source),
        tactical_item=tactical,
        stats=build_stats(result, config.icon_source, labels=labels) if result else None,
        status=BuildStatus.COMPLETE
        if resolved and (result or not config.calculate_stats)
        else BuildStatus.PARTIAL,
        calculation_state=state,
        asset_revision=snapshot.revision if snapshot else None,
        locale=locale,
        issues=issues,
        source_fields={
            key: value
            for key, value in raw.items()
            if key
            not in {
                "charData",
                "weapon",
                "bodyEquip",
                "armEquip",
                "firstAccessory",
                "secondAccessory",
                "tacticalItem",
            }
        },
    )
    if resolved:
        element = avatar.get("Element")
        if element:
            build.element.icons = image_links(
                skport=build.element.icons.skport,
                enka=f"attributeicon/{element}DamageIncrease.png",
                preferred=config.icon_source,
            )
    return build
