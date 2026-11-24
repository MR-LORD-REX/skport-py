"""Shared foundations for normalized, serializable Endfield output."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class OutputModel(BaseModel):
    """Keep future metadata while validating known output fields."""

    model_config = ConfigDict(extra="allow", validate_assignment=True, allow_inf_nan=False)


class ModelIssue(OutputModel):
    """Describe unavailable or unsupported data without inventing a result."""

    code: str
    message: str
    path: str = ""
