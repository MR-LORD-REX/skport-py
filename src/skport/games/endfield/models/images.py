"""Artwork candidates that keep source choice independent from game data."""

from __future__ import annotations

from urllib.parse import urlsplit

from pydantic import Field, computed_field, field_validator

from skport.config import ImageSource
from skport.games.endfield.models.base import OutputModel


class ImageLinks(OutputModel):
    """Retain both real URLs and prefer SKPORT artwork by default."""

    skport: str | None = None
    enka: str | None = None
    preferred: ImageSource = ImageSource.SKPORT

    @field_validator("skport", "enka")
    @classmethod
    def validate_url(cls, value: str | None) -> str | None:
        """Normalize missing links and reject unresolved relative paths."""
        if value is None or not value.strip():
            return None
        value = value.strip()
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("artwork URLs must use HTTP or HTTPS")
        return value

    @computed_field  # type: ignore[prop-decorator]
    @property
    def effective_source(self) -> ImageSource | None:
        """Select an available candidate without asserting network health."""
        if self.preferred is ImageSource.SKPORT:
            return ImageSource.SKPORT if self.skport else ImageSource.ENKA if self.enka else None
        return ImageSource.ENKA if self.enka else ImageSource.SKPORT if self.skport else None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def url(self) -> str | None:
        """Return the preferred available image URL."""
        if self.effective_source is ImageSource.SKPORT:
            return self.skport
        if self.effective_source is ImageSource.ENKA:
            return self.enka
        return None


class CharacterImages(OutputModel):
    """Separate artwork variants used by profile and build card layouts."""

    avatar: ImageLinks = Field(default_factory=ImageLinks)
    portrait: ImageLinks = Field(default_factory=ImageLinks)
    splash: ImageLinks = Field(default_factory=ImageLinks)
    half_body: ImageLinks = Field(default_factory=ImageLinks)
    focal_point: tuple[float, float] | None = None

    @field_validator("focal_point")
    @classmethod
    def validate_focus(cls, value: tuple[float, float] | None) -> tuple[float, float] | None:
        """Keep optional crop guidance normalized to the image bounds."""
        if value is not None and any(position < 0 or position > 1 for position in value):
            raise ValueError("focal point coordinates must lie between zero and one")
        return value


class SemanticLabel(OutputModel):
    """A stable key and localized label, without a renderer color palette."""

    key: str = ""
    name: str = ""
    icons: ImageLinks = Field(default_factory=ImageLinks)
