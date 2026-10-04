"""Versioned configuration contracts (ADR-0019).

A draft names the profile revision it pins and the optional modules it enables.
Core modules are always on and are never part of the input.
"""

from typing import Literal, Self
from uuid import UUID

from pydantic import AwareDatetime, Field, StrictInt, model_validator

from gorgona_booking.business.contracts import Strict, Versioned
from gorgona_booking.business.modules import OPTIONAL_MODULE_IDS

ConfigurationState = Literal["draft", "validated", "published", "superseded"]
ProblemCode = Literal[
    "MODULE_NOT_READY", "DEPENDENCY_MISSING", "REGISTRY_CHANGED", "PROFILE_OUTDATED"
]


class ConfigurationDraftInput(Versioned):
    expected_version: StrictInt = Field(ge=0, le=2_147_483_646)
    profile_revision: StrictInt = Field(ge=1, le=2_147_483_647)
    module_ids: tuple[str, ...] = Field(default=(), max_length=len(OPTIONAL_MODULE_IDS))

    @model_validator(mode="after")
    def known_optional_modules(self) -> Self:
        if len(set(self.module_ids)) != len(self.module_ids):
            raise ValueError("Select each module only once")
        if set(self.module_ids) - OPTIONAL_MODULE_IDS:
            raise ValueError("Unknown or core module; core modules are always enabled")
        return self


class ConfigurationCommand(Versioned):
    expected_revision: StrictInt = Field(ge=1, le=2_147_483_646)


class ConfigurationProblem(Strict):
    code: ProblemCode
    module_id: str | None
    message: str


class ConfigurationValidation(Strict):
    registry_version: int
    problems: tuple[ConfigurationProblem, ...]
    warnings: tuple[ConfigurationProblem, ...]


class ConfigurationVersionView(Strict):
    schema_version: Literal[1] = 1
    business_id: UUID
    version: int = Field(ge=1)
    state: ConfigurationState
    revision: int = Field(ge=1)
    profile_revision: int
    registry_version: int
    module_ids: tuple[str, ...]
    created_at: AwareDatetime
    validation: ConfigurationValidation | None
    validated_at: AwareDatetime | None
    published_at: AwareDatetime | None
    superseded_at: AwareDatetime | None
    superseded_by_version: int | None


class ConfigurationView(Strict):
    schema_version: Literal[1] = 1
    business_id: UUID
    registry_version: int
    # No published version yet: the implicit baseline keeps today's behaviour.
    baseline: bool
    published: ConfigurationVersionView | None
    latest: ConfigurationVersionView | None
    effective_module_ids: tuple[str, ...]


class ConfigurationVersionList(Strict):
    schema_version: Literal[1] = 1
    business_id: UUID
    items: tuple[ConfigurationVersionView, ...]
    next_cursor: int | None


class ModuleStop(Strict):
    module_id: str
    stops: str


class ConfigurationPreview(Strict):
    schema_version: Literal[1] = 1
    business_id: UUID
    version: int
    compared_to_version: int | None
    enabling: tuple[str, ...]
    disabling: tuple[str, ...]
    stopping: tuple[ModuleStop, ...]
    industries_added: tuple[int, ...]
    industries_removed: tuple[int, ...]
    profile_revision: int
    latest_profile_revision: int | None
    problems: tuple[ConfigurationProblem, ...]
    warnings: tuple[ConfigurationProblem, ...]
